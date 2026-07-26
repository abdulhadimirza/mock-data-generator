from typing import Optional, Callable
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import MessagesState
from langgraph.graph.state import CompiledStateGraph
from langgraph.config import get_stream_writer
from langgraph.errors import GraphInterrupt

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
                        writer = get_stream_writer()
                        writer({'event': 'subagent_start', 'tool_name': tc['name'], 'input': tc['args'], 'tool_call_id': tc['id']})
                    except Exception:
                        pass

                    try:
                        result = subgraph.invoke({'messages': [('user', prompt)]}, config)
                        res_messages = result.get('messages', [])
                        
                        trace_lines = []
                        for msg in res_messages:
                            if isinstance(msg, AIMessage) and msg.tool_calls:
                                for call in msg.tool_calls:
                                    trace_lines.append(f"- Executed `{call['name']}` with args: {call['args']}")
                            elif isinstance(msg, ToolMessage):
                                res_str = str(msg.content)
                                if len(res_str) > 200:
                                    res_str = res_str[:200] + "... [truncated]"
                                trace_lines.append(f"  Result: {res_str}")
                                
                        trace = "\n".join(trace_lines)
                        final_text = res_messages[-1].content if res_messages else default_completion_msg
                        
                        if trace:
                            content = f"{final_text}\n\n### Execution Trace:\n{trace}"
                        else:
                            content = final_text
                        
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
