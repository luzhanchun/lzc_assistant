"""
User-level MCP server bindings for registered agents.
"""

from sqlalchemy import delete, select

from app.agent.database.models import AgentMCPBindingModel
from app.agent.registry import AgentHub
from app.database.session import get_session_context


class AgentMCPBindingService:
    """Service for binding user-defined MCP servers to agents."""

    async def bind_server_to_agents(
        self,
        *,
        user_id: str,
        server_name: str,
        agent_names: list[str],
    ) -> None:
        agent_names = self.normalize_agent_names(agent_names)
        self.validate_agent_names(agent_names)

        async with get_session_context() as session:
            for agent_name in agent_names:
                session.add(
                    AgentMCPBindingModel(
                        user_id=user_id,
                        agent_name=agent_name,
                        mcp_server_name=server_name,
                    )
                )

        await self.sync_user_bindings(user_id)

    async def replace_server_bindings(
        self,
        *,
        user_id: str,
        server_name: str,
        agent_names: list[str],
    ) -> None:
        agent_names = self.normalize_agent_names(agent_names)
        self.validate_agent_names(agent_names)

        async with get_session_context() as session:
            await session.execute(
                delete(AgentMCPBindingModel).where(
                    AgentMCPBindingModel.user_id == user_id,
                    AgentMCPBindingModel.mcp_server_name == server_name,
                )
            )
            for agent_name in agent_names:
                session.add(
                    AgentMCPBindingModel(
                        user_id=user_id,
                        agent_name=agent_name,
                        mcp_server_name=server_name,
                    )
                )

        await self.sync_user_bindings(user_id)

    async def delete_server_bindings(self, user_id: str, server_name: str) -> None:
        async with get_session_context() as session:
            await session.execute(
                delete(AgentMCPBindingModel).where(
                    AgentMCPBindingModel.user_id == user_id,
                    AgentMCPBindingModel.mcp_server_name == server_name,
                )
            )

        await self.sync_user_bindings(user_id)

    async def list_server_bound_agents(
        self,
        *,
        user_id: str,
        server_name: str,
    ) -> list[str]:
        async with get_session_context() as session:
            stmt = (
                select(AgentMCPBindingModel.agent_name)
                .where(
                    AgentMCPBindingModel.user_id == user_id,
                    AgentMCPBindingModel.mcp_server_name == server_name,
                )
                .order_by(AgentMCPBindingModel.created_at)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def sync_user_bindings(self, user_id: str) -> dict[str, list[str]]:
        async with get_session_context() as session:
            stmt = (
                select(AgentMCPBindingModel)
                .where(AgentMCPBindingModel.user_id == user_id)
                .order_by(
                    AgentMCPBindingModel.agent_name,
                    AgentMCPBindingModel.created_at,
                )
            )
            result = await session.execute(stmt)
            bindings = list(result.scalars().all())

        by_agent: dict[str, list[str]] = {}
        for binding in bindings:
            by_agent.setdefault(binding.agent_name, []).append(binding.mcp_server_name)

        AgentHub.set_user_agent_mcp_bindings(user_id, by_agent)
        return by_agent

    def normalize_agent_names(self, agent_names: list[str]) -> list[str]:
        normalized = [name.strip() for name in agent_names if name and name.strip()]
        return list(dict.fromkeys(normalized))

    def validate_agent_names(self, agent_names: list[str]) -> None:
        for agent_name in agent_names:
            try:
                AgentHub.get_agent_config(agent_name)
            except KeyError as exc:
                raise ValueError(f"Agent not found: {agent_name}") from exc


agent_mcp_binding_service = AgentMCPBindingService()
