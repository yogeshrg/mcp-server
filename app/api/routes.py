"""API routes for MCP server management."""

import logging
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from typing import Any

from app.models.schemas import (
    ToolCall,
    ToolResult,
    ResourceRequest,
    ResourceContent,
    HealthResponse,
    ErrorResponse,
    TransportType,
)
from app.services.mcp_service import mcp_service
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


async def verify_api_key(request: Request) -> None:
    """Verify API key if enabled."""
    if not settings.api_key_enabled:
        return
    api_key = request.headers.get("X-API-Key")
    if api_key not in settings.api_keys:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version=settings.app_version,
        transport=TransportType(settings.transport),
        tools_registered=len(mcp_service.get_tools()),
        resources_registered=len(mcp_service.get_resources()),
    )


@router.get("/tools", response_model=list[dict[str, Any]])
async def list_tools() -> list[dict[str, Any]]:
    """List all registered tools."""
    tools = mcp_service.get_tools()
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.inputSchema,
        }
        for t in tools
    ]


@router.post("/tools/call", response_model=ToolResult)
async def call_tool(tool_call: ToolCall, _: None = Depends(verify_api_key)) -> ToolResult:
    """Call a tool."""
    import time
    start = time.perf_counter()

    if tool_call.name not in mcp_service._tool_handlers:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_call.name}")

    handler = mcp_service._tool_handlers[tool_call.name]
    try:
        result = await handler(tool_call.arguments)
        duration = (time.perf_counter() - start) * 1000
        return ToolResult(
            name=tool_call.name,
            result=result,
            request_id=tool_call.request_id,
            duration_ms=duration,
        )
    except Exception as e:
        duration = (time.perf_counter() - start) * 1000
        logger.exception(f"Tool {tool_call.name} failed")
        return ToolResult(
            name=tool_call.name,
            result=None,
            error=str(e),
            request_id=tool_call.request_id,
            duration_ms=duration,
        )


@router.get("/resources", response_model=list[dict[str, Any]])
async def list_resources() -> list[dict[str, Any]]:
    """List all registered resources."""
    resources = mcp_service.get_resources()
    return [
        {
            "uri": r.uri,
            "name": r.name,
            "description": r.description,
            "mime_type": r.mimeType,
        }
        for r in resources
    ]


@router.post("/resources/read", response_model=ResourceContent)
async def read_resource(request: ResourceRequest, _: None = Depends(verify_api_key)) -> ResourceContent:
    """Read a resource."""
    if request.uri not in mcp_service._resource_handlers:
        # Try file resource
        if request.uri.startswith("file://"):
            content = await mcp_service._read_file_resource(request.uri)
            return ResourceContent(
                uri=request.uri,
                mime_type=request.mime_type or "text/plain",
                text=content,
            )
        raise HTTPException(status_code=404, detail=f"Resource not found: {request.uri}")

    handler = mcp_service._resource_handlers[request.uri]
    content = await handler(request.uri)
    return ResourceContent(
        uri=request.uri,
        mime_type=request.mime_type or "text/plain",
        text=content if isinstance(content, str) else None,
        blob=content if isinstance(content, bytes) else None,
    )


@router.post("/tools/register")
async def register_tool(
    name: str,
    description: str,
    input_schema: dict[str, Any],
    handler_code: str,
    _: None = Depends(verify_api_key),
) -> dict[str, str]:
    """Register a dynamic tool (handler code is executed in sandbox)."""
    # This would require a sandboxed execution environment
    # For now, return not implemented
    raise HTTPException(status_code=501, detail="Dynamic tool registration not implemented")


@router.delete("/tools/{tool_name}")
async def unregister_tool(tool_name: str, _: None = Depends(verify_api_key)) -> dict[str, str]:
    """Unregister a tool."""
    if tool_name not in mcp_service._tools:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")

    del mcp_service._tools[tool_name]
    del mcp_service._tool_handlers[tool_name]
    return {"status": "unregistered", "tool": tool_name}