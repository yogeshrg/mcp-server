"""MCP Server configuration."""

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "MCP Server"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    # Server
    host: str = "0.0.0.0"
    port: int = 8001
    transport: str = "stdio"  # stdio, sse, or streamable-http

    # MCP
    server_name: str = "mcp-server"
    server_version: str = "0.1.0"

    # Auth
    api_key_enabled: bool = False
    api_keys: list[str] = Field(default=[])

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100
    rate_limit_window: int = 60

    # Tools
    tool_timeout: float = 30.0
    max_tool_calls_per_request: int = 10

    # Resources
    resource_base_path: Path = Field(default=Path("./data/resources"))
    max_resource_size: int = 10 * 1024 * 1024  # 10MB

    # Logging
    log_file: Path | None = None


settings = Settings()