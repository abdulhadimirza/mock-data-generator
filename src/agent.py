import os
import sqlite3
from typing import Optional
from langchain_core.tools import tool
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.config import get_stream_writer
from langgraph.errors import GraphInterrupt

from utils.tools import assistant_tools as base_assistant_tools, editor_tools, generator_tools
from utils.nodes import create_agent_node
from utils.prompts import assistant_system_prompt, editor_system_prompt, generator_system_prompt

# 1. Create Data Editor Subgraph
editor_node = create_agent_node(system_prompt=editor_system_prompt, node_tools=editor_tools)
editor_workflow = StateGraph(MessagesState)
editor_workflow.add_node('agent', editor_node)
editor_workflow.add_node('tools', ToolNode(editor_tools))
editor_workflow.add_edge(START, 'agent')
editor_workflow.add_conditional_edges('agent', tools_condition, {'tools': 'tools', END: END})
editor_workflow.add_edge('tools', 'agent')
data_editor_graph = editor_workflow.compile(name="editor_subagent_graph")

# 2. Create Sample Data Generator Subgraph
generator_node = create_agent_node(system_prompt=generator_system_prompt, node_tools=generator_tools)
generator_workflow = StateGraph(MessagesState)
generator_workflow.add_node('agent', generator_node)
generator_workflow.add_node('tools', ToolNode(generator_tools))
generator_workflow.add_edge(START, 'agent')
generator_workflow.add_conditional_edges('agent', tools_condition, {'tools': 'tools', END: END})
generator_workflow.add_edge('tools', 'agent')
sample_generator_graph = generator_workflow.compile(name="generator_subagent_graph")

# 3. Define Subagent Schema Tools for Assistant
@tool
def call_data_editor(query: str) -> str:
    """
    Delegate database write or mutation operations (INSERT, UPDATE, DELETE, ALTER, DROP, etc.) to the Data Editor subagent.
    
    Args:
        query: Clear instructions or SQL statement for the write operation.
    """
    return "Data Editor task initiated."

@tool
def call_sample_generator(target_table: str, requirements: Optional[str] = None) -> str:
    """
    Delegate synthetic mock data generation and populating database tables to the Sample Data Generator subagent.
    
    Args:
        target_table: Name of the table to generate sample data for.
        requirements: Optional custom rules or specific column guidelines.
    """
    return "Sample Data Generator task initiated."

# Combine base read-only tools with subagent tools schema
assistant_tools = base_assistant_tools + [call_data_editor, call_sample_generator]

# 4. Define Subagent Node Functions with State Mapping (Invoking subgraphs inside nodes)
def editor_subagent_node(state: MessagesState, config: Optional[RunnableConfig] = None):
    messages = state.get("messages", [])
    if not messages:
        return {"messages": []}
    last_message = messages[-1]
    
    tool_messages = []
    if hasattr(last_message, "tool_calls"):
        for tc in last_message.tool_calls:
            if tc["name"] == "call_data_editor":
                query = tc["args"].get("query", "")
                
                try:
                    writer = get_stream_writer()
                    writer({"event": "subagent_start", "tool_name": tc["name"], "input": tc["args"], "tool_call_id": tc["id"]})
                except Exception:
                    pass

                try:
                    result = data_editor_graph.invoke({"messages": [("user", query)]}, config)
                    res_messages = result.get("messages", [])
                    content = res_messages[-1].content if res_messages else "Data Editor task completed."
                    
                    try:
                        writer = get_stream_writer()
                        writer({"event": "subagent_end", "tool_name": tc["name"], "output": content, "tool_call_id": tc["id"]})
                    except Exception:
                        pass
                        
                    tool_messages.append(ToolMessage(content=content, name=tc["name"], tool_call_id=tc["id"]))
                except GraphInterrupt as e:
                    raise e
                except Exception as e:
                    try:
                        writer = get_stream_writer()
                        writer({"event": "subagent_error", "tool_name": tc["name"], "error": str(e), "tool_call_id": tc["id"]})
                    except Exception:
                        pass
                    tool_messages.append(ToolMessage(content=f"Subagent execution failed: {str(e)}", name=tc["name"], tool_call_id=tc["id"]))

    return {"messages": tool_messages}

