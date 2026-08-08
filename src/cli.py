from dotenv import load_dotenv
load_dotenv()

import json
import shutil
import typer
from rich.console import Console
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich.markdown import Markdown
from rich.panel import Panel
from rich.live import Live
from rich.spinner import Spinner

from chat_agent import (
    ChatAgent,
    ChatEvent,
    UserMessageEvent,
    MessageStartEvent,
    MessageChunkEvent,
    MessageCompleteEvent,
    ThinkingEvent,
    ToolRequestEvent,
    ToolResultEvent,
    ToolErrorEvent,
    ToolApprovalRequestEvent,
    SubagentLifecycleEvent,
    SubagentProgressEvent,
    TurnCompleteEvent,
    ErrorEvent,
)

console = Console()
app = typer.Typer()

def render_tool_request(console: Console, name: str, args: dict):
    try:
        args_str = json.dumps(args, indent=2)
    except Exception:
        args_str = str(args)
        
    console.print(Panel(
        f"[bold cyan]Tool Requested:[/bold cyan] {name}\n\n[bold green]Arguments:[/bold green]\n[dim]{args_str}[/dim]",
        title="* Tool Execution Requested",
        border_style='cyan'
    ))

def render_tool_approval_request(console: Console, name: str, args: dict, message: str):
    try:
        args_str = json.dumps(args, indent=2)
    except Exception:
        args_str = str(args)
        
    body = [
        f"[bold yellow]Approval Required for Tool:[/bold yellow] {name}\n",
        f"[bold white]{message}[/bold white]\n",
        f"[bold green]Arguments:[/bold green]\n[dim]{args_str}[/dim]\n",
        "[bold yellow]Type 'y' / 'yes' to approve, or anything else to cancel.[/bold yellow]"
    ]
    
    console.print(Panel(
        "\n".join(body),
        title="! Action Paused - Human Approval Required",
        border_style='yellow'
    ))


def render_tool_result(console: Console, name: str, result: str):
    console.print(Panel(
        f"[bold cyan]Tool Responded:[/bold cyan] {name}\n\n[bold green]Result:[/bold green]\n[dim]{result}[/dim]",
        title="* Tool Execution Result",
        border_style='green'
    ))

def render_tool_error(console: Console, name: str, args: dict, error: str):
    try:
        args_str = json.dumps(args, indent=2)
    except Exception:
        args_str = str(args)
    console.print(Panel(
        f"[bold cyan]Tool Failed:[/bold cyan] {name}\n\n[bold green]Arguments:[/bold green]\n[dim]{args_str}[/dim]\n\n[bold red]Error:[/bold red]\n[dim]{error}[/dim]",
        title="* Tool Execution Error",
        border_style='red'
    ))

def render_agent_error(console: Console, error: str):
    console.print(Panel(
        f"[bold red]Agent Error:[/bold red]\n[dim]{error}[/dim]",
        title="* Error",
        border_style='red'
    ))

def render_subagent_start(console: Console, subagent_name: str, args: dict):
    try:
        args_str = json.dumps(args, indent=2)
    except Exception:
        args_str = str(args)
        
    console.print(Panel(
        f"[bold magenta]Delegated Work to Subagent:[/bold magenta] {subagent_name}\n\n[bold green]Task Parameters:[/bold green]\n[dim]{args_str}[/dim]",
        title=f"Subagent Delegated: {subagent_name}",
        border_style='magenta'
    ))

def render_subagent_result(console: Console, subagent_name: str, result: str):
    console.print(Panel(
        f"[bold magenta]Subagent Completed Task:[/bold magenta] {subagent_name}\n\n[bold green]Result Output:[/bold green]\n{result}",
        title=f"Subagent Finished: {subagent_name}",
        border_style='magenta'
    ))

def render_subagent_error(console: Console, subagent_name: str, error: str):
    console.print(Panel(
        f"[bold red]Subagent Error:[/bold red] {subagent_name}\n\n[dim]{error}[/dim]",
        title=f"* Subagent Error: {subagent_name}",
        border_style='red'
    ))

def render_subagent_tool_request(console: Console, subagent_name: str, tool_name: str, args: dict):
    try:
        args_str = json.dumps(args, indent=2)
    except Exception:
        args_str = str(args)
        
    console.print(Panel(
        f"[bold blue][Subagent: {subagent_name}] Tool Requested:[/bold blue] {tool_name}\n\n[bold green]Arguments:[/bold green]\n[dim]{args_str}[/dim]",
        title=f"[{subagent_name}]* Tool Execution Requested",
        border_style='blue'
    ))

