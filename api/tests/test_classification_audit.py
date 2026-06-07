"""Classification distribution audit — T-0.5 (Sprint 0)."""
from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

logger = logging.getLogger(__name__)

_MESSAGES_PATH = Path(__file__).parent / "synthetic_messages_500.jsonl"


@pytest.fixture(scope="session")
def synthetic_messages() -> list[dict[str, Any]]:
    msgs = []
    with open(_MESSAGES_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                msgs.append(json.loads(line))
    return msgs


@pytest.mark.classification
class TestClassificationAudit:
    def test_messages_load(self, synthetic_messages: list[dict]):
        assert len(synthetic_messages) == 500, f"Expected 500, got {len(synthetic_messages)}"

    def test_messages_structure(self, synthetic_messages: list[dict]):
        required = {"text", "expected_intent", "language", "specialty"}
        for i, m in enumerate(synthetic_messages):
            missing = required - set(m.keys())
            assert not missing, f"Message {i} missing fields: {missing}"

    def test_messages_intent_coverage(self, synthetic_messages: list[dict]):
        intents = Counter(m["expected_intent"] for m in synthetic_messages)
        logger.info("Intent distribution: %s", dict(intents))
        expected = {"kb_query", "appointment", "availability", "reschedule", "cancel", "general", "emergency"}
        missing = expected - set(intents.keys())
        assert not missing, f"Missing intents: {missing}"

    def test_messages_language_coverage(self, synthetic_messages: list[dict]):
        langs = Counter(m["language"] for m in synthetic_messages)
        logger.info("Language distribution: %s", dict(langs))
        assert langs.get("en", 0) >= 200
        assert langs.get("de", 0) >= 50
        assert langs.get("fr", 0) >= 40

    @pytest.mark.skip(reason="Requires real LLM classify() calls — run with --run-classify")
    def test_run_classification(self, synthetic_messages: list[dict]):
        """Run all 500 messages through classify() and report distribution."""
        import asyncio
        from app.core.ai.classify import classify

        results = []
        for m in synthetic_messages:
            result = asyncio.run(classify(m["text"], "eval-tenant"))
            results.append({
                "text": m["text"][:60],
                "expected": m["expected_intent"],
                "actual": result.intent,
                "confidence": getattr(result, "confidence", None),
                "match": result.intent == m["expected_intent"],
            })

        # Compute stats
        total = len(results)
        correct = sum(1 for r in results if r["match"])
        accuracy = correct / total * 100
        logger.info("Classification accuracy: %.1f%% (%d/%d)", accuracy, correct, total)

        # Confidence distribution
        confidences = [r["confidence"] for r in results if r["confidence"] is not None]
        high_conf = sum(1 for c in confidences if c and c > 0.95)
        if confidences:
            logger.info("Confidence > 0.95: %d/%d (%.1f%%)", high_conf, len(confidences), high_conf / len(confidences) * 100)

        # Confusion matrix summary
        from collections import defaultdict
        confusion = defaultdict(lambda: defaultdict(int))
        for r in results:
            confusion[r["expected"]][r["actual"]] += 1

        logger.info("=== Confusion Matrix (expected -> actual) ===")
        for exp, actuals in sorted(confusion.items()):
            logger.info("  %s: %s", exp, dict(actuals))

        # Go/No-Go decision
        if confidences:
            high_conf_pct = high_conf / len(confidences) * 100
            logger.info("=== Go/No-Go Decision ===")
            logger.info("High confidence (>0.95): %.1f%%", high_conf_pct)
            if high_conf_pct > 30:
                logger.info("RECOMMENDATION: Implement rule-based classifier (T-3.5)")
            else:
                logger.info("RECOMMENDATION: Keep current LLM-based classifier")

        # Save report
        report_path = Path(__file__).parent / "classification_audit_report.json"
        import json as j
        report = {
            "total": total,
            "accuracy_pct": round(accuracy, 1),
            "high_confidence_pct": round(high_conf / len(confidences) * 100, 1) if confidences else 0,
            "intent_distribution": dict(Counter(r["actual"] for r in results)),
            "expected_distribution": dict(Counter(r["expected"] for r in results)),
            "go_for_rule_based": high_conf / len(confidences) > 0.3 if confidences else False,
        }
        report_path.write_text(j.dumps(report, indent=2), encoding="utf-8")
        logger.info("Report saved to %s", report_path)