def generator_subagent_node(state: MessagesState, config: Optional[RunnableConfig] = None):
    messages = state.get("messages", [])
    if not messages:
        return {"messages": []}
    last_message = messages[-1]
    
    tool_messages = []
    if hasattr(last_message, "tool_calls"):
        for tc in last_message.tool_calls:
            if tc["name"] == "call_sample_generator":
                target_table = tc["args"].get("target_table", "")
                requirements = tc["args"].get("requirements")
                prompt = f"Generate mock data for table '{target_table}'."
                if requirements:
                    prompt += f" Requirements/Rules: {requirements}"
                
                try:
                    writer = get_stream_writer()
                    writer({"event": "subagent_start", "tool_name": tc["name"], "input": tc["args"], "tool_call_id": tc["id"]})
                except Exception:
                    pass

                try:
                    result = sample_generator_graph.invoke({"messages": [("user", prompt)]}, config)
                    res_messages = result.get("messages", [])
                    content = res_messages[-1].content if res_messages else "Sample Data Generator task completed."
                    
                    try:
                        writer = get_stream_writer()
                        writer({"event": "subagent_end", "tool_name": tc["name"], "output": content, "tool_call_id": tc["id"]})
                    except Exception:
                        pass
                        
                    tool_messages.append(ToolMessage(content=content, name=tc["name"], tool_call_id=tc["id"]))
                except GraphInterrupt as e:
                    raise e
                except Exception as e:
                    try:
                        writer = get_stream_writer()
                        writer({"event": "subagent_error", "tool_name": tc["name"], "error": str(e), "tool_call_id": tc["id"]})
                    except Exception:
                        pass
                    tool_messages.append(ToolMessage(content=f"Subagent execution failed: {str(e)}", name=tc["name"], tool_call_id=tc["id"]))

    return {"messages": tool_messages}

# 5. Define Custom Router
def route_assistant(state: MessagesState):
    messages = state.get("messages", [])
    if not messages:
        return END
    last_message = messages[-1]
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return END
    
    tc_names = [tc["name"] for tc in last_message.tool_calls]
    if "call_data_editor" in tc_names:
        return "editor_subagent"
    elif "call_sample_generator" in tc_names:
        return "generator_subagent"
    else:
        return "assistant_tools"

# 6. Create Main Database Assistant Graph
assistant_node = create_agent_node(system_prompt=assistant_system_prompt, node_tools=assistant_tools)
main_workflow = StateGraph(MessagesState)
main_workflow.add_node('database_assistant_agent', assistant_node)
main_workflow.add_node('assistant_tools', ToolNode(base_assistant_tools))
main_workflow.add_node('editor_subagent', editor_subagent_node)
main_workflow.add_node('generator_subagent', generator_subagent_node)

main_workflow.add_edge(START, 'database_assistant_agent')

main_workflow.add_conditional_edges(
    'database_assistant_agent', 
    route_assistant,
    {
        'assistant_tools': 'assistant_tools',
        'editor_subagent': 'editor_subagent',
        'generator_subagent': 'generator_subagent',
        END: END
    }
)

main_workflow.add_edge('assistant_tools', 'database_assistant_agent')
main_workflow.add_edge('editor_subagent', 'database_assistant_agent')
main_workflow.add_edge('generator_subagent', 'database_assistant_agent')

# Implement SqliteSaver Checkpointer
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
raw_db_path = os.getenv('CHECKPOINT_DB_PATH', 'checkpoints.db')
DB_PATH = raw_db_path if os.path.isabs(raw_db_path) else os.path.abspath(os.path.join(PROJECT_ROOT, raw_db_path))
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
memory = SqliteSaver(conn)

agent = main_workflow.compile(checkpointer=memory)
