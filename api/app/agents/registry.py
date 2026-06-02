from __future__ import annotations

from typing import Any

from .base import Agent, AgentResult
from .errors import AgentNotFoundError

_registry: dict[str, Agent] = {}


def register(agent: Agent) -> None:
    _registry[agent.agent_id] = agent


async def dispatch(agent_id: str, **kwargs: Any) -> AgentResult:
    agent = _registry.get(agent_id)
    if not agent:
        raise AgentNotFoundError(agent_id)
    return await agent.handle(**kwargs)


def list_agents() -> list[Agent]:
    return list(_registry.values())
