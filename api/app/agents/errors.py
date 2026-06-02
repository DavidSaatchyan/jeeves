from __future__ import annotations


class AgentNotFoundError(Exception):
    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        super().__init__(f"Agent '{agent_id}' not found in registry")
