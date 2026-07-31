from langgraph.stream import StreamTransformer, ProtocolEvent

class CustomModeTransformer(StreamTransformer):
    """
    A lightweight stream transformer that requests the 'custom' stream mode from Pregel.
    This enables custom event streaming via get_stream_writer without altering the raw event stream.
    """
    required_stream_modes = ('custom',)

    def init(self) -> dict:
        return {}

    def process(self, event: ProtocolEvent) -> bool:
        return True
