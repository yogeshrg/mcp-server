"""Tests for MCP Server."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from app.core.config import settings
from app.models.schemas import HealthResponse, ToolCall, TransportType
from app.services.mcp_service import MCPService


class TestConfig:
    """Test configuration loading."""

    def test_settings_defaults(self):
        """Test default settings values."""
        assert settings.app_name == "MCP Server"
        assert settings.transport == "stdio"
        assert settings.server_name == "mcp-server"
        assert settings.tool_timeout == 30.0


class TestSchemas:
    """Test Pydantic schemas."""

    def test_health_response(self):
        """Test health response model."""
        health = HealthResponse(
            status="healthy",
            version="0.1.0",
            transport=TransportType.STDIO,
            tools_registered=5,
            resources_registered=2,
        )
        assert health.status == "healthy"
        assert health.tools_registered == 5

    def test_tool_call(self):
        """Test tool call model."""
        call = ToolCall(name="test_tool", arguments={"key": "value"}, request_id="123")
        assert call.name == "test_tool"
        assert call.arguments == {"key": "value"}


class TestMCPService:
    """Test MCP service."""

    @pytest.fixture
    def mcp_service(self):
        """Create MCP service instance."""
        return MCPService()

    @pytest.mark.asyncio
    async def test_initialize_registers_tools(self, mcp_service, tmp_path):
        """Test initialization registers built-in tools."""
        with patch.object(settings, "resource_base_path", tmp_path / "resources"):
            await mcp_service.initialize()

            assert mcp_service._initialized
            tools = mcp_service.get_tools()
            tool_names = [t.name for t in tools]

            # Check built-in tools
            assert "read_file" in tool_names
            assert "write_file" in tool_names
            assert "list_files" in tool_names
            assert "http_get" in tool_names
            assert "http_post" in tool_names
            assert "execute_command" in tool_names
            assert "current_time" in tool_names
            assert "generate_uuid" in tool_names
            assert "json_parse" in tool_names
            assert "json_query" in tool_names

    @pytest.mark.asyncio
    async def test_tool_read_file(self, mcp_service, tmp_path):
        """Test read_file tool."""
        resource_dir = tmp_path / "resources"
        resource_dir.mkdir()
        test_file = resource_dir / "test.txt"
        test_file.write_text("Hello, World!")

        with patch.object(settings, "resource_base_path", resource_dir):
            await mcp_service.initialize()

            handler = mcp_service._tool_handlers["read_file"]
            result = await handler({"path": "test.txt"})

            assert result["content"] == "Hello, World!"
            assert result["path"] == "test.txt"

    @pytest.mark.asyncio
    async def test_tool_write_file(self, mcp_service, tmp_path):
        """Test write_file tool."""
        resource_dir = tmp_path / "resources"
        with patch.object(settings, "resource_base_path", resource_dir):
            await mcp_service.initialize()

            handler = mcp_service._tool_handlers["write_file"]
            result = await handler({"path": "new.txt", "content": "New content"})

            assert result["written"] == 11  # "New content" is 11 chars
            assert (resource_dir / "new.txt").read_text() == "New content"

    @pytest.mark.asyncio
    async def test_tool_list_files(self, mcp_service, tmp_path):
        """Test list_files tool."""
        resource_dir = tmp_path / "resources"
        resource_dir.mkdir()
        (resource_dir / "file1.txt").write_text("1")
        (resource_dir / "file2.txt").write_text("2")
        subdir = resource_dir / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("3")

        with patch.object(settings, "resource_base_path", resource_dir):
            await mcp_service.initialize()

            handler = mcp_service._tool_handlers["list_files"]
            result = await handler({"path": ".", "recursive": True})

            assert len(result["files"]) == 3
            paths = [f["path"] for f in result["files"]]
            assert "file1.txt" in paths
            assert "file2.txt" in paths
            assert "subdir/file3.txt" in paths

    @pytest.mark.asyncio
    async def test_tool_current_time(self, mcp_service, tmp_path):
        """Test current_time tool."""
        with patch.object(settings, "resource_base_path", tmp_path / "resources"):
            await mcp_service.initialize()

            handler = mcp_service._tool_handlers["current_time"]
            result = await handler({})

            assert "iso" in result
            assert "timestamp" in result
            assert result["timezone"] == "UTC"

    @pytest.mark.asyncio
    async def test_tool_generate_uuid(self, mcp_service, tmp_path):
        """Test generate_uuid tool."""
        with patch.object(settings, "resource_base_path", tmp_path / "resources"):
            await mcp_service.initialize()

            handler = mcp_service._tool_handlers["generate_uuid"]
            result = await handler({})

            assert "uuid" in result
            # Validate UUID format
            import uuid
            uuid.UUID(result["uuid"])  # Will raise if invalid

    @pytest.mark.asyncio
    async def test_tool_json_parse(self, mcp_service, tmp_path):
        """Test json_parse tool."""
        with patch.object(settings, "resource_base_path", tmp_path / "resources"):
            await mcp_service.initialize()

            handler = mcp_service._tool_handlers["json_parse"]
            result = await handler({"json_string": '{"key": "value", "num": 42}'})

            assert "parsed" in result
            assert result["parsed"]["key"] == "value"
            assert result["parsed"]["num"] == 42

    @pytest.mark.asyncio
    async def test_tool_json_query(self, mcp_service, tmp_path):
        """Test json_query tool."""
        with patch.object(settings, "resource_base_path", tmp_path / "resources"):
            await mcp_service.initialize()

            handler = mcp_service._tool_handlers["json_query"]
            # Test with simple dot notation (our implementation)
            result = await handler({
                "json_data": {"users": [{"name": "Alice"}, {"name": "Bob"}]},
                "path": "users.0.name",
            })

            assert result["result"] == "Alice"

            # Test with nested object
            result2 = await handler({
                "json_data": {"user": {"name": "Bob", "age": 30}},
                "path": "user.name",
            })
            assert result2["result"] == "Bob"

    @pytest.mark.asyncio
    async def test_tool_http_get(self, mcp_service, tmp_path):
        """Test http_get tool (mocked)."""
        with patch.object(settings, "resource_base_path", tmp_path / "resources"):
            await mcp_service.initialize()

            handler = mcp_service._tool_handlers["http_get"]
            with patch("httpx.AsyncClient.get") as mock_get:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.headers = {"content-type": "application/json"}
                mock_response.text = '{"status": "ok"}'
                mock_get.return_value = mock_response

                result = await handler({"url": "https://api.example.com/test"})

                assert result["status_code"] == 200
                assert result["content"] == '{"status": "ok"}'


class TestAPIRoutes:
    """Test API routes."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "MCP Server"

    def test_health_endpoint(self, client):
        """Test health endpoint."""
        with patch("app.api.routes.mcp_service.get_tools", return_value=[]):
            with patch("app.api.routes.mcp_service.get_resources", return_value=[]):
                response = client.get("/api/v1/health")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "healthy"

    def test_list_tools_endpoint(self, client):
        """Test list tools endpoint."""
        with patch("app.api.routes.mcp_service.get_tools") as mock_tools:
            mock_tool = MagicMock()
            mock_tool.name = "test_tool"
            mock_tool.description = "Test tool"
            mock_tool.inputSchema = {"type": "object"}
            mock_tools.return_value = [mock_tool]

            response = client.get("/api/v1/tools")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["name"] == "test_tool"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])