"""MCP server setup.

This module wires MCP servers into the unified AgentHub provider system.
"""

import logging

from app.agent.registry import AgentHub

logger = logging.getLogger(__name__)


async def register_mcp_servers() -> None:
    """注册所有 MCP 服务器。"""
    await _register_configured_mcp_servers()
    await _register_custom_mcp_servers()


async def _register_custom_mcp_servers() -> None:
    """注册所有用户自定义 MCP 服务器。"""
    from app.services.mcp_service import mcp_service

    try:
        await mcp_service.register_all()
    except Exception as e:
        logger.warning(f"Failed to register custom MCP servers: {e}")


async def _register_configured_mcp_servers() -> None:
    """注册 config.yml 中配置的全局 MCP 服务器。"""
    from app.config import settings
    from app.agent.tools.providers.mcp import MCPToolProvider

    mcp_provider: MCPToolProvider = AgentHub.get_provider("mcp")  # type: ignore

    for server in settings.mcp.servers.values():
        if not server.enabled:
            logger.info("MCP server %s is disabled, skipping registration", server.name)
            continue

        headers = None
        if server.auth_header_name and server.auth_token:
            headers = {server.auth_header_name: server.auth_token}

        mcp_provider.register_server(
            server.name,
            server.endpoint,
            headers,
            scope="global",
            display_name=server.name,
        )

        try:
            loaded = await mcp_provider.load_server_tools(server.name)
            logger.info("Loaded %s tools from MCP server %s", len(loaded), server.name)
        except Exception as e:
            logger.error("Failed to load MCP server %s: %s", server.name, e)
