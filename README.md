# MCP Server

A production-ready **Model Context Protocol (MCP)** server built with **FastMCP** and **FastAPI**. Provides a standardized interface for LLMs to access tools and resources.

## Features

- 🔧 **Built-in Tools** — File system, HTTP, shell commands, JSON processing, utilities
- 📚 **Resources** — File-based resource access with mime type detection
- 🚀 **Multiple Transports** — stdio, SSE, and Streamable HTTP
- 🔐 **Authentication** — Optional API key authentication
- ⚡ **Rate Limiting** — Configurable request rate limiting
- 🐳 **Docker Ready** — Containerized deployment
- 🧪 **Tested** — Comprehensive test suite

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (optional)

### Local Development

```bash
cd mcp-server

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Copy environment config
cp .env.example .env

# Run with stdio transport (for MCP clients like Claude Desktop)
python -m app.cli serve --transport stdio

# Or run with HTTP transport
python -m app.cli serve --transport streamable-http --port 8001
```

### Docker Deployment

```bash
cd docker
docker-compose up -d

# Access API at http://localhost:8001/docs
```

### MCP Client Configuration

For **Claude Desktop** (stdio transport):

```json
{
  "mcpServers": {
    "mcp-server": {
      "command": "python",
      "args": ["-m", "app.cli", "serve", "--transport", "stdio"],
      "cwd": "/path/to/mcp-server"
    }
  }
}
```

For **HTTP-based clients**:

```json
{
  "mcpServers": {
    "mcp-server": {
      "url": "http://localhost:8001/mcp"
    }
  }
}
```

## Built-in Tools

| Tool | Description |
|------|-------------|
| `read_file` | Read a file from resource directory |
| `write_file` | Write a file to resource directory |
| `list_files` | List files in resource directory |
| `http_get` | Make HTTP GET request |
| `http_post` | Make HTTP POST request |
| `execute_command` | Execute shell command (restricted) |
| `current_time` | Get current timestamp |
| `generate_uuid` | Generate random UUID |
| `json_parse` | Parse JSON string |
| `json_query` | Query JSON with path |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/tools` | List all tools |
| POST | `/api/v1/tools/call` | Call a tool |
| GET | `/api/v1/resources` | List all resources |
| POST | `/api/v1/resources/read` | Read a resource |

### Example: Call a Tool

```bash
curl -X POST http://localhost:8001/api/v1/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name": "current_time", "arguments": {}}'
```

### Example: Read a Resource

```bash
curl -X POST http://localhost:8001/api/v1/resources/read \
  -H "Content-Type: application/json" \
  -d '{"uri": "file:///resources/test.txt"}'
```

## Configuration

Key settings in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `TRANSPORT` | `stdio` | Transport type: stdio, sse, streamable-http |
| `API_KEY_ENABLED` | `false` | Enable API key authentication |
| `RATE_LIMIT_ENABLED` | `true` | Enable rate limiting |
| `RESOURCE_BASE_PATH` | `./data/resources` | Base path for file resources |
| `TOOL_TIMEOUT` | `30.0` | Tool execution timeout (seconds) |

## Project Structure

```
mcp-server/
├── app/
│   ├── api/routes.py          # FastAPI routes
│   ├── cli.py                 # Typer CLI
│   ├── core/config.py         # Pydantic settings
│   ├── main.py                # FastAPI app entry
│   ├── models/schemas.py      # Pydantic models
│   └── services/mcp_service.py # MCP server logic
├── docker/
│   ├── Dockerfile             # Multi-stage build
│   └── docker-compose.yml     # Full stack
├── tests/                     # Pytest suite
├── pyproject.toml             # Project config
└── .env.example               # Environment template
```

## Adding Custom Tools

```python
from app.services.mcp_service import mcp_service
from mcp import types

# Define tool schema
tool = types.Tool(
    name="my_tool",
    description="My custom tool",
    inputSchema={
        "type": "object",
        "properties": {
            "param": {"type": "string"},
        },
        "required": ["param"],
    },
)

# Define handler
async def my_handler(args: dict) -> dict:
    param = args["param"]
    return {"result": f"Processed: {param}"}

# Register
mcp_service.register_tool(tool, my_handler)
```

## Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=app --cov-report=html
```

## License

MIT License

## Author

Yogesh Gaikwad — Yogesh.r.gaikwad@gmail.com