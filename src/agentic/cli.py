"""
Command-line interface for the Agentic assistant.

Provides interactive CLI and one-shot command support.
"""

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

app = typer.Typer(
    name="agentic",
    help="Personal AI assistant with memory and task management",
    no_args_is_help=True,
)
console = Console()


def print_response(text: str) -> None:
    """Print assistant response with formatting."""
    console.print(Panel(
        Markdown(text),
        title="[bold blue]Assistant[/bold blue]",
        border_style="blue",
    ))


def print_user(text: str) -> None:
    """Print user input with formatting."""
    console.print(f"[bold green]You:[/bold green] {text}")


def print_error(text: str) -> None:
    """Print error message."""
    console.print(f"[bold red]Error:[/bold red] {text}")


@app.command()
def chat(
    message: Optional[str] = typer.Argument(
        None,
        help="Message to send (omit for interactive mode)",
    ),
    voice: bool = typer.Option(
        False,
        "--voice",
        "-v",
        help="Enable voice input/output",
    ),
    stream: bool = typer.Option(
        True,
        "--stream/--no-stream",
        "-s",
        help="Stream responses",
    ),
) -> None:
    """
    Chat with the assistant.
    
    Run without arguments for interactive mode:
        agentic chat
    
    Or provide a message directly:
        agentic chat "Set a reminder for tomorrow"
    """
    asyncio.run(_chat_async(message, voice, stream))


async def _chat_async(
    message: Optional[str],
    voice: bool,
    stream: bool,
) -> None:
    """Async chat implementation."""
    from agentic.app import Assistant
    
    console.print("[bold]Initializing assistant...[/bold]")
    
    async with Assistant(enable_voice=voice) as assistant:
        console.print("[green]Ready![/green] Type 'quit' to exit, 'help' for commands.\n")
        
        if message:
            # One-shot mode
            print_user(message)
            
            if stream:
                response_text = ""
                console.print("[bold blue]Assistant:[/bold blue] ", end="")
                async for chunk in await assistant.chat(message, stream=True):
                    console.print(chunk, end="")
                    response_text += chunk
                console.print()  # New line after streaming
            else:
                response = await assistant.chat(message)
                print_response(response)
        else:
            # Interactive mode
            await _interactive_loop(assistant, stream)


async def _interactive_loop(assistant, stream: bool) -> None:
    """Interactive chat loop."""
    while True:
        try:
            user_input = Prompt.ask("\n[bold green]You[/bold green]")
            
            if not user_input.strip():
                continue
            
            # Handle special commands
            cmd = user_input.lower().strip()
            
            if cmd in ("quit", "exit", "bye"):
                console.print("[yellow]Goodbye![/yellow]")
                break
            
            elif cmd == "help":
                _show_help()
                continue
            
            elif cmd == "new" or cmd == "clear":
                await assistant.new_session()
                console.print("[yellow]Started new session[/yellow]")
                continue
            
            elif cmd == "stats":
                stats = await assistant.get_stats()
                console.print(Panel(str(stats), title="Statistics"))
                continue
            
            elif cmd == "capabilities":
                console.print(assistant.get_capabilities())
                continue
            
            elif cmd.startswith("remember "):
                fact = user_input[9:].strip()
                result = await assistant.remember(fact)
                console.print(f"[green]{result}[/green]")
                continue
            
            elif cmd.startswith("recall "):
                query = user_input[7:].strip()
                results = await assistant.recall(query)
                if results:
                    console.print("[bold]Memories:[/bold]")
                    for i, memory in enumerate(results, 1):
                        console.print(f"  {i}. {memory}")
                else:
                    console.print("[yellow]No relevant memories found[/yellow]")
                continue
            
            # Regular chat
            if stream:
                console.print("[bold blue]Assistant:[/bold blue] ", end="")
                response = await assistant.chat(user_input, stream=True)
                async for chunk in response:
                    console.print(chunk, end="")
                console.print()
            else:
                response = await assistant.chat(user_input)
                print_response(response)
                
        except KeyboardInterrupt:
            console.print("\n[yellow]Use 'quit' to exit[/yellow]")
        except Exception as e:
            print_error(str(e))


def _show_help() -> None:
    """Show help information."""
    help_text = """
[bold]Available Commands:[/bold]

  [cyan]help[/cyan]          Show this help message
  [cyan]quit[/cyan], [cyan]exit[/cyan]   Exit the assistant
  [cyan]new[/cyan], [cyan]clear[/cyan]   Start a new session
  [cyan]stats[/cyan]         Show assistant statistics
  [cyan]capabilities[/cyan]  Show what I can do

[bold]Memory Commands:[/bold]

  [cyan]remember <fact>[/cyan]  Store a fact in memory
  [cyan]recall <query>[/cyan]   Search memories

[bold]Examples:[/bold]

  Set a reminder for tomorrow at 3pm
  Add "buy groceries" to my tasks
  Show my tasks
  Take a note: Meeting notes from today...
  Remember that my wife's birthday is March 15th
"""
    console.print(Panel(help_text, title="Help", border_style="cyan"))


@app.command()
def remember(
    fact: str = typer.Argument(..., help="The fact to remember"),
) -> None:
    """Store a fact in long-term memory."""
    asyncio.run(_remember_async(fact))


async def _remember_async(fact: str) -> None:
    """Async remember implementation."""
    from agentic.app import Assistant
    
    async with Assistant() as assistant:
        result = await assistant.remember(fact)
        console.print(f"[green]{result}[/green]")


@app.command()
def recall(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(5, "--limit", "-n", help="Max results"),
) -> None:
    """Search long-term memory."""
    asyncio.run(_recall_async(query, limit))


async def _recall_async(query: str, limit: int) -> None:
    """Async recall implementation."""
    from agentic.app import Assistant
    
    async with Assistant() as assistant:
        results = await assistant.recall(query, k=limit)
        
        if results:
            console.print("[bold]Memories:[/bold]")
            for i, memory in enumerate(results, 1):
                console.print(f"  {i}. {memory}")
        else:
            console.print("[yellow]No relevant memories found[/yellow]")


@app.command()
def version() -> None:
    """Show version information."""
    from agentic import __version__
    console.print(f"Agentic v{__version__}")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload"),
) -> None:
    """Start the API server."""
    try:
        import uvicorn
        
        console.print(f"[bold]Starting API server on {host}:{port}...[/bold]")
        uvicorn.run(
            "agentic.api.server:app",
            host=host,
            port=port,
            reload=reload,
        )
    except ImportError:
        print_error("FastAPI/Uvicorn not installed. Install with: pip install agentic[web]")


if __name__ == "__main__":
    app()
