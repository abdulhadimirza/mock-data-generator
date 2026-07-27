from typing import Optional
from langchain_core.tools import tool
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition

from utils.tools import reader_tools
from utils.nodes import create_agent_node
from utils.prompts import reader_system_prompt

# 1. Create Database Reader Subgraph
reader_node = create_agent_node(system_prompt=reader_system_prompt, node_tools=reader_tools)
reader_workflow = StateGraph(MessagesState)
reader_workflow.add_node('agent', reader_node)
reader_workflow.add_node('tools', ToolNode(reader_tools))
reader_workflow.add_edge(START, 'agent')
reader_workflow.add_conditional_edges('agent', tools_condition, {'tools': 'tools', END: END})
reader_workflow.add_edge('tools', 'agent')
database_reader_graph = reader_workflow.compile(name="reader_subagent_graph")

# 2. Subagent Tool Definition
@tool
def call_database_reader(query: str) -> str:
    """
    Delegate database schema inspection, table listing, data querying, and read-only analytical tasks to the Database Reader subagent.
    
    Args:
        query: Clear instructions or request regarding database inspection or data querying.
    """
    return "Database Reader task initiated."
