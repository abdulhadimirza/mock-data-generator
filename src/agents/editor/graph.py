from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition

from .tools import editor_tools
from shared.llm import get_llm
from .prompts import editor_system_prompt

# 1. Create Data Editor Subgraph
def editor_node(state):
    llm = get_llm(editor_tools)
    state_messages = state.get('messages', []) if isinstance(state, dict) else getattr(state, 'messages', [])
    messages = [SystemMessage(content=editor_system_prompt)] + list(state_messages)
    response = llm.invoke(messages)
    return {'messages': [response]}

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
