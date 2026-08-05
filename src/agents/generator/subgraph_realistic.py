from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END

from shared.llm import get_llm, deepseek_planner, gemini_planner
from .prompts import realistic_planner_system_prompt
from .state import GeneratorState
from .nodes import (
    emit_progress,
    sandbox_execution_node,
    subgraph_route_execution,
)
from .nodes_realistic import (
    utility_synthesizer_node,
    realistic_code_generator_node,
)

planner_llm = get_llm(primary=deepseek_planner, fallbacks=[gemini_planner])


def realistic_planner_node(state: GeneratorState, config: RunnableConfig = None):
    emit_progress("Planning realistic analytics mock data strategy...")
    state_messages = state.get('messages', [])
    relevant_tables = state.get('relevant_tables', [])
    schema_map = state.get('schema_map', '')
    
    system_prompt = realistic_planner_system_prompt
    if relevant_tables:
        system_prompt += f"\n\nRelevant tables identified for this request:\n<relevant_tables>\n{', '.join(relevant_tables)}\n</relevant_tables>"
    if schema_map:
        system_prompt += f"\n\nSchema map of relevant tables:\n<schema_map>\n{schema_map}\n</schema_map>"
        
    messages = [SystemMessage(content=system_prompt)] + list(state_messages)
    response = planner_llm.invoke(messages, config=config)
    return {'generated_plan': response.content}


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