def render_subagent_tool_result(console: Console, subagent_name: str, tool_name: str, result: str):
    console.print(Panel(
        f"[bold blue][Subagent: {subagent_name}] Tool Responded:[/bold blue] {tool_name}\n\n[bold green]Result:[/bold green]\n[dim]{result}[/dim]",
        title=f"[{subagent_name}]* Tool Execution Result",
        border_style='blue'
    ))

def render_subagent_tool_error(console: Console, subagent_name: str, tool_name: str, args: dict, error: str):
    try:
        args_str = json.dumps(args, indent=2)
    except Exception:
        args_str = str(args)
    console.print(Panel(
        f"[bold red][Subagent: {subagent_name}] Tool Error:[/bold red] {tool_name}\n\n[bold green]Arguments:[/bold green]\n[dim]{args_str}[/dim]\n\n[bold red]Error:[/bold red]\n[dim]{error}[/dim]",
        title=f"[{subagent_name}]* Tool Execution Error",
        border_style='red'
    ))

def render_subagent_progress(console: Console, subagent_name: str, message: str):
    console.print(Panel(
        f"[bold cyan][Subagent: {subagent_name}][/bold cyan] {message}",
        title=f"[{subagent_name}] * Progress Update",
        border_style='cyan'
    ))

class CLIRenderer:
    def __init__(self, console: Console):
        self.console = console
        self.live = None
        self.full_response = ''
        self.awaiting_approval = False
        
        # Dispatcher Registry for event handling
        self.handlers = {
            UserMessageEvent: self._handle_user_message,
            ThinkingEvent: self._handle_thinking,
            MessageStartEvent: self._handle_message_start,
            MessageChunkEvent: self._handle_message_chunk,
            MessageCompleteEvent: self._handle_message_complete,
            ToolRequestEvent: self._handle_tool_request,
            ToolApprovalRequestEvent: self._handle_tool_approval_request,
            ToolResultEvent: self._handle_tool_result,
            ToolErrorEvent: self._handle_tool_error,
            SubagentLifecycleEvent: self._handle_subagent_lifecycle,
            SubagentProgressEvent: self._handle_subagent_progress,
            ErrorEvent: self._handle_error,
            TurnCompleteEvent: self._handle_turn_complete,
        }

    def _debug(self, msg):
        pass

    def start_live(self):
        self._debug("start_live called")
        if not self.live:
            self.live = Live(
                console=self.console, 
                refresh_per_second=10, 
                transient=True, 
                vertical_overflow='visible'
            )
            self.live.start()

    def stop_live(self):
        self._debug(f"stop_live called. live active: {bool(self.live)}")
        if self.live:
            self.live.stop()
            self.live = None

    def handle_event(self, event: ChatEvent):
        handler = self.handlers.get(type(event))
        if handler:
            handler(event)

    def _handle_user_message(self, event: UserMessageEvent):
        self.stop_live()
        if event.is_history:
            self.console.print(f"\n[bold green]You:[/bold green]\n{event.content}")
            self.console.print("\n[bold blue]Assistant:[/bold blue]")

    def _handle_thinking(self, event: ThinkingEvent):
        self.start_live()
        prefix = f'[{event.source}] ' if event.source != 'Assistant' else ''
        self.live.update(Spinner('dots', text=f'[dim]{prefix}Thinking...[/dim]'))

    def _handle_subagent_progress(self, event: SubagentProgressEvent):
        self.stop_live()
        if self.full_response:
            self.console.print(Markdown(self.full_response))
            self.full_response = ''
        render_subagent_progress(self.console, event.source, event.message)

    def _handle_message_start(self, event: MessageStartEvent):
        if event.source == 'Assistant':
            self.full_response = ''

    def _handle_message_chunk(self, event: MessageChunkEvent):
        if event.source != 'Assistant':
            return

        self.full_response += event.chunk
        if not self.live:
            self.start_live()
            
        term_height = shutil.get_terminal_size().lines
        max_lines = max(5, term_height - 10)
        
        lines = self.full_response.split('\n')
        if len(lines) > max_lines:
            display_text = '...\n' + '\n'.join(lines[-max_lines:])
        else:
            display_text = self.full_response
            
        self.live.update(Markdown(display_text + ' ▌'))

    def _handle_message_complete(self, event: MessageCompleteEvent):
        self.stop_live()
        display_text = self.full_response if self.full_response else getattr(event, 'content', '')
        if display_text:
            self.console.print(Markdown(display_text))
        self.full_response = ''

    def _handle_tool_request(self, event: ToolRequestEvent):
        self.stop_live()
        if self.full_response:
            self.console.print(Markdown(self.full_response))
            self.full_response = ''
        
        if event.source != 'Assistant':
            render_subagent_tool_request(self.console, event.source, event.tool_name, event.arguments)
        else:
            render_tool_request(self.console, event.tool_name, event.arguments)

    def _handle_tool_approval_request(self, event: ToolApprovalRequestEvent):
        self.stop_live()
        if self.full_response:
            self.console.print(Markdown(self.full_response))
            self.full_response = ''
        render_tool_approval_request(self.console, event.tool_name, event.arguments, event.message)
        self.awaiting_approval = True

    def _handle_tool_result(self, event: ToolResultEvent):
        self.stop_live()
        if event.source != 'Assistant':
            render_subagent_tool_result(self.console, event.source, event.tool_name, str(event.result))
        else:
            render_tool_result(self.console, event.tool_name, str(event.result))
        self.full_response = ''

    def _handle_tool_error(self, event: ToolErrorEvent):
        self.stop_live()
        if event.source != 'Assistant':
            render_subagent_tool_error(self.console, event.source, event.tool_name, event.arguments, event.error)
        else:
            render_tool_error(self.console, event.tool_name, event.arguments, event.error)
        self.full_response = ''

    def _handle_subagent_lifecycle(self, event: SubagentLifecycleEvent):
        self.stop_live()
        if self.full_response:
            self.console.print(Markdown(self.full_response))
            self.full_response = ''
            
        if event.lifecycle_type == 'start':
            render_subagent_start(self.console, event.source, event.arguments or {})
        elif event.lifecycle_type == 'result':
            render_subagent_result(self.console, event.source, event.result or '')
        elif event.lifecycle_type == 'error':
            render_subagent_error(self.console, event.source, event.error or '')

    def _handle_error(self, event: ErrorEvent):
        self.stop_live()
        render_agent_error(self.console, event.error)
        self.full_response = ''

    def _handle_turn_complete(self, event: TurnCompleteEvent):
        self.stop_live()
        if self.full_response:
            self.console.print(Markdown(self.full_response))
        self.full_response = ''

