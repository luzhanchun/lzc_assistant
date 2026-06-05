"""Agent routing decision module."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

from app.agent.database.models import AgentSessionModel
from app.agent.database.repository import AgentRepository, agent_repository
from app.agent.prompts import AGENT_ROUTER_SYSTEM_PROMPT
from app.agent.registry import AgentHub
from app.config import settings
from app.llm.context import llm_context
from app.llm.provider import LLMProvider

logger = logging.getLogger(__name__)


MIN_ROUTE_CONFIDENCE = 0.5
FALLBACK_AGENT_NAME = "fallback_triage_agent"


@dataclass
class AgentRouteDecision:
    """Structured routing decision for selecting an agent."""

    agent_name: str
    confidence: float
    reason: str


class Agent_router:
    """Route a user message to the best registered agent."""

    def __init__(
        self,
        repository: Optional[AgentRepository] = None,
        recent_messages_limit: int = 20,
        fallback_agent_name: str = FALLBACK_AGENT_NAME,
    ):
        self.repository = repository or agent_repository
        self.recent_messages_limit = recent_messages_limit
        self.fallback_agent_name = fallback_agent_name

    async def router(
        self,
        session: AgentSessionModel,
        message: str,
    ) -> AgentRouteDecision:
        """Return a structured routing decision for the current message."""
        session_id = str(session.id)
        configs = AgentHub.list_agent_configs()
        allowed_names = {config.name for config in configs}

        if not configs:
            return self._fallback("No registered agents are available")

        compressed_summary = ""
        compressed_count = 0
        recent_messages: list[dict] = []

        try:
            compressed_summary, compressed_count = (
                await self.repository.get_compressed_summary(session_id)
            )
            recent_messages = await self.repository.get_recent_messages(
                session_id,
                skip=compressed_count,
                limit=self.recent_messages_limit,
            )
        except Exception as exc:
            logger.warning("Failed to load routing history: %s", exc)

        agent_candidates = [
            {
                "name": config.name,
                "description": config.description,
            }
            for config in configs
        ]

        prompt = AGENT_ROUTER_SYSTEM_PROMPT.format(
            agent_candidates=json.dumps(
                agent_candidates,
                ensure_ascii=False,
                default=str,
            ),
            message=message,
            compressed_summary=compressed_summary or "无",
            recent_messages=json.dumps(
                recent_messages,
                ensure_ascii=False,
                default=str,
            ),
        )

        try:
            provider = LLMProvider(settings.llm)
            invoker = provider.create_invoker(
                llm_type="fast",
                streaming=False,
                temperature=0,
            )
            with llm_context(
                "agent:router",
                getattr(session, "user_id", None),
                session_id,
            ):
                response = await invoker.ainvoke(
                    [
                        {"role": "system", "content": prompt},
                        {
                            "role": "user",
                            "content": "请根据上面的输入，只输出一个合法 JSON 路由决策对象。",
                        },
                    ]
                )
            raw_content = self._extract_content(response)
            payload = self._parse_json(raw_content)
            decision = self._validate_payload(payload, allowed_names)
            if decision.confidence < MIN_ROUTE_CONFIDENCE:
                return self._fallback(
                    f"Route confidence too low: {decision.confidence}"
                )
            return decision
        except Exception as exc:
            logger.warning(
                "Agent routing failed, using fallback: %s; response=%s",
                exc,
                self._response_debug_info(locals().get("response")),
            )
            return self._fallback(f"Agent routing failed: {exc}")

    def _fallback(self, reason: str) -> AgentRouteDecision:
        return AgentRouteDecision(
            agent_name=self.fallback_agent_name,
            confidence=0.0,
            reason=reason,
        )

    def _extract_content(self, response: Any) -> str:
        if hasattr(response, "content"):
            content = response.content
        else:
            content = response

        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict):
                    text = part.get("text") or part.get("content")
                    if isinstance(text, str):
                        text_parts.append(text)
            if text_parts:
                return "\n".join(text_parts)
        return json.dumps(content, ensure_ascii=False, default=str)

    def _parse_json(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if not text:
            raise ValueError("Router LLM returned empty content")

        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                raise
            payload = json.loads(text[start : end + 1])

        if not isinstance(payload, dict):
            raise ValueError("Router output must be a JSON object")
        return payload

    def _validate_payload(
        self,
        payload: dict[str, Any],
        allowed_names: set[str],
    ) -> AgentRouteDecision:
        agent_name = payload.get("agent_name")
        confidence = payload.get("confidence")
        reason = payload.get("reason")

        if not isinstance(agent_name, str) or not agent_name:
            raise ValueError("Router output has invalid agent_name")
        if agent_name not in allowed_names:
            raise ValueError(f"Router selected unknown agent: {agent_name}")
        if isinstance(confidence, str):
            try:
                confidence = float(confidence)
            except ValueError as exc:
                raise ValueError("Router output has invalid confidence") from exc
        if not isinstance(confidence, (int, float)):
            raise ValueError("Router output has invalid confidence")
        if not isinstance(reason, str) or not reason:
            raise ValueError("Router output has invalid reason")

        bounded_confidence = max(0.0, min(1.0, float(confidence)))
        return AgentRouteDecision(
            agent_name=agent_name,
            confidence=bounded_confidence,
            reason=reason,
        )

    def _response_debug_info(self, response: Any) -> dict[str, Any]:
        if response is None:
            return {"is_none": True}

        debug = {
            "type": type(response).__name__,
            "content_preview": self._extract_content(response)[:200],
        }
        if hasattr(response, "response_metadata"):
            debug["response_metadata"] = getattr(response, "response_metadata")
        if hasattr(response, "additional_kwargs"):
            debug["additional_kwargs"] = getattr(response, "additional_kwargs")
        if hasattr(response, "usage_metadata"):
            debug["usage_metadata"] = getattr(response, "usage_metadata")
        return debug


__all__ = ["Agent_router", "AgentRouteDecision"]
