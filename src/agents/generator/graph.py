from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END

from .state import GeneratorState
from .common.utils import emit_progress
from .common.nodes import (
    infer_intent_node,
    filter_tables_node,
    fetch_schema_node,
    summary_node,
)
from .realistic.graph import realistic_subgraph
from .stress.graph import stress_subgraph


# 9. Main Workflow Assembly
def route_mode(state: GeneratorState):
    mode = state.get('generation_mode', 'Stress Testing')
    if mode == 'Realistic Analytics':
        emit_progress("Routing execution to Realistic Analytics subgraph branch...")
        return 'realistic_branch'
    emit_progress("Routing execution to Stress Testing subgraph branch...")
    return 'stress_branch'


generator_workflow = StateGraph(GeneratorState)

generator_workflow.add_node('infer_intent', infer_intent_node)
generator_workflow.add_node('filter_tables', filter_tables_node)
generator_workflow.add_node('fetch_schema', fetch_schema_node)

generator_workflow.add_node('realistic_branch', realistic_subgraph)
generator_workflow.add_node('stress_branch', stress_subgraph)
generator_workflow.add_node('summary', summary_node)

generator_workflow.add_edge(START, 'infer_intent')
generator_workflow.add_edge('infer_intent', 'filter_tables')
generator_workflow.add_edge('filter_tables', 'fetch_schema')

generator_workflow.add_conditional_edges(
    'fetch_schema',
    route_mode,
    {
        'realistic_branch': 'realistic_branch',
        'stress_branch': 'stress_branch'
    }
)

generator_workflow.add_edge('realistic_branch', 'summary')
generator_workflow.add_edge('stress_branch', 'summary')
generator_workflow.add_edge('summary', END)

mock_generator_graph = generator_workflow.compile(name="generator_subagent_graph")


# Subagent Tool Definition
@tool
def call_mock_generator(query: str) -> str:
    """
    Delegate mock data generation to the Mock Data Generator subagent.

    What it does:
    
    1. Inspects schema.
    2. Clears out existing data if needed.
    3. Generates and inserts mock data into database tables.
    4. Returns a summary of the execution.
    
    Args:
        query: Clear request or requirements regarding mock data generation.
    """
    return "Mock Data Generator task initiated."
