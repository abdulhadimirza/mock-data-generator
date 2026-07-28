from typing import Optional
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition

from utils.tools import generator_tools, list_tables, get_tables_schema_with_deps
from utils.nodes import get_llm
from utils.prompts import generator_planner_system_prompt
from utils.state import GeneratorState, TableSelectionResponse

# Top-level LLM Instantiation
filter_llm = get_llm().with_structured_output(TableSelectionResponse)
planner_llm = get_llm()

# 1. Stateless Filter Node
def filter_tables_node(state: GeneratorState):
    tables = list_tables.invoke({})
    filter_prompt = (
        f"Available tables in database:\n{tables}\n\n"
        "Based on the user query, return only the list of table names relevant for generating data."
    )
    state_messages = state["messages"]
    messages = [SystemMessage(content=filter_prompt)] + list(state_messages)
    
    result = filter_llm.invoke(messages)
    
    relevant_tables = result.relevant_tables
    return {"relevant_tables": relevant_tables}

# 2. Fetch Schema Node
def fetch_schema_node(state: GeneratorState):
    relevant_tables = state.get("relevant_tables", [])
    if not relevant_tables:
        return {"schema_map": ""}
    
    schema_map = get_tables_schema_with_deps.invoke({"table_names": relevant_tables})
    return {"schema_map": schema_map}

# 3. Mock Data Generator Planner Node
def generator_planner_node(state: GeneratorState):
    state_messages = state["messages"]
    
    relevant_tables = state.get("relevant_tables", [])
    schema_map = state.get("schema_map", "")
    
    system_prompt = generator_planner_system_prompt
    if relevant_tables:
        system_prompt += f"\n\nRelevant tables identified for this request: {', '.join(relevant_tables)}"
    if schema_map:
        system_prompt += f"\n\nSchema map of relevant tables:\n{schema_map}"
        
    messages = [SystemMessage(content=system_prompt)] + list(state_messages)
    response = planner_llm.invoke(messages)
    return {"messages": [response]}

generator_workflow = StateGraph(GeneratorState)

generator_workflow.add_node('filter_tables', filter_tables_node)
generator_workflow.add_node('fetch_schema', fetch_schema_node)
generator_workflow.add_node('planner', generator_planner_node)

generator_workflow.add_edge(START, 'filter_tables')
generator_workflow.add_edge('filter_tables', 'fetch_schema')
generator_workflow.add_edge('fetch_schema', 'planner')
generator_workflow.add_edge('planner', END)

sample_generator_graph = generator_workflow.compile(name="generator_subagent_graph")



# 2. Subagent Tool Definition
@tool
def call_sample_generator(query: str) -> str:
    """
    Delegate mock data generation planning to the Sample Data Generator subagent.
    Returns a comprehensive mock data generation plan for database tables.
    
    Args:
        query: Clear request or requirements regarding mock data planning.
    """
    return "Sample Data Generator task initiated."


