"""
Agent 模块

独立的对话处理系统，与现有 ConversationService 完全分离。
"""

from app.agent.types import (
    AgentChunk,
    AgentChunkType,
    AgentConfig,
    AgentContext,
    AgentToolBinding,
    AgentMessage,
    AgentSession,
    ToolCallInfo,
    ToolResult,
    ToolResultInfo,
    TraceStep,
)
from app.agent.agents import BaseAgent, Diet_Cook_Agent, Travel_Planning_Agent
from app.agent.registry import AgentHub
from app.agent.tools.providers import (
    LocalToolProvider,
    MCPToolProvider,
    SubagentToolProvider,
)
from app.agent.service import AgentService, agent_service
from app.agent.prompts import (
    DIET_COOKING_ASSISTANT_DESCRIPTION,
    DIET_COOKING_ASSISTANT_SYSTEM_PROMPT,
    TRAVEL_PLANNING_ASSISTANT_DESCRIPTION,
    TRAVEL_PLANNING_ASSISTANT_SYSTEM_PROMPT,
)
from app.agent.context import (
    AgentContextBuilder,
    AgentContextCompressor,
    agent_context_builder,
    agent_context_compressor,
)
from app.agent.tools.base import BaseTool, MCPTool, ToolExecutor


def setup_agent_module():
    """
    初始化 Agent 模块（同步部分）。

    注册内置 Agent、Tool、Skill 和 Subagent。
    应在应用启动时调用。
    """
    # Register tool providers once
    if not AgentHub.list_providers():
        AgentHub.register_provider(LocalToolProvider())
        AgentHub.register_provider(MCPToolProvider())
        AgentHub.register_provider(SubagentToolProvider())

    # 注册内置 Tools
    from app.agent.tools.common import register_common_tools

    register_common_tools()

    # 注册饮食模块 Tools
    from app.diet.tools import register_diet_tools

    register_diet_tools()

    # 注册内置 Subagents
    from app.agent.subagents import register_builtin_subagents

    register_builtin_subagents()

    # 注册所有Agent
    _register_all_agent()


async def setup_mcp_servers():
    """
    初始化 MCP 服务器（异步部分）。

    注册并加载所有配置的 MCP 服务器。
    应在应用启动时、setup_agent_module 之后调用。
    """
    from app.agent.tools.mcp.setup import register_mcp_servers

    await register_mcp_servers()


def _register_all_agent():
    _register_diet_cook_agent()
    _register_travel_planning_agent()


def _register_diet_cook_agent():
    """注册diet_cooking_assistant Agent。"""
    default_config = AgentConfig(
        name="diet_cooking_assistant",
        description=DIET_COOKING_ASSISTANT_DESCRIPTION,
        system_prompt=DIET_COOKING_ASSISTANT_SYSTEM_PROMPT,
        tool_binding=AgentToolBinding(
            local=[
                "calculator",
                "datetime",
                "web_search",
                "image_generator",
                "knowledge_base_search",
                "diet_plan",
                "diet_log",
                "diet_analysis",
            ],
            mcp=["amap"],
            subagents=["subagent_diet_planner"],
        ),
        max_iterations=10,
    )

    AgentHub.register_agent(Diet_Cook_Agent, default_config)


def _register_travel_planning_agent():
    """注册travel_planning_assistant Agent。"""
    default_config = AgentConfig(
        name="travel_planning_assistant",
        description=TRAVEL_PLANNING_ASSISTANT_DESCRIPTION,
        system_prompt=TRAVEL_PLANNING_ASSISTANT_SYSTEM_PROMPT,
        tool_binding=AgentToolBinding(
            local=[
                "calculator",
                "datetime",
                "web_search",
                "image_generator",
            ],
            mcp=["amap"],
            subagents=[],
        ),
        max_iterations=10,
    )

    AgentHub.register_agent(Travel_Planning_Agent, default_config)


__all__ = [
    # Types
    "AgentChunk",
    "AgentChunkType",
    "AgentConfig",
    "AgentContext",
    "AgentToolBinding",
    "AgentMessage",
    "AgentSession",
    "ToolCallInfo",
    "ToolResult",
    "ToolResultInfo",
    "TraceStep",
    # Base classes
    "BaseAgent",
    "Diet_Cook_Agent",
    "Travel_Planning_Agent",
    "BaseTool",
    "MCPTool",
    "ToolExecutor",
    # Service
    "AgentService",
    "agent_service",
    # Context
    "AgentContextBuilder",
    "AgentContextCompressor",
    "agent_context_builder",
    "agent_context_compressor",
    # Setup
    "setup_agent_module",
    "setup_mcp_servers",
]
