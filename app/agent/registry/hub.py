"""AgentHub: single entrypoint for Agent + Tool + Provider (MCP, custom).

Design goals:
- One import path for all registration/lookup APIs.
- Providers are first-class: builtin, mcp, and future user-defined.
- No backwards compatibility layer.

Public API intentionally mirrors what the rest of the codebase needs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import TYPE_CHECKING, Optional, Protocol, Type, runtime_checkable

from app.agent.types import AgentConfig, AgentToolBinding
from app.agent.tools.base import BaseTool, ToolExecutor

logger = logging.getLogger(__name__)


@runtime_checkable
class ToolProvider(Protocol):
    """Tool source provider.

    Examples:
    - builtin provider: registers python-implemented tools
    - mcp provider: loads & registers tools from MCP servers
    - custom provider: user-defined tools from DB/config
    """

    name: str

    def get_tool(self, name: str) -> Optional[BaseTool]:
        raise NotImplementedError

    def get_tool_schema(self, name: str) -> Optional[dict]:
        raise NotImplementedError

    def get_tool_schemas(self, names: Optional[list[str]] = None) -> list[dict]:
        raise NotImplementedError

    def list_tool_names(self) -> list[str]:
        raise NotImplementedError

    def register_tool(self, tool: BaseTool) -> None:
        raise NotImplementedError

    def unregister_tool(self, name: str) -> bool:
        raise NotImplementedError

    def list_servers_with_tools(self) -> list[dict]:
        """Return tools grouped by server.

        Returns:
            List of server info dicts, each containing:
            - name: server name
            - type: "local" or "mcp"
            - tools: list of tool info dicts
        """
        raise NotImplementedError


@dataclass(frozen=True)
class _AgentEntry:
    cls: Type["BaseAgent"]#BaseAgent类
    config: AgentConfig#AgentConfig类的一个实例


class AgentHub:
    """Unified module hub."""

    _agents: dict[str, _AgentEntry] = {}
    _providers: dict[str, ToolProvider] = {}
    _user_agent_mcp_bindings: dict[str, dict[str, list[str]]] = {}

    # ==================== Agent ====================

    @classmethod
    def register_agent(cls, agent_cls: Type["BaseAgent"], config: AgentConfig) -> None:
        cls._agents[config.name] = _AgentEntry(cls=agent_cls, config=config)
        logger.info(f"Registered agent: {config.name}")

    @classmethod
    def get_agent(cls, name: str) -> "BaseAgent":
        entry = cls._agents.get(name)
        if not entry:
            raise KeyError(f"Agent '{name}' not found")
        #返回一个由_AgentEntry实例构造的agent实例
        return entry.cls(entry.config)

    @classmethod
    def get_agent_config(cls, name: str) -> AgentConfig:
        entry = cls._agents.get(name)
        if not entry:
            raise KeyError(f"Agent '{name}' not found")
        return entry.config

    @classmethod
    def list_agents(cls) -> list[str]:
        return list(cls._agents.keys())

    @classmethod
    def list_agent_configs(cls) -> list[AgentConfig]:
        return [entry.config for entry in cls._agents.values()]

    @classmethod
    def clear_agents(cls) -> None:
        cls._agents.clear()

    @classmethod
    def set_user_agent_mcp_bindings(
        cls,
        user_id: str,
        bindings: dict[str, list[str]],
    ) -> None:
        cls._user_agent_mcp_bindings[user_id] = {
            agent_name: list(dict.fromkeys(server_names))
            for agent_name, server_names in bindings.items()
        }

    @classmethod
    def get_user_agent_mcp_bindings(
        cls,
        user_id: Optional[str],
        agent_name: Optional[str],
    ) -> list[str]:
        if not user_id or not agent_name:
            return []
        return cls._user_agent_mcp_bindings.get(user_id, {}).get(agent_name, [])

    # ==================== Providers ====================

    @classmethod
    def register_provider(cls, provider: ToolProvider) -> None:
        if provider.name in cls._providers:
            raise ValueError(f"Provider already registered: {provider.name}")
        cls._providers[provider.name] = provider
        logger.info(f"Registered tool provider: {provider.name}")

    @classmethod
    def get_provider(cls, name: str) -> ToolProvider:
        provider = cls._providers.get(name)
        if not provider:
            raise KeyError(f"Provider '{name}' not found")
        return provider

    @classmethod
    def list_providers(cls) -> list[str]:
        return list(cls._providers.keys())

    @classmethod
    def clear_providers(cls) -> None:
        cls._providers.clear()

    # ==================== Tool surface (aggregated) ====================

    @classmethod
    def register_tool(cls, tool: BaseTool, provider: str = "local") -> None:
        cls.get_provider(provider).register_tool(tool)

    @classmethod
    def unregister_tool(cls, name: str) -> bool:
        for p in cls._providers.values():
            if p.get_tool(name):
                return p.unregister_tool(name)
        return False

    @classmethod
    def get_tool(cls, name: str, user_id: Optional[str] = None) -> Optional[BaseTool]:
        for p in cls._providers.values():
            # SubagentToolProvider 和 MCPToolProvider 需要 user_id 做用户级过滤
            if p.name in {"subagent", "mcp"} and user_id:
                tool = p.get_tool(name, user_id)  # type: ignore
            else:
                tool = p.get_tool(name)
            if tool:
                return tool
        return None

    @classmethod
    def get_tool_schemas(
        cls,
        names: Optional[list[str]] = None,
        user_id: Optional[str] = None,
    ) -> list[dict]:
        if names is None:
            schemas: list[dict] = []
            for p in cls._providers.values():
                if p.name in {"subagent", "mcp"} and user_id:
                    schemas.extend(p.get_tool_schemas(None, user_id))  # type: ignore
                else:
                    schemas.extend(p.get_tool_schemas(None))
            return schemas

        # keep order per names
        result: list[dict] = []
        for n in names:
            for p in cls._providers.values():
                if p.name in {"subagent", "mcp"} and user_id:
                    schema = p.get_tool_schema(n, user_id)  # type: ignore
                else:
                    schema = p.get_tool_schema(n)
                if schema:
                    result.append(schema)
                    break
        return result

    @classmethod
    def list_tools(cls, user_id: Optional[str] = None) -> list[str]:
        names: list[str] = []
        for p in cls._providers.values():
            if p.name in {"subagent", "mcp"} and user_id:
                names.extend(p.list_tool_names(user_id))  # type: ignore
            else:
                names.extend(p.list_tool_names())
        return names

    @classmethod
    def list_all_servers(cls, user_id: Optional[str] = None) -> list[dict]:
        """Aggregate all servers with tools from all providers.

        Returns:
            List of server dicts with unified structure:
            [
                { "name": "builtin", "type": "local", "tools": [...] },
                { "name": "amap", "type": "mcp", "tools": [...] },
                { "name": "subagents", "type": "subagent", "tools": [...] },
            ]
        """
        servers: list[dict] = []
        for p in cls._providers.values():
            if p.name in {"subagent", "mcp"} and user_id:
                servers.extend(p.list_servers_with_tools(user_id))  # type: ignore
            else:
                servers.extend(p.list_servers_with_tools())
        return servers

    @classmethod
    def resolve_agent_tool_names(
        cls,
        agent_name: str,
        user_id: Optional[str] = None,
        selected_tools: Optional[list[str]] = None,
    ) -> list[str]:
        """Return the final tool names available to an agent.
        根据agent绑定的工具名列表和前端传回的工具名列表,决定 Agent 可用的最终工具名称
        Agent tool bindings are the permission boundary. If selected_tools is
        None or empty, the agent gets all tools allowed by its binding. If
        selected_tools is non-empty, only selected tools within that binding are
        returned.
        """
        try:
            config = cls.get_agent_config(agent_name)
        except KeyError:
            config = AgentConfig(
                name=agent_name,
                description="Default agent",
                system_prompt="You are a helpful assistant.",
            )
        #返回agent绑定的所有工具名列表
        bound_names = cls.resolve_tool_binding(
            config.tool_binding,
            user_id=user_id,
            agent_name=agent_name,
        )
        if not selected_tools:
            return bound_names

        bound_set = set(bound_names)
        return [name for name in selected_tools if name in bound_set]

    @classmethod
    def get_agent_tool_schemas(
        cls,
        agent_name: str,
        user_id: Optional[str] = None,
        selected_tools: Optional[list[str]] = None,
    ) -> list[dict]:
        tool_names = cls.resolve_agent_tool_names(
            agent_name,
            user_id=user_id,
            selected_tools=selected_tools,
        )
        return cls.get_tool_schemas(tool_names, user_id=user_id)

    @classmethod
    def build_agent_tool_manifest(
        cls,
        user_id: Optional[str] = None,
    ) -> list[dict]:
        """Build the frontend-facing tools view grouped by agent and type."""
        agents: list[dict] = []
        all_servers = cls.list_all_servers(user_id=user_id)

        for config in cls.list_agent_configs():
            bound_names = cls.resolve_tool_binding(
                config.tool_binding,
                user_id=user_id,
                agent_name=config.name,
            )
            bound_set = set(bound_names)
            grouped = {
                "tool": cls._filter_servers_by_names(
                    all_servers, bound_set, server_type="local"
                ),
                "mcp": cls._filter_servers_by_names(
                    all_servers, bound_set, server_type="mcp"
                ),
                "subagent": cls._filter_servers_by_names(
                    all_servers, bound_set, server_type="subagent"
                ),
            }
            agents.append(
                {
                    "name": config.name,
                    "description": config.description,
                    "tools": grouped,
                    "default_tools": bound_names,
                }
            )

        return agents

    @classmethod
    def resolve_tool_binding(
        cls,
        binding: AgentToolBinding,
        user_id: Optional[str] = None,
        agent_name: Optional[str] = None,
    ) -> list[str]:
        '''
        把一个 AgentToolBinding 里配置的各种工具绑定，解析成最终可用的工具名列表，并且去重保序。
        返回agent绑定的所有工具名列表
        '''
        names: list[str] = []
        names.extend(cls._resolve_provider_binding("local", binding.local, user_id))
        mcp_servers = list(binding.mcp)
        mcp_servers.extend(cls.get_user_agent_mcp_bindings(user_id, agent_name))
        names.extend(cls._resolve_mcp_server_binding(mcp_servers, user_id))
        names.extend(
            cls._resolve_provider_binding("subagent", binding.subagents, user_id)
        )
        return list(dict.fromkeys(names))

    @classmethod
    def _resolve_mcp_server_binding(
        cls,
        server_names: list[str],
        user_id: Optional[str] = None,
    ) -> list[str]:
        provider = cls._providers.get("mcp")
        if not provider or not server_names:
            return []
        #available是当前用户所有可见的工具名列表
        if user_id:
            available = provider.list_tool_names(user_id)  # type: ignore
        else:
            available = provider.list_tool_names()

        expanded: list[str] = []
        if hasattr(provider, "list_tool_names_by_servers"):
            if user_id:
                expanded = provider.list_tool_names_by_servers(  # type: ignore
                    server_names, user_id
                )
            else:
                expanded = provider.list_tool_names_by_servers(server_names)  # type: ignore

        # Keep explicit MCP tool names working for older configs.
        #allowed_names为本agent绑定的mcp服务器下的所有工具名列表
        allowed_names = set(expanded) | set(server_names)
        return [name for name in available if name in allowed_names]

    @classmethod
    def _resolve_provider_binding(
        cls,
        provider_name: str,
        patterns: list[str],
        user_id: Optional[str] = None,
    ) -> list[str]:
        provider = cls._providers.get(provider_name)
        if not provider or not patterns:
            return []
        #available 是所有可用工具
        if provider_name in {"subagent", "mcp"} and user_id:
            available = provider.list_tool_names(user_id)  # type: ignore
        else:
            available = provider.list_tool_names()

        normalized_patterns: list[str] = []
        for p in patterns:
            normalized_patterns.append(p)
            if provider_name == "subagent":
                if p.startswith("subagent_"):
                    normalized_patterns.append(p.removeprefix("subagent_"))
                else:
                    normalized_patterns.append(f"subagent_{p}")

        if "*" in normalized_patterns:
            return available

        return [
            name
            for name in available
            if any(fnmatch(name, pattern) for pattern in normalized_patterns)
        ]

    @staticmethod
    def _filter_servers_by_names(
        servers: list[dict],
        names: set[str],
        server_type: str,
    ) -> list[dict]:
        filtered: list[dict] = []
        for server in servers:
            if server.get("type") != server_type:
                continue
            tools = [t for t in server.get("tools", []) if t.get("name") in names]
            if tools:
                filtered.append(
                    {
                        "name": server.get("name", ""),
                        "type": server.get("type", ""),
                        "tools": tools,
                    }
                )
        return filtered

    @classmethod
    def create_tool_executor(
        cls,
        tool_names: Optional[list[str]] = None,
        user_id: Optional[str] = None,
    ) -> ToolExecutor:
        if tool_names is None:
            tools: dict[str, BaseTool] = {}
            for p in cls._providers.values():
                if p.name in {"subagent", "mcp"} and user_id:
                    tool_list = p.list_tool_names(user_id)  # type: ignore
                else:
                    tool_list = p.list_tool_names()
                for name in tool_list:
                    if p.name in {"subagent", "mcp"} and user_id:
                        tool = p.get_tool(name, user_id)  # type: ignore
                    else:
                        tool = p.get_tool(name)
                    if tool:
                        tools[name] = tool
            return ToolExecutor(tools, user_id=user_id)

        tools = {}
        for n in tool_names:
            tool = cls.get_tool(n, user_id)
            if tool:
                tools[n] = tool
        return ToolExecutor(tools, user_id=user_id)

    # ==================== Cleanup ====================

    @classmethod
    def clear_all(cls) -> None:
        cls.clear_agents()
        cls.clear_providers()
        cls._user_agent_mcp_bindings.clear()


# Imported only for type checking; avoid runtime circular import
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent.agents import BaseAgent  # pragma: no cover
