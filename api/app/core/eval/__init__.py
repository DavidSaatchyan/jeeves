from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class EvalSample:
    question: str
    answer: str
    contexts: list[str]
    reference_answer: str
    source_type: str
    language: str
    specialty: str
    difficulty: str
    requires_doc: str | None = None


@dataclass
class EvalResult:
    faithfulness: float | None = None
    answer_relevancy: float | None = None
    context_precision: float | None = None
    context_recall: float | None = None


class RAGEvaluator:
    def __init__(self, llm_model: str = "gpt-4o-mini") -> None:
        self._llm_model = llm_model
        self._ragas_available = self._check_ragas()

    def _check_ragas(self) -> bool:
        try:
            from ragas.metrics._faithfulness import faithfulness  # noqa: F401
            from ragas import evaluate  # noqa: F401
            return True
        except ImportError:
            logger.warning("ragas not available — eval will be skipped")
            return False

    def compute(self, samples: list[EvalSample]) -> EvalResult:
        if not self._ragas_available:
            return EvalResult()

        from ragas import evaluate
        from ragas.embeddings.base import LangchainEmbeddingsWrapper
        from ragas.llms import llm_factory
        from ragas.metrics._faithfulness import faithfulness as _faithfulness
        from ragas.metrics._answer_relevance import answer_relevancy as _answer_relevancy
        from ragas.metrics._context_precision import context_precision as _context_precision
        from ragas.metrics._context_recall import context_recall as _context_recall
        import pandas as pd
        from datasets import Dataset
        from langchain_openai import OpenAIEmbeddings
        from openai import OpenAI

        _client = OpenAI()
        _lc_emb = OpenAIEmbeddings(model="text-embedding-3-small")

        llm = llm_factory(self._llm_model, client=_client)

        _faithfulness.llm = llm
        _answer_relevancy.llm = llm
        _answer_relevancy.embeddings = LangchainEmbeddingsWrapper(_lc_emb)
        _context_precision.llm = llm
        _context_recall.llm = llm

        contexts = [s.contexts for s in samples]
        if contexts and all(not c for c in contexts):
            contexts = [["placeholder"] for _ in samples]

        data = {
            "question": [s.question for s in samples],
            "answer": [s.answer for s in samples],
            "contexts": contexts,
            "ground_truth": [s.reference_answer for s in samples],
        }
        ds = Dataset.from_dict(data)
        try:
            result = evaluate(
                ds,
                metrics=[_faithfulness, _answer_relevancy, _context_precision, _context_recall],
                llm=llm,
                raise_exceptions=False,
            )
            df = result.to_pandas()
            faith = df.get("faithfulness", pd.Series([None]))
            answer_rel = df.get("answer_relevancy", pd.Series([None]))
            ctx_prec = df.get("context_precision", pd.Series([None]))
            ctx_recall = df.get("context_recall", pd.Series([None]))
            return EvalResult(
                faithfulness=float(faith.mean()) if not faith.isna().all() else None,
                answer_relevancy=float(answer_rel.mean()) if not answer_rel.isna().all() else None,
                context_precision=float(ctx_prec.mean()) if not ctx_prec.isna().all() else None,
                context_recall=float(ctx_recall.mean()) if not ctx_recall.isna().all() else None,
            )
        except Exception as e:
            logger.warning("RAGAS evaluate failed: %s", e)
            return EvalResult()

    def save_baseline(self, result: EvalResult, path: Path) -> None:
        data = {
            "faithfulness": result.faithfulness,
            "answer_relevancy": result.answer_relevancy,
            "context_precision": result.context_precision,
            "context_recall": result.context_recall,
            "model": self._llm_model,
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("baseline saved to %s", path)

    def load_baseline(self, path: Path) -> EvalResult | None:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return EvalResult(
            faithfulness=data.get("faithfulness"),
            answer_relevancy=data.get("answer_relevancy"),
            context_precision=data.get("context_precision"),
            context_recall=data.get("context_recall"),
        )
