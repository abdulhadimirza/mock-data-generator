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

@dataclass
class ChatEvent:
    """Base class for all events in the chat history."""
    event_type: str = field(init=False)

@dataclass
class UserMessageEvent(ChatEvent):
    content: str
    is_history: bool = False
    event_type: str = field(default='user_message', init=False)

@dataclass
class AgentMessageCompleteEvent(ChatEvent):
    content: str
    event_type: str = field(default='agent_message_complete', init=False)

@dataclass
class AgentThinkingEvent(ChatEvent):
    event_type: str = field(default='agent_thinking', init=False)

@dataclass
class AgentToolRequestEvent(ChatEvent):
    tool_name: str
    arguments: Dict[str, Any]
    event_type: str = field(default='agent_tool_request', init=False)

@dataclass
class AgentToolResultEvent(ChatEvent):
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    event_type: str = field(default='agent_tool_result', init=False)

@dataclass
class AgentToolErrorEvent(ChatEvent):
    tool_name: str
    arguments: Dict[str, Any]
    error: str
    event_type: str = field(default='agent_tool_error', init=False)

@dataclass
class AgentToolApprovalRequestEvent(ChatEvent):
    tool_name: str
    arguments: Dict[str, Any]
    message: str
    event_type: str = field(default='agent_tool_approval_request', init=False)

@dataclass
class AgentMessageStartEvent(ChatEvent):
    event_type: str = field(default='agent_message_start', init=False)

@dataclass
class AgentMessageChunkEvent(ChatEvent):
    chunk: str
    event_type: str = field(default='agent_message_chunk', init=False)

@dataclass
class AgentTurnCompleteEvent(ChatEvent):
    event_type: str = field(default='agent_turn_complete', init=False)

@dataclass
class AgentErrorEvent(ChatEvent):
    error: str
    event_type: str = field(default='agent_error', init=False)

# --- Subagent Specific Events ---

@dataclass
class AgentSubagentStartEvent(ChatEvent):
    subagent_name: str
    arguments: Dict[str, Any]
    event_type: str = field(default='agent_subagent_start', init=False)

@dataclass
class AgentSubagentResultEvent(ChatEvent):
    subagent_name: str
    result: str
    event_type: str = field(default='agent_subagent_result', init=False)

@dataclass
class AgentSubagentMessageChunkEvent(ChatEvent):
    subagent_name: str
    chunk: str
    event_type: str = field(default='agent_subagent_message_chunk', init=False)

@dataclass
class AgentSubagentToolRequestEvent(ChatEvent):
    subagent_name: str
    tool_name: str
    arguments: Dict[str, Any]
    event_type: str = field(default='agent_subagent_tool_request', init=False)

@dataclass
class AgentSubagentToolResultEvent(ChatEvent):
    subagent_name: str
    tool_name: str
    result: str
    event_type: str = field(default='agent_subagent_tool_result', init=False)

