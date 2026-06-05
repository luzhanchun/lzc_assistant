"""
MCP server management service.
"""

import logging
from hashlib import sha256
from typing import List

from sqlalchemy import select

from app.agent.database.models import AgentMCPServerModel
from app.agent.registry import AgentHub
from app.agent.tools.providers.mcp import MCPToolProvider
from app.config.mcp_config import (
    validate_mcp_auth,
    validate_mcp_endpoint,
    validate_mcp_name,
)
from app.database.session import get_session_context

logger = logging.getLogger(__name__)


class MCPService:
    """Service for managing user-defined MCP servers."""

    async def list_servers(self, user_id: str) -> List[AgentMCPServerModel]:
        async with get_session_context() as session:
            stmt = select(AgentMCPServerModel).where(
                AgentMCPServerModel.user_id == user_id
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def create_server(
        self,
        *,
        user_id: str,
        name: str,
        endpoint: str,
        enabled: bool = True,
        auth_header_name: str | None = None,
        auth_token: str | None = None,
    ) -> AgentMCPServerModel:
        self._validate_name(name)
        self._validate_endpoint(endpoint)
        self._validate_auth(auth_header_name, auth_token)

        async with get_session_context() as session:
            existing_stmt = select(AgentMCPServerModel).where(
                AgentMCPServerModel.user_id == user_id,
                AgentMCPServerModel.name == name,
            )
            existing = (await session.execute(existing_stmt)).scalar_one_or_none()
            if existing:
                raise ValueError("MCP 名称已存在")

            server = AgentMCPServerModel(
                user_id=user_id,
                name=name,
                endpoint=endpoint,
                auth_header_name=auth_header_name,
                auth_token=auth_token,
                enabled=enabled,
            )
            session.add(server)
            await session.flush()

        if enabled:
            try:
                registered = await self.register_server(server)
            except Exception as exc:
                await self._cleanup_failed_create(user_id, name)
                raise ValueError(f"MCP 工具加载失败：{exc}") from exc

            if not registered:
                provider = self._get_provider()
                registry_name = self._registry_name(user_id, name)
                load_error = provider.get_last_load_error(registry_name)
                await self._cleanup_failed_create(user_id, name)
                detail = load_error or "未加载到任何工具"
                raise ValueError(f"MCP 工具加载失败：{detail}")

        return server

    async def register_server(self, server: AgentMCPServerModel) -> bool:
        if not server.enabled:
            return False

        provider = self._get_provider()
        headers = self._build_headers(server)
        registry_name = self._registry_name(server.user_id, server.name)
        provider.register_server(
            registry_name,
            server.endpoint,
            headers,
            scope="user",
            user_id=server.user_id,
            display_name=server.name,
        )
        loaded = await provider.load_server_tools(registry_name)
        return len(loaded) > 0

    async def register_all_for_user(self, user_id: str) -> None:
        servers = await self.list_servers(user_id)
        for server in servers:
            if not server.enabled:
                continue
            try:
                await self.register_server(server)
            except Exception as exc:
                logger.warning(
                    "Failed to register MCP server %s for user %s: %s",
                    server.name,
                    user_id,
                    exc,
                )

    async def register_all(self) -> None:
        async with get_session_context() as session:
            stmt = select(AgentMCPServerModel).where(
                AgentMCPServerModel.enabled.is_(True)
            )
            result = await session.execute(stmt)
            servers = list(result.scalars().all())

        for server in servers:
            try:
                await self.register_server(server)
            except Exception as exc:
                logger.warning("Failed to register MCP server %s: %s", server.name, exc)

    async def update_server(
        self,
        *,
        user_id: str,
        name: str,
        endpoint: str | None = None,
        enabled: bool | None = None,
        auth_header_name: str | None = None,
        auth_token: str | None = None,
        update_auth: bool = False,
    ) -> AgentMCPServerModel | None:
        async with get_session_context() as session:
            stmt = select(AgentMCPServerModel).where(
                AgentMCPServerModel.user_id == user_id,
                AgentMCPServerModel.name == name,
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if not existing:
                return None

            if endpoint is not None:
                self._validate_endpoint(endpoint)
                existing.endpoint = endpoint

            if update_auth:
                self._validate_auth(auth_header_name, auth_token)
                existing.auth_header_name = auth_header_name
                existing.auth_token = auth_token

            if enabled is not None:
                existing.enabled = enabled

        if not existing.enabled:
            self._unregister_server(existing.user_id, existing.name)
            return existing

        await self.register_server(existing)
        return existing

    async def delete_server(self, user_id: str, name: str) -> bool:
        async with get_session_context() as session:
            stmt = select(AgentMCPServerModel).where(
                AgentMCPServerModel.user_id == user_id,
                AgentMCPServerModel.name == name,
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if not existing:
                return False

            await session.delete(existing)

        self._unregister_server(user_id, name)
        return True

    def _validate_name(self, name: str) -> None:
        validate_mcp_name(name)

    def _validate_endpoint(self, endpoint: str) -> None:
        validate_mcp_endpoint(endpoint)

    def _validate_auth(
        self, auth_header_name: str | None, auth_token: str | None
    ) -> None:
        validate_mcp_auth(auth_header_name, auth_token)

    def _build_headers(self, server: AgentMCPServerModel) -> dict[str, str] | None:
        if server.auth_header_name and server.auth_token:
            return {server.auth_header_name: server.auth_token}
        return None

    def _get_provider(self) -> MCPToolProvider:
        return AgentHub.get_provider("mcp")  # type: ignore

    def _registry_name(self, user_id: str, name: str) -> str:
        user_hash = sha256(user_id.encode("utf-8")).hexdigest()[:12]
        return f"user_{user_hash}_{name}"

    def _unregister_server(self, user_id: str, name: str) -> None:
        provider = self._get_provider()
        provider.unregister_server(self._registry_name(user_id, name))

    async def _cleanup_failed_create(self, user_id: str, name: str) -> None:
        try:
            await self.delete_server(user_id, name)
        except Exception as exc:
            logger.warning(
                "Failed to cleanup MCP server %s after load failure: %s",
                name,
                exc,
            )


mcp_service = MCPService()
