"""
ChatAgent abstraction layer.

This module defines the ChatAgent class, which serves as a decoupled abstraction
between the display interface (CLI/UI) and the underlying agent logic.
"""
from dotenv import load_dotenv
load_dotenv()

import warnings
from langchain_core._api import LangChainBetaWarning
warnings.filterwarnings('ignore', category=LangChainBetaWarning)

from uuid import uuid4
from dataclasses import dataclass, field
from typing import List, Dict, Any, Callable, Optional
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage
from langgraph.prebuilt import ToolCallTransformer
from langgraph.stream import StreamTransformer, StreamChannel
from langgraph.errors import GraphRecursionError
from langgraph.types import Command
from langchain_core.runnables import RunnableConfig

from agent import agent

class SubagentTransformer(StreamTransformer):
    required_stream_modes = ("custom",)
    
    def __init__(self, scope: tuple[str, ...] = ()):
        super().__init__(scope)
        self.subagent_start = StreamChannel("subagent_start")
        self.subagent_end = StreamChannel("subagent_end")
        self.subagent_error = StreamChannel("subagent_error")

    def init(self) -> dict:
        return {
            "subagent_start": self.subagent_start,
            "subagent_end": self.subagent_end,
            "subagent_error": self.subagent_error
        }

    def process(self, event) -> bool:
        if event["method"] == "custom":
            data = event["params"]["data"]
            if isinstance(data, dict):
                event_name = data.get("event")
                if event_name == "subagent_start":
                    self.subagent_start.push(data)
                elif event_name == "subagent_end":
                    self.subagent_end.push(data)
                elif event_name == "subagent_error":
                    self.subagent_error.push(data)
        return True

# --- Consolidated Event Hierarchy ---

@dataclass
class ChatEvent:
    """Base class for all events in the chat history."""
    source: str = "Assistant"
    event_type: str = field(init=False)

@dataclass
class UserMessageEvent(ChatEvent):
    content: str = ""
    is_history: bool = False
    event_type: str = field(default='user_message', init=False)

@dataclass
class MessageStartEvent(ChatEvent):
    event_type: str = field(default='message_start', init=False)

@dataclass
class MessageChunkEvent(ChatEvent):
    chunk: str = ""
    event_type: str = field(default='message_chunk', init=False)

@dataclass
class MessageCompleteEvent(ChatEvent):
    content: str = ""
    event_type: str = field(default='message_complete', init=False)

@dataclass
class ThinkingEvent(ChatEvent):
    event_type: str = field(default='thinking', init=False)

@dataclass
class ToolRequestEvent(ChatEvent):
    tool_name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    event_type: str = field(default='tool_request', init=False)

@dataclass
class ToolResultEvent(ChatEvent):
    tool_name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    event_type: str = field(default='tool_result', init=False)

@dataclass
class ToolErrorEvent(ChatEvent):
    tool_name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    event_type: str = field(default='tool_error', init=False)

@dataclass
class ToolApprovalRequestEvent(ChatEvent):
    tool_name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    event_type: str = field(default='tool_approval_request', init=False)

@dataclass
class SubagentLifecycleEvent(ChatEvent):
    lifecycle_type: str = "start"  # 'start', 'result', 'error'
    arguments: Optional[Dict[str, Any]] = None
    result: Optional[str] = None
    error: Optional[str] = None
    event_type: str = field(default='subagent_lifecycle', init=False)

@dataclass
class TurnCompleteEvent(ChatEvent):
    event_type: str = field(default='turn_complete', init=False)

@dataclass
class ErrorEvent(ChatEvent):
    error: str = ""
    event_type: str = field(default='error', init=False)


DEFAULT_SUBAGENT_NAMES = {
    'reader_subagent_graph': 'Database Reader',
    'reader_subagent': 'Database Reader',
    'call_database_reader': 'Database Reader',
    'generator_subagent_graph': 'Sample Data Generator',
    'generator_subagent': 'Sample Data Generator',
    'call_sample_generator': 'Sample Data Generator',
    'editor_subagent_graph': 'Data Editor (Backup)',
    'editor_subagent': 'Data Editor (Backup)',
    'call_data_editor': 'Data Editor (Backup)',
}