class ChatAgent:
    """
    A unified abstraction for an agentic chatbot session.
    
    This class uses an event-driven architecture. UIs can subscribe to events
    (like MessageChunkEvent for streaming) and update themselves accordingly.
    """
    
    def __init__(self, thread_id: str = 'default_session'):
        """
        Initialize a new or existing chat session.
        """
        self.history: List[ChatEvent] = []
        self.config: RunnableConfig = {'configurable': {'thread_id': thread_id}, 'recursion_limit': 50}
        self._listeners: List[Callable[[ChatEvent], None]] = []
        
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
                    self._emit(AgentMessageStartEvent())
                    self._emit(AgentMessageCompleteEvent(content=text_content))
                    
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tc in msg.tool_calls:
                        tool_calls_map[tc['id']] = tc
                        self._emit(AgentToolRequestEvent(
                            tool_name=tc['name'],
                            arguments=tc['args']
                        ))
                
                # If there are no tool calls, it means the agent finished its turn
                if not getattr(msg, 'tool_calls', []):
                    self._emit(AgentTurnCompleteEvent())
                    
            elif isinstance(msg, ToolMessage):
                tc = tool_calls_map.get(msg.tool_call_id)
                t_name = tc['name'] if tc else getattr(msg, 'name', 'Unknown')
                t_args = tc['args'] if tc else {}
                
                if getattr(msg, 'status', 'success') == 'error':
                    self._emit(AgentToolErrorEvent(
                        tool_name=t_name,
                        arguments=t_args,
                        error=msg.content if isinstance(msg.content, str) else str(msg.content)
                    ))
                else:
                    self._emit(AgentToolResultEvent(
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
                        
                    self._emit(AgentToolApprovalRequestEvent(
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
            name = ns.split(':')[0]
            if name in ('editor_subagent_graph', 'editor_subagent', 'call_data_editor'):
                return 'Data Editor'
            elif name in ('generator_subagent_graph', 'generator_subagent', 'call_sample_generator'):
                return 'Sample Data Generator'
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
        if not isinstance(event, (AgentMessageChunkEvent, AgentSubagentMessageChunkEvent, AgentThinkingEvent)):
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
        pending_tool_errors: List[AgentToolErrorEvent] = []
        
        try:
            self._emit(AgentThinkingEvent())
            
            for event in stream:
                namespace = event.get('params', {}).get('namespace', [])
                subagent_name = self._get_subagent_name(namespace)

                if event['method'] == 'messages':
                    payload_dict = event['params']['data'][0]
                    event_type = payload_dict['event']

                    if subagent_name:
                        if event_type == 'content-block-delta':
                            delta = payload_dict['delta']
                            if delta.get('type') == 'text-delta':
                                text_chunk = delta['text']
                                self._emit(AgentSubagentMessageChunkEvent(subagent_name=subagent_name, chunk=text_chunk))
                    else:
                        if event_type == 'content-block-start':
                            block_type = payload_dict['content']['type']
                            if block_type == 'text':
                                self._emit(AgentMessageStartEvent())
                                current_msg_buffer = ''
                        elif event_type == 'content-block-delta':
                            delta = payload_dict['delta']
                            if delta.get('type') == 'text-delta':
                                text_chunk = delta['text']
                                self._emit(AgentMessageChunkEvent(chunk=text_chunk))
                                current_msg_buffer += text_chunk
                        elif event_type == 'content-block-finish':
                            if current_msg_buffer:
                                self._emit(AgentMessageCompleteEvent(content=current_msg_buffer))
                                current_msg_buffer = ''
                elif event['method'] == 'tools':
                    data = event['params']['data']
                    if subagent_name:
                        if data['event'] == 'tool-started':
                            tool_name = data['tool_name']
                            tool_input = data['input']
                            tool_call_id = data.get('tool_call_id')
                            if tool_call_id:
                                active_tools[tool_call_id] = {
                                    'tool_name': tool_name,
                                    'input': tool_input
                                }
                            self._emit(AgentSubagentToolRequestEvent(
                                subagent_name=subagent_name,
                                tool_name=tool_name,
                                arguments=tool_input
                            ))
                        elif data['event'] == 'tool-finished':
                            tool_message = data['output']
                            tool_output = tool_message.content if hasattr(tool_message, 'content') else str(tool_message)
                            tool_call_id = data.get('tool_call_id')
                            active_tool = active_tools.pop(tool_call_id, {}) if tool_call_id else {}
                            t_name = active_tool.get('tool_name', data.get('tool_name', 'Unknown'))
                            self._emit(AgentSubagentToolResultEvent(
                                subagent_name=subagent_name,
                                tool_name=t_name,
                                result=tool_output
                            ))
                    else:
                        if data['event'] == 'tool-started':
                            tool_name = data['tool_name']
                            tool_input = data['input']
                            tool_call_id = data['tool_call_id']
                            active_tools[tool_call_id] = {
                                'tool_name': tool_name,
                                'input': tool_input
                            }
                            self._emit(AgentToolRequestEvent(tool_name=tool_name, arguments=tool_input))
                        elif data['event'] == 'tool-finished':
                            tool_message = data['output']
                            tool_output = tool_message.content if hasattr(tool_message, 'content') else str(tool_message)
                            tool_call_id = data['tool_call_id']
                            active_tool = active_tools.pop(tool_call_id, {})
                            t_name = active_tool.get('tool_name', 'Unknown')
                            t_input = active_tool.get('input', {})
                            
                            if getattr(tool_message, 'status', 'success') == 'error':
                                self._emit(AgentToolErrorEvent(tool_name=t_name, arguments=t_input, error=tool_output))
                            else:
                                self._emit(AgentToolResultEvent(tool_name=t_name, arguments=t_input, result=tool_output))
                                
                            self._emit(AgentThinkingEvent())
                        elif data['event'] == 'tool-error':
                            tool_call_id = data.get('tool_call_id')
                            active_tool = active_tools.pop(tool_call_id, {}) if tool_call_id else {}
                            t_name = active_tool.get('tool_name', 'Unknown')
                            t_input = active_tool.get('input', {})
                            err_msg = str(data.get('message') or data.get('error') or "Tool Failed")
                            pending_tool_errors.append(AgentToolErrorEvent(tool_name=t_name, arguments=t_input, error=err_msg))
                elif event['method'] == 'custom:subagent_start':
                    data = event['params']['data']
                    tool_name = data.get('tool_name', 'Unknown')
                    tool_input = data.get('input', {})
                    s_name = "Data Editor" if tool_name == "call_data_editor" else ("Sample Data Generator" if tool_name == "call_sample_generator" else tool_name)
                    self._emit(AgentSubagentStartEvent(subagent_name=s_name, arguments=tool_input))
                elif event['method'] == 'custom:subagent_end':
                    data = event['params']['data']
                    tool_name = data.get('tool_name', 'Unknown')
                    s_name = "Data Editor" if tool_name == "call_data_editor" else ("Sample Data Generator" if tool_name == "call_sample_generator" else tool_name)
                    formatted_result = self._format_subagent_output(data.get('output', ''))
                    self._emit(AgentSubagentResultEvent(subagent_name=s_name, result=formatted_result))
                    self._emit(AgentThinkingEvent())
                elif event['method'] == 'custom:subagent_error':
                    data = event['params']['data']
                    tool_name = data.get('tool_name', 'Unknown')
                    s_name = "Data Editor" if tool_name == "call_data_editor" else ("Sample Data Generator" if tool_name == "call_sample_generator" else tool_name)
                    err_msg = str(data.get('error') or "Subagent execution failed")
                    self._emit(AgentSubagentResultEvent(subagent_name=s_name, result=f"Error: {err_msg}"))
                    self._emit(AgentThinkingEvent())

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
                        
                    self._emit(AgentToolApprovalRequestEvent(
                        tool_name=t_name,
                        arguments=t_args,
                        message=t_msg
                    ))
            else:
                # Stream completed without interruption; emit any real pending tool errors
                for err_event in pending_tool_errors:
                    self._emit(err_event)
                    self._emit(AgentThinkingEvent())
        except GraphRecursionError as e:
            error_msg = f"Recursion limit reached: {str(e)}"
            self._emit(AgentErrorEvent(error=error_msg))
            self._inject_error_to_agent_state(error_msg)
        except Exception as e:
            error_msg = f"Agent execution failed: {str(e)}"
            self._emit(AgentErrorEvent(error=error_msg))
            self._inject_error_to_agent_state(error_msg)
        finally:
            self._emit(AgentTurnCompleteEvent())

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
        if isinstance(event, AgentMessageChunkEvent):
            # Print chunks on the same line to test streaming
            print(event.chunk, end="", flush=True)
        else:
            # Print other events with their type to clearly see the order
            print(f"\n[EVENT EMITTED] {type(event).__name__}")
            if isinstance(event, AgentMessageCompleteEvent):
                print(f"   Content Length: {len(event.content)} characters")
            elif isinstance(event, UserMessageEvent):
                print(f"   User Says: {event.content}")
            elif isinstance(event, AgentToolRequestEvent):
                print(f"   Tool: {event.tool_name} requested")
            elif isinstance(event, AgentToolResultEvent):
                print(f"   Tool: {event.tool_name} returned result")
            elif isinstance(event, AgentErrorEvent):
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
        print(f"History[{i}]: {type(event).__name__}")