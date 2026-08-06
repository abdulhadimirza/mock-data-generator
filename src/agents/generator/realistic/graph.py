from langgraph.graph import StateGraph, START, END

from ..common.nodes import (
    sandbox_execution_node,
    subgraph_route_execution,
)
from ..state import GeneratorState
from .nodes import (
    realistic_planner_node,
    utility_synthesizer_node,
    realistic_code_generator_node,
)


def _build_realistic_subgraph():
    builder = StateGraph(GeneratorState)
    builder.add_node('planner', realistic_planner_node)
    builder.add_node('utility_synthesizer', utility_synthesizer_node)
    builder.add_node('code_generator', realistic_code_generator_node)
    builder.add_node('sandbox_execution', sandbox_execution_node)
    
    builder.add_edge(START, 'planner')
    builder.add_edge('planner', 'utility_synthesizer')
    builder.add_edge('utility_synthesizer', 'code_generator')
    builder.add_edge('code_generator', 'sandbox_execution')
    
    builder.add_conditional_edges(
        'sandbox_execution',
        subgraph_route_execution,
        {
            'code_generator': 'code_generator',
            END: END
        }
    )
    return builder.compile(name="realistic_subgraph")


realistic_subgraph = _build_realistic_subgraph()
