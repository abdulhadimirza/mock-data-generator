from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode

from utils.tools import assistant_tools as base_assistant_tools
from utils.nodes import create_agent_node
from utils.prompts import assistant_system_prompt

from subagents.editor import data_editor_graph, call_data_editor
from subagents.generator import sample_generator_graph, call_sample_generator
from core.subagent_nodes import create_subagent_node
from core.routing import route_assistant
from core.checkpointer import get_checkpointer

# Combine base read-only tools with subagent tools schema
assistant_tools = base_assistant_tools + [call_data_editor, call_sample_generator]

# Subagent prompt builders
def _editor_prompt_builder(args: dict) -> str:
    return args.get('query', '')

def _generator_prompt_builder(args: dict) -> str:
    target_table = args.get('target_table', '')
    requirements = args.get('requirements')
    prompt = f"Generate mock data for table '{target_table}'."
    if requirements:
        prompt += f" Requirements/Rules: {requirements}"
    return prompt

editor_subagent_node = create_subagent_node(
    subgraph=data_editor_graph,
    tool_name='call_data_editor',
    prompt_builder=_editor_prompt_builder,
    default_completion_msg="Data Editor task completed."
)

generator_subagent_node = create_subagent_node(
    subgraph=sample_generator_graph,
    tool_name='call_sample_generator',
    prompt_builder=_generator_prompt_builder,
    default_completion_msg="Sample Data Generator task completed."
)

def build_agent():
    assistant_node = create_agent_node(system_prompt=assistant_system_prompt, node_tools=assistant_tools)
    main_workflow = StateGraph(MessagesState)
    main_workflow.add_node('database_assistant_agent', assistant_node)
    main_workflow.add_node('assistant_tools', ToolNode(base_assistant_tools))
    main_workflow.add_node('editor_subagent', editor_subagent_node)
    main_workflow.add_node('generator_subagent', generator_subagent_node)

    main_workflow.add_edge(START, 'database_assistant_agent')

    main_workflow.add_conditional_edges(
        'database_assistant_agent', 
        route_assistant,
        {
            'assistant_tools': 'assistant_tools',
            'editor_subagent': 'editor_subagent',
            'generator_subagent': 'generator_subagent',
            END: END
        }
    )

    main_workflow.add_edge('assistant_tools', 'database_assistant_agent')
    main_workflow.add_edge('editor_subagent', 'database_assistant_agent')
    main_workflow.add_edge('generator_subagent', 'database_assistant_agent')

    memory = get_checkpointer()
    return main_workflow.compile(checkpointer=memory)

agent = build_agent()
