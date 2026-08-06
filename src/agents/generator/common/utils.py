from langchain_core.messages import HumanMessage
from langgraph.config import get_stream_writer


def emit_progress(message: str):
    try:
        writer = get_stream_writer()
        writer({
            'event': 'subagent_progress',
            'tool_name': 'call_mock_generator',
            'message': message
        })
    except Exception:
        pass


def _extract_initial_user_request(state_messages):
    for m in state_messages:
        if isinstance(m, HumanMessage):
            return m
    return None
