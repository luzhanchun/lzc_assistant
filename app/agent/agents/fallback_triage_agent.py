# app/agent/agents/fallback_triage_agent.py
"""
FallbackTriageAgent - 兜底分诊 Agent

兜底分诊 Agent 实现，无特殊逻辑。
"""

from app.agent.agents.base import BaseAgent


class FallbackTriageAgent(BaseAgent):
    """
    兜底分诊 Agent 实现。

    用于承接无法明确匹配到专业 Agent 的请求，无特殊逻辑。
    """

    pass


__all__ = ["FallbackTriageAgent"]
