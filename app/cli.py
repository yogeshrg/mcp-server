"""CLI for MCP Server."""

import asyncio
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from app.core.config import settings
from app.services.mcp_service import mcp_service

app = typer.Typer(help="MCP Server CLI")
console = Console()


@app.command()
def serve(
    transport: str = typer.Option("stdio", "--transport", "-t", help="Transport type: stdio, sse, streamable-http"),
    host: str = typer.Option("0.0.0.0", "--host", help="Host for HTTP transports"),
    port: int = typer.Option(8001, "--port", "-p", help="Port for HTTP transports"),
):
    """Start the MCP server."""
    asyncio.run(_serve_async(transport, host, port))


async def _serve_async(transport: str, host: str, port: int):
    console.print(Panel.fit(f"[bold blue]{settings.app_name}[/bold blue] v{settings.app_version}"))
    console.print(f"Transport: [cyan]{transport}[/cyan]")
    if transport != "stdio":
        console.print(f"Host: [cyan]{host}:{port}[/cyan]")
    console.print()

    await mcp_service.initialize()

    console.print(f"Registered tools: [green]{len(mcp_service.get_tools())}[/green]")
    console.print(f"Registered resources: [green]{len(mcp_service.get_resources())}[/green]")
    console.print()

    try:
        if transport == "stdio":
            await mcp_service.run_stdio()
        elif transport == "sse":
            await mcp_service.run_sse(host, port)
        elif transport == "streamable-http":
            await mcp_service.run_streamable_http(host, port)
        else:
            console.print(f"[red]Unknown transport: {transport}[/red]")
            return
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped[/yellow]")


@app.command()
def tools():
    """List all registered tools."""
    asyncio.run(_tools_async())


async def _tools_async():
    console.print(Panel.fit(f"[bold blue]{settings.app_name}[/bold blue] - Tools"))
    await mcp_service.initialize()

    tools = mcp_service.get_tools()
    if not tools:
        console.print("[yellow]No tools registered[/yellow]")
        return

    table = Table(title="Registered Tools")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("Input Schema")

    for tool in tools:
        schema_str = str(tool.inputSchema)[:80] + "..." if len(str(tool.inputSchema)) > 80 else str(tool.inputSchema)
        table.add_row(tool.name, tool.description, schema_str)

    console.print(table)


@app.command()
def resources():
    """List all registered resources."""
    asyncio.run(_resources_async())


async def _resources_async():
    console.print(Panel.fit(f"[bold blue]{settings.app_name}[/bold blue] - Resources"))
    await mcp_service.initialize()

    resources = mcp_service.get_resources()
    if not resources:
        console.print("[yellow]No resources registered[/yellow]")
        return

    table = Table(title="Registered Resources")
    table.add_column("URI", style="cyan")
    table.add_column("Name")
    table.add_column("Description")

    for resource in resources:
        table.add_row(resource.uri, resource.name, resource.description or "")

    console.print(table)


@app.command()
def health():
    """Check server health."""
    asyncio.run(_health_async())


async def _health_async():
    console.print(Panel.fit(f"[bold blue]{settings.app_name}[/bold blue] - Health Check"))
    await mcp_service.initialize()

    console.print(f"  Status: [green]healthy[/green]")
    console.print(f"  Tools: [cyan]{len(mcp_service.get_tools())}[/cyan]")
    console.print(f"  Resources: [cyan]{len(mcp_service.get_resources())}[/cyan]")
    console.print(f"  Resource Path: [cyan]{settings.resource_base_path}[/cyan]")


@app.command()
def test_tool(
    name: str = typer.Argument(..., help="Tool name"),
    args: str = typer.Option("{}", "--args", "-a", help="JSON arguments"),
):
    """Test a tool with given arguments."""
    asyncio.run(_test_tool_async(name, args))


async def _test_tool_async(name: str, args: str):
    console.print(Panel.fit(f"[bold blue]{settings.app_name}[/bold blue] - Test Tool"))
    await mcp_service.initialize()

    import json
    try:
        arguments = json.loads(args)
    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid JSON: {e}[/red]")
        return

    if name not in mcp_service._tool_handlers:
        console.print(f"[red]Tool not found: {name}[/red]")
        return

    handler = mcp_service._tool_handlers[name]
    try:
        console.print(f"Calling [cyan]{name}[/cyan] with args: {arguments}")
        result = await handler(arguments)
        console.print(f"[green]Result:[/green] {json.dumps(result, indent=2, default=str)}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    app()