from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class Worker(ABC):
    name: str = "base"

    @abstractmethod
    async def run(self) -> None:
        ...

    async def start(self) -> None:
        logger.info("worker %s started", self.name)
        try:
            await self.run()
        except Exception as e:
            logger.exception("worker %s crashed: %s", self.name, e)
            raise
