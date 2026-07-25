from typing import Optional, Callable
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import MessagesState
from langgraph.config import get_stream_writer
from langgraph.errors import GraphInterrupt

def create_subagent_node(
    subgraph,
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
                        writer = get_stream_writer()
                        writer({'event': 'subagent_start', 'tool_name': tc['name'], 'input': tc['args'], 'tool_call_id': tc['id']})
                    except Exception:
                        pass

                    try:
                        result = subgraph.invoke({'messages': [('user', prompt)]}, config)
                        res_messages = result.get('messages', [])
                        content = res_messages[-1].content if res_messages else default_completion_msg
                        
                        try:
                            writer = get_stream_writer()
                            writer({'event': 'subagent_end', 'tool_name': tc['name'], 'output': content, 'tool_call_id': tc['id']})
                        except Exception:
                            pass
                            
                        tool_messages.append(ToolMessage(content=content, name=tc['name'], tool_call_id=tc['id']))
                    except GraphInterrupt as e:
                        raise e
                    except Exception as e:
                        try:
                            writer = get_stream_writer()
                            writer({'event': 'subagent_error', 'tool_name': tc['name'], 'error': str(e), 'tool_call_id': tc['id']})
                        except Exception:
                            pass
                        tool_messages.append(ToolMessage(content=f"Subagent execution failed: {str(e)}", name=tc['name'], tool_call_id=tc['id']))

        return {'messages': tool_messages}
    return node
