from typing import Optional, Callable
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import MessagesState
from langgraph.graph.state import CompiledStateGraph
from langgraph.config import get_stream_writer
from langgraph.errors import GraphInterrupt

def emit_lifecycle_event(event_type: str, tool_name: str, tool_call_id: str, **kwargs):
    try:
        writer = get_stream_writer()
        payload = {'event': event_type, 'tool_name': tool_name, 'tool_call_id': tool_call_id}
        payload.update(kwargs)
        writer(payload)
    except Exception:
        pass

def create_subagent_node(
    subgraph: CompiledStateGraph,
    tool_name: str,
    prompt_builder: Callable[[dict], str],
    default_completion_msg: str
):
    def node(state: MessagesState, config: Optional[RunnableConfig] = None):
        messages = state.get('messages', [])
        if not messages:
            return {'messages': []}
        last_message = messages[-1]
        
        tool_messages = []
        if hasattr(last_message, 'tool_calls'):
            for tc in last_message.tool_calls:
                if tc['name'] == tool_name:
                    prompt = prompt_builder(tc['args'])
                    
                    try:
                        emit_lifecycle_event('subagent_start', tc['name'], tc['id'], input=tc['args'])
                        sub_config = {**(config or {}), 'recursion_limit': 100}
                        result = subgraph.invoke({'messages': [('user', prompt)]}, sub_config)
                        res_messages = result.get('messages', [])
                        
                        final_text = res_messages[-1].content if res_messages else default_completion_msg
                        content = final_text
                        
                        emit_lifecycle_event('subagent_end', tc['name'], tc['id'], output=content)
                            
                        tool_messages.append(ToolMessage(content=content, name=tc['name'], tool_call_id=tc['id']))
                    except GraphInterrupt as e:
                        raise e
                    except Exception as e:
                        emit_lifecycle_event('subagent_error', tc['name'], tc['id'], error=str(e))
                        tool_messages.append(ToolMessage(content=f'Subagent execution failed: {str(e)}', name=tc['name'], tool_call_id=tc['id']))

        return {'messages': tool_messages}
    return node
