"""MCP tool provider."""

from __future__ import annotations

import logging
from typing import Optional

from app.agent.tools.base import BaseTool, MCPTool
from app.agent.tools.mcp.client import MCPClient

logger = logging.getLogger(__name__)


class MCPToolProvider:
    name = "mcp"

    def __init__(self):
        self._tools: dict[str, MCPTool] = {}
        #保存 MCP 服务器名称到 endpoint URL 的映射
        self._servers: dict[str, str] = {}
        #保存每个 MCP 服务器需要携带的请求头，通常用于鉴权。
        #当创建 MCPClient 或 MCPTool 时，这些 headers 会传进去，后续请求 MCP 服务器时自动带上。
        self._server_headers: dict[str, dict[str, str]] = {}
        #缓存每个服务器对应的 MCPClient 实例，避免每次加载工具都重新创建客户端。
        self._clients: dict[str, MCPClient] = {}
        #最近一次加载失败的诊断信息
        self._last_load_errors: dict[str, str] = {}
        #保存 MCP 服务器归属信息。未记录的服务器按全局服务器处理，兼容旧调用。
        self._server_meta: dict[str, dict[str, Optional[str]]] = {}
        #保存工具名到 MCP 服务器内部名称的映射，用于按用户过滤。
        self._tool_servers: dict[str, str] = {}

    # ----- server management -----

    def register_server(
        self,
        name: str,
        endpoint: str,
        headers: Optional[dict[str, str]] = None,
        *,
        scope: str = "global",
        user_id: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> None:
        if scope not in {"global", "user"}:
            raise ValueError("MCP server scope must be 'global' or 'user'")
        if scope == "user" and not user_id:
            raise ValueError("user scoped MCP server requires user_id")

        self._servers[name] = endpoint
        self._server_meta[name] = {
            "scope": scope,
            "user_id": user_id,
            "display_name": display_name or name,
        }
        if headers:
            self._server_headers[name] = headers
        elif name in self._server_headers:
            del self._server_headers[name]
        if name in self._clients:
            del self._clients[name]

    def list_servers(self) -> list[str]:
        return list(self._servers.keys())

    def get_last_load_error(self, name: str) -> Optional[str]:
        return self._last_load_errors.get(name)

    def _get_client(self, name: str) -> Optional[MCPClient]:
        endpoint = self._servers.get(name)
        if not endpoint:
            return None
        if name not in self._clients:
            self._clients[name] = MCPClient(
                endpoint,
                headers=self._server_headers.get(name),
            )
        return self._clients[name]

    def _remove_server_tools(self, name: str) -> None:
        prefix = f"mcp_{name}_"
        for tool_name in list(self._tools.keys()):
            if tool_name.startswith(prefix):
                del self._tools[tool_name]
                self._tool_servers.pop(tool_name, None)

    def _is_server_visible(self, name: str, user_id: Optional[str]) -> bool:
        meta = self._server_meta.get(name)
        if not meta:
            return True
        if meta.get("scope") == "global":
            return True
        return bool(user_id and meta.get("user_id") == user_id)

    def _is_tool_visible(self, name: str, user_id: Optional[str]) -> bool:
        server_name = self._tool_servers.get(name)
        if not server_name:
            return True
        return self._is_server_visible(server_name, user_id)

    async def load_server_tools(self, name: str) -> list[MCPTool]:
        client = self._get_client(name)
        if not client:
            logger.warning(f"MCP server not registered: {name}")
            return []

        try:
            self._last_load_errors.pop(name, None)
            self._remove_server_tools(name)
            await client.initialize()
            tools = await client.list_tools()
            loaded: list[MCPTool] = []

            for tool_info in tools:
                tool_name = tool_info.get("name", "")
                if not tool_name:
                    continue
                full_tool_name = f"mcp_{name}_{tool_name}"

                mcp_tool = MCPTool(
                    name=full_tool_name,
                    description=tool_info.get("description", ""),
                    mcp_endpoint=self._servers[name],
                    mcp_tool_name=tool_name,
                    mcp_headers=self._server_headers.get(name),
                    parameters=tool_info.get("inputSchema", {}),
                )

                self._tools[mcp_tool.name] = mcp_tool
                self._tool_servers[mcp_tool.name] = name
                loaded.append(mcp_tool)

            logger.info(f"Loaded {len(loaded)} tools from MCP server: {name}")
            return loaded
        except Exception as e:
            self._last_load_errors[name] = str(e)
            logger.exception(f"Failed to load tools from MCP server {name}: {e}")
            return []

    def unregister_server(self, name: str) -> None:
        self._remove_server_tools(name)
        if name in self._servers:
            del self._servers[name]
        if name in self._server_headers:
            del self._server_headers[name]
        if name in self._clients:
            del self._clients[name]
        if name in self._last_load_errors:
            del self._last_load_errors[name]
        if name in self._server_meta:
            del self._server_meta[name]

    # ----- ToolProvider surface -----

    def register_tool(self, tool: BaseTool) -> None:
        if not isinstance(tool, MCPTool):
            raise TypeError("MCPToolProvider only accepts MCPTool")
        self._tools[tool.name] = tool

    def unregister_tool(self, name: str) -> bool:
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get_tool(
        self, name: str, user_id: Optional[str] = None
    ) -> Optional[BaseTool]:
        if not self._is_tool_visible(name, user_id):
            return None
        return self._tools.get(name)

    def list_tool_names(self, user_id: Optional[str] = None) -> list[str]:
        return [
            name for name in self._tools.keys() if self._is_tool_visible(name, user_id)
        ]

    def get_tool_schema(
        self, name: str, user_id: Optional[str] = None
    ) -> Optional[dict]:
        if not self._is_tool_visible(name, user_id):
            return None
        tool = self._tools.get(name)
        if not tool:
            return None
        return tool.to_openai_schema()

    def get_tool_schemas(
        self, names: Optional[list[str]] = None, user_id: Optional[str] = None
    ) -> list[dict]:
        if names is None:
            return [
                t.to_openai_schema()
                for name, t in self._tools.items()
                if self._is_tool_visible(name, user_id)
            ]
        return [
            self._tools[n].to_openai_schema()
            for n in names
            if n in self._tools and self._is_tool_visible(n, user_id)
        ]

    def list_servers_with_tools(self, user_id: Optional[str] = None) -> list[dict]:
        """Return tools grouped by MCP server.

        Returns:
            List of server dicts, each containing:
            - name: server name
            - type: "mcp"
            - tools: list of tool info dicts
        """
        servers: dict[str, dict] = {}

        for t in self._tools.values():
            server_key = self._tool_servers.get(t.name)
            if server_key and not self._is_server_visible(server_key, user_id):
                continue

            meta = self._server_meta.get(server_key or "")
            server_id = server_key or "unknown"
            server_name = (
                meta.get("display_name")
                if meta and meta.get("display_name")
                else server_id
            )

            if server_id not in servers:
                servers[server_id] = {
                    "name": server_name,
                    "type": "mcp",
                    "tools": [],
                }

            servers[server_id]["tools"].append(
                {
                    "name": t.name,
                    "description": t.description,
                }
            )

        return list(servers.values())
