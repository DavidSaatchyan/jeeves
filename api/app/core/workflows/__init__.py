from __future__ import annotations

from .registry import register_workflow


def init_workflows() -> None:
    from .wismo import WismoWorkflow

    register_workflow("wismo", WismoWorkflow)