class ChatAgent:
    """
    A unified abstraction for an agentic chatbot session.
    
    This class uses an event-driven architecture. UIs can subscribe to events
    (like MessageChunkEvent for streaming) and update themselves accordingly.
    """
    
    def __init__(self, thread_id: str = 'default_session', subagent_names: Optional[Dict[str, str]] = None):
        """
        Initialize a new or existing chat session.
        """
        self.history: List[ChatEvent] = []
        self.config: RunnableConfig = {'configurable': {'thread_id': thread_id}, 'recursion_limit': 50}
        self._listeners: List[Callable[[ChatEvent], None]] = []
        self.subagent_names: Dict[str, str] = subagent_names if subagent_names is not None else DEFAULT_SUBAGENT_NAMES
        
    def load(self) -> None:
        """
        Load history and emit events to listeners.
        """
        self._restore_history()
        
    def _restore_history(self) -> None:
        """
        Restore chat history from the persisted state.
        """
        state = agent.get_state(self.config)
        if not state or 'messages' not in state.values:
            return
            
        messages: List[BaseMessage] = state.values.get('messages', [])
        tool_calls_map: Dict[str, Dict[str, Any]] = {}
        
        for msg in messages:
            if isinstance(msg, HumanMessage):
                self._emit(UserMessageEvent(content=msg.content, is_history=True))
            elif isinstance(msg, AIMessage):
                text_content = ""
                if isinstance(msg.content, str):
                    text_content = msg.content
                elif isinstance(msg.content, list):
                    for block in msg.content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_content += block.get("text", "")
                        elif isinstance(block, str):
                            text_content += block
                            
                if text_content:
                    self._emit(MessageStartEvent())
                    self._emit(MessageCompleteEvent(content=text_content))
                    
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tc in msg.tool_calls:
                        tool_calls_map[tc['id']] = tc
                        self._emit(ToolRequestEvent(
                            tool_name=tc['name'],
                            arguments=tc['args']
                        ))
                
                # If there are no tool calls, it means the agent finished its turn
                if not getattr(msg, 'tool_calls', []):
                    self._emit(TurnCompleteEvent())
                    
            elif isinstance(msg, ToolMessage):
                tc = tool_calls_map.get(msg.tool_call_id)
                t_name = tc['name'] if tc else getattr(msg, 'name', 'Unknown')
                t_args = tc['args'] if tc else {}
                
                if getattr(msg, 'status', 'success') == 'error':
                    self._emit(ToolErrorEvent(
                        tool_name=t_name,
                        arguments=t_args,
                        error=msg.content if isinstance(msg.content, str) else str(msg.content)
                    ))
                else:
                    self._emit(ToolResultEvent(
                        tool_name=t_name,
                        arguments=t_args,
                        result=msg.content
                    ))

        # Check if the persisted graph state is suspended on a pending interrupt
        if hasattr(state, 'tasks') and state.tasks:
            for task in state.tasks:
                if hasattr(task, 'interrupts') and task.interrupts:
                    payload = task.interrupts[0].value
                    if isinstance(payload, dict):
                        t_name = payload.get("tool_name", "UnknownTool")
                        t_args = payload.get("arguments", {})
                        t_msg = payload.get("message", "Approval required.")
                    else:
                        t_name = "UnknownTool"
                        t_args = {}
                        t_msg = str(payload)
                        
                    self._emit(ToolApprovalRequestEvent(
                        tool_name=t_name,
                        arguments=t_args,
                        message=t_msg
                    ))
                    break
    
    def add_listener(self, listener: Callable[[ChatEvent], None]) -> None:
        """
        Subscribe a callback function to listen to all chat events.
        """
        self._listeners.append(listener)
        
    def _get_subagent_name(self, namespace: List[str]) -> Optional[str]:
        for ns in namespace:
            key = ns.split(':')[0]
            if key in self.subagent_names:
                return self.subagent_names[key]
        return None

    def _format_subagent_output(self, raw_output: Any) -> str:
        if isinstance(raw_output, str):
            return raw_output
        elif isinstance(raw_output, list):
            text_parts = []
            for item in raw_output:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    text_parts.append(item)
                else:
                    text_parts.append(str(item))
            return "\n".join(text_parts) if text_parts else str(raw_output)
        else:
            return str(raw_output)

    def _emit(self, event: ChatEvent) -> None:
        """
        Internal method to add an event to history and notify listeners.
        Note: Chunk events are usually just emitted, while full messages are saved to history.
        """
        if not isinstance(event, (MessageChunkEvent, ThinkingEvent)):
            self.history.append(event)
            
        for listener in self._listeners:
            try:
                listener(event)
            except Exception as e:
                print(f"[ChatAgent] Listener error: {e}")

    def _inject_error_to_agent_state(self, error_msg: str) -> None:
        """
        Inject an error message into the agent's state so the LLM is aware of the failure on the next turn.
        """
        agent.update_state(self.config, {"messages": [("system", f"The previous agent turn failed with error: {error_msg}")]})

    def _process_stream(self, stream) -> None:
        """
        Process the event stream returned by agent.stream_events.
        """
        active_tools: Dict[str, Dict[str, Any]] = {}
        current_msg_buffer = ''
        pending_tool_errors: List[ChatEvent] = []
        
        try:
            self._emit(ThinkingEvent())
            
            for event in stream:
                namespace = event.get('params', {}).get('namespace', [])
                subagent_name = self._get_subagent_name(namespace)
                event_source = subagent_name if subagent_name else "Assistant"

                if event['method'] == 'messages':
                    payload_dict = event['params']['data'][0]
                    event_type = payload_dict['event']

                    if subagent_name:
                        if event_type == 'content-block-delta':
                            delta = payload_dict['delta']
                            if delta.get('type') == 'text-delta':
                                text_chunk = delta['text']
                                self._emit(MessageChunkEvent(source=subagent_name, chunk=text_chunk))
                    else:
                        if event_type == 'content-block-start':
                            block_type = payload_dict['content']['type']
                            if block_type == 'text':
                                self._emit(MessageStartEvent(source="Assistant"))
                                current_msg_buffer = ''
                        elif event_type == 'content-block-delta':
                            delta = payload_dict['delta']
                            if delta.get('type') == 'text-delta':
                                text_chunk = delta['text']
                                self._emit(MessageChunkEvent(source="Assistant", chunk=text_chunk))
                                current_msg_buffer += text_chunk
                        elif event_type == 'content-block-finish':
                            if current_msg_buffer:
                                self._emit(MessageCompleteEvent(source="Assistant", content=current_msg_buffer))
                                current_msg_buffer = ''
                elif event['method'] == 'tools':
                    data = event['params']['data']
                    if data['event'] == 'tool-started':
                        tool_name = data['tool_name']
                        tool_input = data['input']
                        tool_call_id = data.get('tool_call_id')
                        if tool_call_id:
                            active_tools[tool_call_id] = {
                                'tool_name': tool_name,
                                'input': tool_input
                            }
                        self._emit(ToolRequestEvent(source=event_source, tool_name=tool_name, arguments=tool_input))
                    elif data['event'] == 'tool-finished':
                        tool_message = data['output']
                        tool_output = tool_message.content if hasattr(tool_message, 'content') else str(tool_message)
                        tool_call_id = data.get('tool_call_id')
                        active_tool = active_tools.pop(tool_call_id, {}) if tool_call_id else {}
                        t_name = active_tool.get('tool_name', data.get('tool_name', 'Unknown'))
                        t_input = active_tool.get('input', {})
                        
                        if getattr(tool_message, 'status', 'success') == 'error':
                            self._emit(ToolErrorEvent(source=event_source, tool_name=t_name, arguments=t_input, error=tool_output))
                        else:
                            self._emit(ToolResultEvent(source=event_source, tool_name=t_name, arguments=t_input, result=tool_output))
                            
                        if not subagent_name:
                            self._emit(ThinkingEvent())
                    elif data['event'] == 'tool-error':
                        tool_call_id = data.get('tool_call_id')
                        active_tool = active_tools.pop(tool_call_id, {}) if tool_call_id else {}
                        t_name = active_tool.get('tool_name', 'Unknown')
                        t_input = active_tool.get('input', {})
                        err_msg = str(data.get('message') or data.get('error') or "Tool Failed")
                        pending_tool_errors.append(ToolErrorEvent(source=event_source, tool_name=t_name, arguments=t_input, error=err_msg))
                elif event['method'] == 'custom:subagent_start':
                    data = event['params']['data']
                    tool_name = data.get('tool_name', 'Unknown')
                    tool_input = data.get('input', {})
                    s_name = self.subagent_names.get(tool_name, tool_name)
                    self._emit(SubagentLifecycleEvent(source=s_name, lifecycle_type='start', arguments=tool_input))
                elif event['method'] == 'custom:subagent_end':
                    data = event['params']['data']
                    tool_name = data.get('tool_name', 'Unknown')
                    s_name = self.subagent_names.get(tool_name, tool_name)
                    formatted_result = self._format_subagent_output(data.get('output', ''))
                    self._emit(SubagentLifecycleEvent(source=s_name, lifecycle_type='result', result=formatted_result))
                    self._emit(ThinkingEvent())
                elif event['method'] == 'custom:subagent_error':
                    data = event['params']['data']
                    tool_name = data.get('tool_name', 'Unknown')
                    s_name = self.subagent_names.get(tool_name, tool_name)
                    err_msg = str(data.get('error') or "Subagent execution failed")
                    self._emit(SubagentLifecycleEvent(source=s_name, lifecycle_type='error', error=err_msg))
                    self._emit(ThinkingEvent())

            if getattr(stream, 'interrupted', False):
                # Stream was interrupted for human approval; discard transient tool errors
                pending_tool_errors.clear()
                interrupts = getattr(stream, 'interrupts', [])
                if interrupts:
                    payload = interrupts[0].value
                    if isinstance(payload, dict):
                        t_name = payload.get("tool_name", "UnknownTool")
                        t_args = payload.get("arguments", {})
                        t_msg = payload.get("message", "Approval required.")
                    else:
                        t_name = "UnknownTool"
                        t_args = {}
                        t_msg = str(payload)
                        
                    self._emit(ToolApprovalRequestEvent(
                        tool_name=t_name,
                        arguments=t_args,
                        message=t_msg
                    ))
            else:
                # Stream completed without interruption; emit any real pending tool errors
                for err_event in pending_tool_errors:
                    self._emit(err_event)
                    self._emit(ThinkingEvent())
        except GraphRecursionError as e:
            error_msg = f"Recursion limit reached: {str(e)}"
            self._emit(ErrorEvent(error=error_msg))
            self._inject_error_to_agent_state(error_msg)
        except Exception as e:
            error_msg = f"Agent execution failed: {str(e)}"
            self._emit(ErrorEvent(error=error_msg))
            self._inject_error_to_agent_state(error_msg)
        finally:
            self._emit(TurnCompleteEvent())

    def send_message(self, message: str) -> None:
        """
        Initiate sending a message. The agent's progress and response 
        will be communicated entirely via event listeners.
        """
        self._emit(UserMessageEvent(content=message))
        
        input_state = {'messages': [{'role': 'user', 'content': message}]}
        
        stream = agent.stream_events(
            input_state,
            self.config,
            version='v3',
            transformers=[ToolCallTransformer, SubagentTransformer]
        )
        self._process_stream(stream)
        
    def resume_turn(self, resume_data: Any) -> None:
        """
        Resume execution after an interrupt with the provided human feedback.
        """
        stream = agent.stream_events(
            Command(resume=resume_data),
            self.config,
            version='v3',
            transformers=[ToolCallTransformer, SubagentTransformer]
        )
        self._process_stream(stream)
        
    def approve(self) -> None:
        """
        Approve the pending action/tool execution.
        """
        self.resume_turn(True)

    def reject(self) -> None:
        """
        Reject/cancel the pending action/tool execution.
        """
        self.resume_turn(False)

    def respond_to_approval(self, approved: bool) -> None:
        """
        Respond to a pending tool approval request with a boolean decision.
        """
        if approved:
            self.approve()
        else:
            self.reject()
        
    def get_history(self) -> List[ChatEvent]:
        """
        Retrieve the current conversation history.
        """
        return self.history

