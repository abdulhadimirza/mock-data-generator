from typing import Optional
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition

from utils.tools import generator_tools, list_tables
from utils.nodes import get_llm
from utils.prompts import generator_system_prompt
from utils.state import GeneratorState, TableSelectionResponse

# 1. Stateless Filter Node
def filter_tables_node(state: GeneratorState):
    tables = list_tables.invoke({})
    filter_prompt = (
        f"Available tables in database:\n{tables}\n\n"
        "Based on the user query, return only the list of table names relevant for generating data."
    )
    state_messages = state["messages"]
    messages = [SystemMessage(content=filter_prompt)] + list(state_messages)
    
    structured_llm = get_llm().with_structured_output(TableSelectionResponse)
    result = structured_llm.invoke(messages)
    
    relevant_tables = result.relevant_tables
    return {"relevant_tables": relevant_tables}

# 2. Sample Data Generator Agent Node
def generator_node(state: GeneratorState):
    llm = get_llm(generator_tools)
    state_messages = state["messages"]
    
    relevant_tables = state["relevant_tables"]
    system_prompt = generator_system_prompt
    if relevant_tables:
        system_prompt += f"\n\nRelevant tables identified for this request: {', '.join(relevant_tables)}"
        
    messages = [SystemMessage(content=system_prompt)] + list(state_messages)
    response = llm.invoke(messages)
    return {"messages": [response]}

generator_workflow = StateGraph(GeneratorState)

generator_workflow.add_node('filter_tables', filter_tables_node)
generator_workflow.add_node('agent', generator_node)
generator_workflow.add_node('tools', ToolNode(generator_tools))

generator_workflow.add_edge(START, 'filter_tables')
generator_workflow.add_edge('filter_tables', 'agent')
generator_workflow.add_conditional_edges('agent', tools_condition, {'tools': 'tools', END: END})
generator_workflow.add_edge('tools', 'agent')

sample_generator_graph = generator_workflow.compile(name="generator_subagent_graph")



# 2. Subagent Tool Definition
@tool
def call_sample_generator(query: str) -> str:
    """
    Delegate synthetic mock data generation and populating database tables to the Sample Data Generator subagent.
    
    Args:
        query: Clear request or instructions regarding mock data generation requirements.
    """
    return "Sample Data Generator task initiated."

