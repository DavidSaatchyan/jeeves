"""RAG evaluation runner — calls pipeline directly (not via /chat) and collects metrics."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.agents.incoming_line import _handle_kb_query
from app.core.ai.generator import simple_llm_response
from app.core.eval import EvalSample, RAGEvaluator
from tests.golden_dataset import GoldenSample

logger = logging.getLogger(__name__)


async def run_sample(
    sample: GoldenSample,
    tenant_id: str,
    agent_config: dict[str, Any],
) -> EvalSample:
    if sample.source_type == "general":
        personality = agent_config.get("personality", {})
        system_prompt = personality.get(
            "system_prompt",
            "You are the front desk of a medical clinic. Be warm and professional.",
        )
        result = await simple_llm_response(
            tenant_id, sample.query,
            system_override=system_prompt,
        )
        answer = result.get("response", "")
        context_list: list[str] = []
    else:
        answer, _citations = await _handle_kb_query(sample.query, tenant_id, agent_config)
        context_list: list[str] = [c.get("text_snippet", c.get("text", "")) for c in (_citations or []) if isinstance(c, dict)]
    return EvalSample(
        question=sample.query,
        answer=answer or "",
        contexts=context_list or [],
        reference_answer=sample.reference_answer or "",
        source_type=sample.source_type or "",
        language=sample.language or "en",
        specialty=sample.specialty or "",
        difficulty=sample.difficulty or "easy",
        requires_doc=sample.requires_doc,
    )


async def run_eval(
    samples: list[GoldenSample],
    tenant_id: str,
    agent_config: dict[str, Any],
    evaluator: RAGEvaluator,
) -> dict[str, Any]:
    eval_samples = []
    for sample in samples:
        es = await run_sample(sample, tenant_id, agent_config)
        eval_samples.append(es)
    result = evaluator.compute(eval_samples)
    return {
        "faithfulness": result.faithfulness,
        "answer_relevancy": result.answer_relevancy,
        "context_precision": result.context_precision,
        "context_recall": result.context_recall,
        "num_samples": len(eval_samples),
    }


def load_golden_dataset(path: Path) -> list[dict[str, Any]]:
    samples = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    return samples
