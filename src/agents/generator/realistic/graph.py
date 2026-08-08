from langgraph.graph import StateGraph, START, END

from ..common.nodes import (
    sandbox_execution_node,
    subgraph_route_execution,
)
from .state import RealisticState
from .nodes import (
    realistic_planner_node,
    utility_synthesizer_node,
    realistic_code_generator_node,
    create_ast_checker_node,
    create_syntax_fixer_node,
)


def route_ast_check(success_target: str, fixer_target: str, fallback_target: str, max_retries: int = 3):
    def router(state: RealisticState):
        error = state.get('ast_error')
        retries = state.get('ast_retry_count', 0)

        if not error:
            return success_target
        if retries < max_retries:
            return fixer_target
        return fallback_target

    return router


def _build_realistic_subgraph():
    builder = StateGraph(RealisticState)

    # 1. Main Nodes
    builder.add_node('planner', realistic_planner_node)
    builder.add_node('utility_synthesizer', utility_synthesizer_node)
    builder.add_node('code_generator', realistic_code_generator_node)
    builder.add_node('sandbox_execution', sandbox_execution_node)

    # 2. AST Checker & Fixer Nodes
    builder.add_node('utility_ast_checker', create_ast_checker_node('utility_code'))
    builder.add_node('utility_ast_fixer', create_syntax_fixer_node('utility_code'))
    builder.add_node('code_ast_checker', create_ast_checker_node('generated_code'))
    builder.add_node('code_ast_fixer', create_syntax_fixer_node('generated_code'))

    # 3. Flow 1: Utility Code Loop
    builder.add_edge(START, 'planner')
    builder.add_edge('planner', 'utility_synthesizer')
    builder.add_edge('utility_synthesizer', 'utility_ast_checker')

    builder.add_conditional_edges(
        'utility_ast_checker',
        route_ast_check(
            success_target='code_generator',
            fixer_target='utility_ast_fixer',
            fallback_target='utility_synthesizer',
            max_retries=3,
        ),
        {
            'code_generator': 'code_generator',
            'utility_ast_fixer': 'utility_ast_fixer',
            'utility_synthesizer': 'utility_synthesizer',
        }
    )
    builder.add_edge('utility_ast_fixer', 'utility_ast_checker')

    # 4. Flow 2: Generated Code Loop
    builder.add_edge('code_generator', 'code_ast_checker')

    builder.add_conditional_edges(
        'code_ast_checker',
        route_ast_check(
            success_target='sandbox_execution',
            fixer_target='code_ast_fixer',
            fallback_target='code_generator',
            max_retries=3,
        ),
        {
            'sandbox_execution': 'sandbox_execution',
            'code_ast_fixer': 'code_ast_fixer',
            'code_generator': 'code_generator',
        }
    )
    builder.add_edge('code_ast_fixer', 'code_ast_checker')

    # 5. Flow 3: Sandbox Execution
    builder.add_conditional_edges(
        'sandbox_execution',
        subgraph_route_execution,
        {
            'code_generator': 'code_generator',
            END: END
        }
    )
    return builder.compile(name='realistic_subgraph')


realistic_subgraph = _build_realistic_subgraph()
