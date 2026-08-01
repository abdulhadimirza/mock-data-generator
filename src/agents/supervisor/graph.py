from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, MessagesState, START, END

from shared.llm import get_llm, deepseek_supervisor, gemini_supervisor
from .prompts import supervisor_system_prompt
from .routing import route_supervisor

from agents.reader import database_reader_graph, call_database_reader
from agents.generator import mock_generator_graph, call_mock_generator
from core.subagent_nodes import create_subagent_node
from core.checkpointer import get_checkpointer
from langgraph.prebuilt import ToolCallTransformer
from core.stream import CustomModeTransformer

# Supervisor subagent tool definitions
supervisor_tools = [call_database_reader, call_mock_generator]

# Subagent prompt builders
def _reader_prompt_builder(args: dict) -> str:
    return args.get('query', '')

def _generator_prompt_builder(args: dict) -> str:
    return args.get('query', '')

reader_subagent_node = create_subagent_node(
    subgraph=database_reader_graph,
    tool_name='call_database_reader',
    prompt_builder=_reader_prompt_builder,
    default_completion_msg='Database Reader task completed.'
)

generator_subagent_node = create_subagent_node(
    subgraph=mock_generator_graph,
    tool_name='call_mock_generator',
    prompt_builder=_generator_prompt_builder,
    default_completion_msg='Mock Data Generator task completed.'
)

supervisor_llm = get_llm(primary=deepseek_supervisor, fallbacks=[gemini_supervisor], tools=supervisor_tools)

def supervisor_node(state):
    state_messages = state.get('messages', []) if isinstance(state, dict) else getattr(state, 'messages', [])
    messages = [SystemMessage(content=supervisor_system_prompt)] + list(state_messages)
    response = supervisor_llm.invoke(messages)
    return {'messages': [response]}

def build_agent():
    main_workflow = StateGraph(MessagesState)
    
    main_workflow.add_node('supervisor_agent', supervisor_node)

    main_workflow.add_node('reader_subagent', reader_subagent_node)
    main_workflow.add_node('generator_subagent', generator_subagent_node)

    main_workflow.add_edge(START, 'supervisor_agent')

    main_workflow.add_conditional_edges(
        'supervisor_agent', 
        route_supervisor,
        {
            'reader_subagent': 'reader_subagent',
            'generator_subagent': 'generator_subagent',
            END: END
        }
    )

    main_workflow.add_edge('reader_subagent', 'supervisor_agent')
    main_workflow.add_edge('generator_subagent', 'supervisor_agent')

    memory = get_checkpointer()
    return main_workflow.compile(
        checkpointer=memory,
        transformers=[ToolCallTransformer, CustomModeTransformer]
    )

agent = build_agent()
