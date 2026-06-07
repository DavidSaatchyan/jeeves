"""RAG evaluation tests — Sprint 0 baseline."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.eval import RAGEvaluator


@pytest.fixture
def baseline_path() -> Path:
    return Path(__file__).parent / "rag_baseline.json"


@pytest.mark.eval
class TestGoldenDataset:
    def test_dataset_loads(self, golden_dataset: list[dict]):
        assert len(golden_dataset) >= 75, f"Expected >=75 samples, got {len(golden_dataset)}"

    def test_dataset_structure(self, golden_dataset: list[dict]):
        required = {"query", "reference_answer", "source_type", "language", "specialty", "difficulty"}
        for i, s in enumerate(golden_dataset):
            missing = required - set(s.keys())
            assert not missing, f"Sample {i} missing fields: {missing}"

    def test_dataset_languages(self, golden_dataset: list[dict]):
        langs = {s["language"] for s in golden_dataset}
        assert "en" in langs
        assert any(lang in langs for lang in ("de", "fr", "es", "it"))

    def test_dataset_specialties(self, golden_dataset: list[dict]):
        specialties = {s["specialty"] for s in golden_dataset}
        expected = {"gp", "dermatology", "gynecology", "aesthetic", "dentistry", "preventive"}
        missing = expected - specialties
        assert not missing, f"Missing specialties: {missing}"


@pytest.mark.eval
class TestRAGEvaluator:
    def test_evaluator_import(self):
        ev = RAGEvaluator()
        assert ev._ragas_available, "ragas should be importable"

    def test_baseline_save_load(self, tmp_path: Path, baseline_path: Path):
        from app.core.eval import EvalResult
        r = EvalResult(faithfulness=0.85, answer_relevancy=0.72, context_precision=0.68, context_recall=0.55)
        ev = RAGEvaluator()
        p = tmp_path / "test_baseline.json"
        ev.save_baseline(r, p)
        assert p.exists()
        loaded = ev.load_baseline(p)
        assert loaded is not None
        assert loaded.faithfulness == 0.85

    @pytest.mark.skip(reason="Requires real LLM calls and indexed data — run manually with --run-eval")
    def test_full_eval(self, golden_dataset: list[dict], synthetic_kb_loader: list[str], synthetic_pms_loader: list[str]):
        """Full eval pipeline — requires --run-eval flag."""
        ev = RAGEvaluator()
        samples = []
        for s in golden_dataset:
            from app.core.eval import EvalSample
            samples.append(EvalSample(
                question=s["query"],
                answer="",
                contexts=[],
                reference_answer=s["reference_answer"],
                source_type=s["source_type"],
                language=s.get("language", "en"),
                specialty=s.get("specialty", ""),
                difficulty=s.get("difficulty", "easy"),
            ))
        result = ev.compute(samples)
        assert result.faithfulness is not None
        assert result.answer_relevancy is not None