@app.command()
def main():
    console.print(Panel.fit("[bold blue]Natural Language to SQL CLI[/bold blue]", border_style='blue'))
    
    agent = ChatAgent()
    renderer = CLIRenderer(console)
    agent.add_listener(renderer.handle_event)
    
    # Restore chat history organically via listener events
    console.print("[dim]Restoring previous session...[/dim]")
    agent.load()
                
    session = PromptSession()
    
    bindings = KeyBindings()

    @bindings.add('enter')
    def _(event):
        event.current_buffer.validate_and_handle()

    @bindings.add('escape', 'enter')
    def _(event):
        event.current_buffer.insert_text('\n')
        
    while True:
        try:
            if renderer.awaiting_approval:
                prompt_label = HTML("\n<ansiyellow><b>Approve execution? (y/n):</b></ansiyellow>\n")
                toolbar_label = HTML("<b>Type 'y' or 'yes' to approve | Any other input to cancel/reject | /quit or /exit to exit</b>")
            else:
                prompt_label = HTML("\n<ansigreen><b>You:</b></ansigreen>\n")
                toolbar_label = HTML("<b>[Enter] to send | [Esc] -> [Enter] for new line | /quit or /exit to exit</b>")
                
            prompt = session.prompt(
                prompt_label,
                multiline=True,
                key_bindings=bindings,
                bottom_toolbar=toolbar_label,
                style=Style.from_dict({'bottom-toolbar': 'default'})
            )
            
            if prompt.strip() in ['/quit', '/exit']:
                break
            if not prompt.strip():
                continue
                
            console.print("\n[bold blue]Assistant:[/bold blue]")
            
            renderer.full_response = ''
            if renderer.awaiting_approval:
                renderer.awaiting_approval = False
                approved = prompt.strip().lower() in ['y', 'yes']
                agent.respond_to_approval(approved)
            else:
                agent.send_message(prompt)
                
        except (KeyboardInterrupt, EOFError):
            break
            
    console.print("\n[bold blue]Goodbye![/bold blue]")

if __name__ == '__main__':
    app()
