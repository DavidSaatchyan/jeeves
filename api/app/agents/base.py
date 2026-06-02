from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session


@dataclass
class AgentAction:
    action_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = "success"


@dataclass
class AgentResult:
    response: str | None = None
    actions: list[AgentAction] = field(default_factory=list)
    escalate: bool = False
    intent: str | None = None


class Agent(ABC):
    agent_id: str = ""
    description: str = ""

    @abstractmethod
    async def handle(
        self,
        *,
        tenant_id: str,
        customer_id: str,
        db: Session,
        **kwargs: Any,
    ) -> AgentResult:
        ...