if __name__ == '__main__':
    print("\n--- Initializing Agent ---")
    testAgent = ChatAgent()
    
    # 1. Define a UI listener function
    def my_ui_renderer(event: ChatEvent):
        if isinstance(event, MessageChunkEvent):
            # Print chunks on the same line to test streaming
            print(event.chunk, end="", flush=True)
        else:
            # Print other events with their type to clearly see the order
            print(f"\n[EVENT EMITTED] {type(event).__name__} (Source: {event.source})")
            if isinstance(event, MessageCompleteEvent):
                print(f"   Content Length: {len(event.content)} characters")
            elif isinstance(event, UserMessageEvent):
                print(f"   User Says: {event.content}")
            elif isinstance(event, ToolRequestEvent):
                print(f"   Tool: {event.tool_name} requested")
            elif isinstance(event, ToolResultEvent):
                print(f"   Tool: {event.tool_name} returned result")
            elif isinstance(event, ErrorEvent):
                print(f"   Error: {event.error}")
            
    # 2. Subscribe the UI to the agent
    testAgent.add_listener(my_ui_renderer)
    testAgent.load()
    
    # 3. Send message (agent will now emit events to the renderer)
    print("\n--- Sending First Message ---")
    testAgent.send_message("List the tables in the database and describe them.")
    
    # 4. Verify History Order
    print("\n\n--- Verifying History Order ---")
    history = testAgent.get_history()
    for i, event in enumerate(history):
        print(f"History[{i}]: {type(event).__name__} (Source: {event.source})")