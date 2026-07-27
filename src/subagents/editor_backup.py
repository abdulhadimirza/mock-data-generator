from langchain_core.tools import tool
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition

from utils.tools import editor_tools
from utils.nodes import create_agent_node
from utils.prompts import editor_system_prompt

# 1. Create Data Editor Subgraph
editor_node = create_agent_node(system_prompt=editor_system_prompt, node_tools=editor_tools)
editor_workflow = StateGraph(MessagesState)
editor_workflow.add_node('agent', editor_node)
editor_workflow.add_node('tools', ToolNode(editor_tools))
editor_workflow.add_edge(START, 'agent')
editor_workflow.add_conditional_edges('agent', tools_condition, {'tools': 'tools', END: END})
editor_workflow.add_edge('tools', 'agent')
data_editor_graph = editor_workflow.compile(name="editor_subagent_graph")

# 2. Subagent Tool Definition
@tool
def call_data_editor(query: str) -> str:
    """
    Delegate database write or mutation operations (INSERT, UPDATE, DELETE, ALTER, DROP, etc.) to the Data Editor subagent.
    
    Args:
        query: Clear instructions or SQL statement for the write operation.
    """
    return "Data Editor task initiated."
