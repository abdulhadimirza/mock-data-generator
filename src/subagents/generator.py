from typing import Optional
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition

from utils.tools import generator_tools
from utils.nodes import get_llm
from utils.prompts import generator_system_prompt

# 1. Create Sample Data Generator Subgraph
def generator_node(state):
    llm = get_llm(generator_tools)
    state_messages = state.get("messages", []) if isinstance(state, dict) else getattr(state, "messages", [])
    messages = [SystemMessage(content=generator_system_prompt)] + list(state_messages)
    response = llm.invoke(messages)
    return {"messages": [response]}

generator_workflow = StateGraph(MessagesState)


generator_workflow.add_node('agent', generator_node)
generator_workflow.add_node('tools', ToolNode(generator_tools))

generator_workflow.add_edge(START, 'agent')
generator_workflow.add_conditional_edges('agent', tools_condition, {'tools': 'tools', END: END})
generator_workflow.add_edge('tools', 'agent')

sample_generator_graph = generator_workflow.compile(name="generator_subagent_graph")


# 2. Subagent Tool Definition
@tool
def call_sample_generator(target_table: str, requirements: Optional[str] = None) -> str:
    """
    Delegate synthetic mock data generation and populating database tables to the Sample Data Generator subagent.
    
    Args:
        target_table: Name of the table to generate sample data for.
        requirements: Optional custom rules or specific column guidelines.
    """
    return "Sample Data Generator task initiated."
