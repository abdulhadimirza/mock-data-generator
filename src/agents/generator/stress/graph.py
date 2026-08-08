from langgraph.graph import StateGraph, START, END

from ..common.nodes import (
    sandbox_execution_node,
    subgraph_route_execution,
)
from .state import StressState
from .nodes import (
    stress_planner_node,
    code_generator_node,
)


def _build_stress_subgraph():
    builder = StateGraph(StressState)
    builder.add_node('planner', stress_planner_node)
    builder.add_node('code_generator', code_generator_node)
    builder.add_node('sandbox_execution', sandbox_execution_node)
    
    builder.add_edge(START, 'planner')
    builder.add_edge('planner', 'code_generator')
    builder.add_edge('code_generator', 'sandbox_execution')
    
    builder.add_conditional_edges(
        'sandbox_execution',
        subgraph_route_execution,
        {
            'code_generator': 'code_generator',
            END: END
        }
    )
    return builder.compile(name='stress_subgraph')


stress_subgraph = _build_stress_subgraph()
