"""MCP Server service with tools and resources."""

import asyncio
import base64
import json
import logging
import time
from pathlib import Path
from typing import Any

import aiofiles
import uvicorn
from mcp import types
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http import StreamableHTTPServerTransport
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from app.core.config import settings

logger = logging.getLogger(__name__)


class MCPService:
    """MCP Server service managing tools and resources."""

    def __init__(self) -> None:
        self.server = Server(settings.server_name)
        self._tools: dict[str, types.Tool] = {}
        self._resources: dict[str, types.Resource] = {}
        self._tool_handlers: dict[str, callable] = {}
        self._resource_handlers: dict[str, callable] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the MCP server with tools and resources."""
        if self._initialized:
            return

        logger.info("Initializing MCP server...")

        # Register built-in tools
        await self._register_builtin_tools()

        # Register built-in resources
        await self._register_builtin_resources()

        # Set up request handlers
        self._setup_handlers()

        self._initialized = True
        logger.info(f"MCP server initialized with {len(self._tools)} tools and {len(self._resources)} resources")

    async def _register_builtin_tools(self) -> None:
        """Register built-in tools."""

        # File system tools
        self.register_tool(
            types.Tool(
                name="read_file",
                description="Read a file from the resource directory",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path to file"},
                    },
                    "required": ["path"],
                },
            ),
            self._tool_read_file,
        )

        self.register_tool(
            types.Tool(
                name="write_file",
                description="Write a file to the resource directory",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path to file"},
                        "content": {"type": "string", "description": "File content"},
                    },
                    "required": ["path", "content"],
                },
            ),
            self._tool_write_file,
        )

        self.register_tool(
            types.Tool(
                name="list_files",
                description="List files in the resource directory",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path (default: root)"},
                        "recursive": {"type": "boolean", "default": False},
                    },
                },
            ),
            self._tool_list_files,
        )

        # Web tools
        self.register_tool(
            types.Tool(
                name="http_get",
                description="Make an HTTP GET request",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to fetch"},
                        "headers": {"type": "object", "description": "Optional headers"},
                        "timeout": {"type": "number", "default": 30},
                    },
                    "required": ["url"],
                },
            ),
            self._tool_http_get,
        )

        self.register_tool(
            types.Tool(
                name="http_post",
                description="Make an HTTP POST request",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to post to"},
                        "json": {"type": "object", "description": "JSON body"},
                        "headers": {"type": "object", "description": "Optional headers"},
                        "timeout": {"type": "number", "default": 30},
                    },
                    "required": ["url"],
                },
            ),
            self._tool_http_post,
        )

        # Utility tools
        self.register_tool(
            types.Tool(
                name="execute_command",
                description="Execute a shell command (restricted)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Command to execute"},
                        "timeout": {"type": "number", "default": 30},
                    },
                    "required": ["command"],
                },
            ),
            self._tool_execute_command,
        )

        self.register_tool(
            types.Tool(
                name="current_time",
                description="Get current timestamp",
                inputSchema={"type": "object", "properties": {}},
            ),
            self._tool_current_time,
        )

        self.register_tool(
            types.Tool(
                name="generate_uuid",
                description="Generate a random UUID",
                inputSchema={"type": "object", "properties": {}},
            ),
            self._tool_generate_uuid,
        )

        # JSON tools
        self.register_tool(
            types.Tool(
                name="json_parse",
                description="Parse JSON string",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "json_string": {"type": "string", "description": "JSON string to parse"},
                    },
                    "required": ["json_string"],
                },
            ),
            self._tool_json_parse,
        )

        self.register_tool(
            types.Tool(
                name="json_query",
                description="Query JSON with JSONPath",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "json_data": {"type": "object", "description": "JSON object"},
                        "path": {"type": "string", "description": "JSONPath expression"},
                    },
                    "required": ["json_data", "path"],
                },
            ),
            self._tool_json_query,
        )

    async def _register_builtin_resources(self) -> None:
        """Register built-in resources."""
        # Ensure resource directory exists
        settings.resource_base_path.mkdir(parents=True, exist_ok=True)

        # Register resource directory as a resource
        self.register_resource(
            types.Resource(
                uri="file:///resources",
                name="Resource Directory",
                description="Access to resource files",
                mimeType="application/json",
            ),
            self._resource_list_directory,
        )

    def _setup_handlers(self) -> None:
        """Set up MCP request handlers."""
        from mcp import types as mcp_types

        async def list_tools(request: mcp_types.ListToolsRequest) -> mcp_types.ListToolsResult:
            return mcp_types.ListToolsResult(tools=list(self._tools.values()))

        async def call_tool(request: mcp_types.CallToolRequest) -> mcp_types.CallToolResult:
            name = request.params.name
            arguments = request.params.arguments or {}

            if name not in self._tool_handlers:
                return mcp_types.CallToolResult(
                    content=[mcp_types.TextContent(type="text", text=f"Unknown tool: {name}")],
                    isError=True,
                )

            handler = self._tool_handlers[name]
            try:
                result = await handler(arguments)
                return mcp_types.CallToolResult(
                    content=[mcp_types.TextContent(type="text", text=json.dumps(result, default=str))],
                    isError=False,
                )
            except Exception as e:
                logger.exception(f"Tool {name} failed")
                return mcp_types.CallToolResult(
                    content=[mcp_types.TextContent(type="text", text=f"Error: {str(e)}")],
                    isError=True,
                )

        async def list_resources(request: mcp_types.ListResourcesRequest) -> mcp_types.ListResourcesResult:
            return mcp_types.ListResourcesResult(resources=list(self._resources.values()))

        async def read_resource(request: mcp_types.ReadResourceRequest) -> mcp_types.ReadResourceResult:
            uri = request.params.uri

            if uri not in self._resource_handlers:
                # Try to read as file
                if uri.startswith("file://"):
                    content = await self._read_file_resource(uri)
                    return mcp_types.ReadResourceResult(
                        contents=[mcp_types.TextResourceContents(uri=uri, mimeType="text/plain", text=content)]
                    )
                raise ValueError(f"Unknown resource: {uri}")

            handler = self._resource_handlers[uri]
            content = await handler(uri)

            if isinstance(content, str):
                return mcp_types.ReadResourceResult(
                    contents=[mcp_types.TextResourceContents(uri=uri, mimeType="text/plain", text=content)]
                )
            else:
                return mcp_types.ReadResourceResult(
                    contents=[mcp_types.BlobResourceContents(uri=uri, mimeType="application/octet-stream", blob=content)]
                )

        self.server.add_request_handler("tools/list", mcp_types.ListToolsRequest, list_tools)
        self.server.add_request_handler("tools/call", mcp_types.CallToolRequest, call_tool)
        self.server.add_request_handler("resources/list", mcp_types.ListResourcesRequest, list_resources)
        self.server.add_request_handler("resources/read", mcp_types.ReadResourceRequest, read_resource)

    def register_tool(self, tool: types.Tool, handler: callable) -> None:
        """Register a tool with its handler."""
        self._tools[tool.name] = tool
        self._tool_handlers[tool.name] = handler

    def register_resource(self, resource: types.Resource, handler: callable) -> None:
        """Register a resource with its handler."""
        self._resources[resource.uri] = resource
        self._resource_handlers[resource.uri] = handler

    # Tool handlers
    async def _tool_read_file(self, args: dict[str, Any]) -> dict[str, Any]:
        path = args["path"]
        file_path = settings.resource_base_path / path
        if not file_path.exists():
            return {"error": "File not found", "path": path}
        if not file_path.is_file():
            return {"error": "Not a file", "path": path}

        # Check size
        if file_path.stat().st_size > settings.max_resource_size:
            return {"error": "File too large", "path": path}

        async with aiofiles.open(file_path, "r") as f:
            content = await f.read()
        return {"path": path, "content": content}

    async def _tool_write_file(self, args: dict[str, Any]) -> dict[str, Any]:
        path = args["path"]
        content = args["content"]
        file_path = settings.resource_base_path / path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(file_path, "w") as f:
            await f.write(content)
        return {"path": path, "written": len(content)}

    async def _tool_list_files(self, args: dict[str, Any]) -> dict[str, Any]:
        path = args.get("path", ".")
        recursive = args.get("recursive", False)
        dir_path = settings.resource_base_path / path

        if not dir_path.exists():
            return {"error": "Directory not found", "path": path}

        files = []
        if recursive:
            for f in dir_path.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(settings.resource_base_path)
                    files.append({"path": str(rel), "size": f.stat().st_size})
        else:
            for f in dir_path.iterdir():
                if f.is_file():
                    rel = f.relative_to(settings.resource_base_path)
                    files.append({"path": str(rel), "size": f.stat().st_size})

        return {"path": path, "files": files}

    async def _tool_http_get(self, args: dict[str, Any]) -> dict[str, Any]:
        import httpx
        url = args["url"]
        headers = args.get("headers", {})
        timeout = args.get("timeout", 30)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "content": response.text,
            }

    async def _tool_http_post(self, args: dict[str, Any]) -> dict[str, Any]:
        import httpx
        url = args["url"]
        json_body = args.get("json", {})
        headers = args.get("headers", {})
        timeout = args.get("timeout", 30)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=json_body, headers=headers)
            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "content": response.text,
            }

    async def _tool_execute_command(self, args: dict[str, Any]) -> dict[str, Any]:
        import subprocess
        command = args["command"]
        timeout = args.get("timeout", 30)

        # Security: Only allow safe commands
        allowed_commands = ["ls", "cat", "head", "tail", "grep", "find", "wc", "echo", "date", "whoami"]
        cmd_parts = command.split()
        if cmd_parts[0] not in allowed_commands:
            return {"error": f"Command not allowed: {cmd_parts[0]}"}

        try:
            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=settings.resource_base_path,
            )
            return {
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out", "command": command}

    async def _tool_current_time(self, args: dict[str, Any]) -> dict[str, Any]:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        return {
            "iso": now.isoformat(),
            "timestamp": now.timestamp(),
            "timezone": "UTC",
        }

    async def _tool_generate_uuid(self, args: dict[str, Any]) -> dict[str, Any]:
        import uuid
        return {"uuid": str(uuid.uuid4())}

    async def _tool_json_parse(self, args: dict[str, Any]) -> dict[str, Any]:
        json_string = args["json_string"]
        try:
            return {"parsed": json.loads(json_string)}
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON: {str(e)}"}

    async def _tool_json_query(self, args: dict[str, Any]) -> dict[str, Any]:
        json_data = args["json_data"]
        path = args["path"]

        # Simple JSONPath implementation (supports basic .key and [index])
        def query(obj: Any, path: str) -> Any:
            if path == "$" or path == "":
                return obj
            
            # Split path into steps
            parts = path.lstrip("$.").split(".")
            current = obj
            for part in parts:
                # Check if part is an array index (numeric)
                if part.isdigit():
                    idx = int(part)
                    if isinstance(current, list) and 0 <= idx < len(current):
                        current = current[idx]
                    else:
                        return {"error": f"Index {idx} out of bounds or not a list"}
                elif "[" in part and "]" in part:
                    # Handle key[index] format
                    import re
                    key = part[: part.index("[")]
                    indices = re.findall(r'\[(\d+)\]', part)
                    if key:
                        if isinstance(current, dict):
                            current = current.get(key, {})
                        else:
                            return {"error": f"Expected dict for key '{key}', got {type(current).__name__}"}
                    for idx_str in indices:
                        idx = int(idx_str)
                        if isinstance(current, list) and 0 <= idx < len(current):
                            current = current[idx]
                        else:
                            return {"error": f"Index {idx} out of bounds or not a list"}
                else:
                    # Object key
                    if isinstance(current, dict):
                        current = current.get(part, {})
                    else:
                        return {"error": f"Expected dict for key '{part}', got {type(current).__name__}"}
            return current

        try:
            result = query(json_data, path)
            if isinstance(result, dict) and "error" in result:
                return result
            return {"result": result}
        except Exception as e:
            return {"error": f"Query failed: {str(e)}"}

    # Resource handlers
    async def _resource_list_directory(self, uri: str) -> str:
        files = []
        for f in settings.resource_base_path.rglob("*"):
            if f.is_file():
                rel = f.relative_to(settings.resource_base_path)
                files.append({"path": str(rel), "size": f.stat().st_size})
        return json.dumps({"files": files}, indent=2)

    async def _read_file_resource(self, uri: str) -> str:
        # file:///path/to/file
        path = uri[7:]  # Remove file://
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = settings.resource_base_path / file_path

        if not file_path.exists():
            raise ValueError(f"File not found: {path}")

        async with aiofiles.open(file_path, "rb") as f:
            content = await f.read()

        # Try to decode as text
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            # Return base64 for binary
            return base64.b64encode(content).decode("ascii")

    async def run_stdio(self) -> None:
        """Run server with stdio transport."""
        logger.info("Starting MCP server with stdio transport...")
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name=settings.server_name,
                    server_version=settings.server_version,
                    capabilities=self.server.get_capabilities(
                        notification_options=None,
                        experimental_capabilities=None,
                    ),
                ),
            )

    async def run_sse(self, host: str = "0.0.0.0", port: int = 8001) -> None:
        """Run server with SSE transport."""
        logger.info(f"Starting MCP server with SSE transport on {host}:{port}...")

        sse_transport = SseServerTransport("/messages/")

        async def handle_sse(request):
            async with sse_transport.connect_sse(
                request.scope, request.receive, request._send
            ) as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    InitializationOptions(
                        server_name=settings.server_name,
                        server_version=settings.server_version,
                        capabilities=self.server.get_capabilities(
                            notification_options=None,
                            experimental_capabilities=None,
                        ),
                    ),
                )

        async def handle_messages(request):
            await sse_transport.handle_post_message(
                request.scope, request.receive, request._send
            )

        starlette_app = Starlette(
            routes=[
                Route("/sse", handle_sse),
                Mount("/messages/", app=handle_messages),
            ]
        )

        config = uvicorn.Config(starlette_app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()

    async def run_streamable_http(self, host: str = "0.0.0.0", port: int = 8001) -> None:
        """Run server with Streamable HTTP transport."""
        logger.info(f"Starting MCP server with Streamable HTTP on {host}:{port}...")

        transport = StreamableHTTPServerTransport()

        async def handle_request(scope, receive, send):
            await transport.handle_request(scope, receive, send, self.server)

        starlette_app = Starlette(routes=[Mount("/mcp", app=handle_request)])

        config = uvicorn.Config(starlette_app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()

    def get_tools(self) -> list[types.Tool]:
        """Get list of registered tools."""
        return list(self._tools.values())

    def get_resources(self) -> list[types.Resource]:
        """Get list of registered resources."""
        return list(self._resources.values())


# Global service instance
mcp_service = MCPService()