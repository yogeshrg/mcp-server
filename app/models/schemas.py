"""Pydantic models for MCP server."""

from typing import Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class TransportType(str, Enum):
    """MCP transport types."""

    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable-http"


class ToolCall(BaseModel):
    """Tool call request."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ToolResult(BaseModel):
    """Tool call result."""

    name: str
    result: Any
    error: str | None = None
    request_id: str | None = None
    duration_ms: float = 0.0


class ResourceRequest(BaseModel):
    """Resource read request."""

    uri: str
    mime_type: str | None = None


class ResourceContent(BaseModel):
    """Resource content."""

    uri: str
    mime_type: str
    text: str | None = None
    blob: str | None = None  # base64 encoded


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    transport: TransportType
    tools_registered: int
    resources_registered: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    detail: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)