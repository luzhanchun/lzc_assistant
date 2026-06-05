# app/config/mcp_config.py
"""MCP (Model Context Protocol) configuration for CookHero."""

import re
from typing import Optional

from pydantic import BaseModel, Field, model_validator


NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{2,64}$")


def validate_mcp_name(name: str) -> None:
    """Validate an MCP server name."""
    if not NAME_PATTERN.match(name):
        raise ValueError("MCP 名称需为 2-64 位，支持字母、数字、_、-")


def validate_mcp_endpoint(endpoint: str) -> None:
    """Validate an MCP server endpoint."""
    if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
        raise ValueError("Endpoint 需要以 http:// 或 https:// 开头")
    if len(endpoint) > 512:
        raise ValueError("Endpoint 过长")


def validate_mcp_auth(
    auth_header_name: str | None, auth_token: str | None
) -> None:
    """Validate MCP auth header/token fields."""
    if not auth_header_name and not auth_token:
        return
    if not auth_header_name or not auth_token:
        raise ValueError("Header 名称和 Token 需要同时填写")
    if len(auth_header_name) > 128:
        raise ValueError("Header 名称过长")
    if "\n" in auth_header_name or "\r" in auth_header_name:
        raise ValueError("Header 名称不合法")


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    name: str
    endpoint: str
    auth_header_name: Optional[str] = None
    auth_token: Optional[str] = None
    enabled: bool = True

    @model_validator(mode="after")
    def validate_server(self) -> "MCPServerConfig":
        validate_mcp_name(self.name)
        validate_mcp_endpoint(self.endpoint)
        validate_mcp_auth(self.auth_header_name, self.auth_token)
        return self


class MCPConfig(BaseModel):
    """
    Configuration for MCP (Model Context Protocol) integration.
    """

    servers: dict[str, MCPServerConfig] = Field(default_factory=dict)
