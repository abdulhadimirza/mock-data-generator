from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, MessagesState, START, END

from shared.llm import get_llm
from core.prompts import supervisor_system_prompt

from subagents.reader import database_reader_graph, call_database_reader
from subagents.generator import sample_generator_graph, call_sample_generator
from core.subagent_nodes import create_subagent_node
from core.routing import route_supervisor
from core.checkpointer import get_checkpointer

# Supervisor subagent tool definitions
supervisor_tools = [call_database_reader, call_sample_generator]

# Subagent prompt builders
def _reader_prompt_builder(args: dict) -> str:
    return args.get('query', '')

def _generator_prompt_builder(args: dict) -> str:
    return args.get('query', '')

reader_subagent_node = create_subagent_node(
    subgraph=database_reader_graph,
    tool_name='call_database_reader',
    prompt_builder=_reader_prompt_builder,
    default_completion_msg="Database Reader task completed."
)

generator_subagent_node = create_subagent_node(
    subgraph=sample_generator_graph,
    tool_name='call_sample_generator',
    prompt_builder=_generator_prompt_builder,
    default_completion_msg="Sample Data Generator task completed."
)

def supervisor_node(state):
    llm = get_llm(supervisor_tools)
    state_messages = state.get("messages", []) if isinstance(state, dict) else getattr(state, "messages", [])
    messages = [SystemMessage(content=supervisor_system_prompt)] + list(state_messages)
    response = llm.invoke(messages)
    return {"messages": [response]}

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
    return main_workflow.compile(checkpointer=memory)

agent = build_agent()
