from langgraph.graph import MessagesState, END

def route_assistant(state: MessagesState):
    messages = state.get('messages', [])
    if not messages:
        return END
    last_message = messages[-1]
    if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
        return END
    
    tc_names = [tc['name'] for tc in last_message.tool_calls]
    if 'call_data_editor' in tc_names:
        return 'editor_subagent'
    elif 'call_sample_generator' in tc_names:
        return 'generator_subagent'
    else:
        return 'assistant_tools'
