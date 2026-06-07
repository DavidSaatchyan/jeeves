"""Standalone baseline eval — indexes synthetic data, runs RAGAS eval, saves baseline."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Point config to the real config.yaml before any app imports
_BASE = Path(__file__).resolve().parent.parent
os.environ.setdefault("CONFIG_PATH", str(_BASE / "app" / "config.yaml"))
os.environ.setdefault("KNOWLEDGE_DIR", str(_BASE / "tests" / "synthetic_kb"))
os.environ.setdefault("CHROMA_PATH", str(_BASE / ".chroma_eval"))

# Load .env so ragas can find OPENAI_API_KEY
_env_path = _BASE / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

from app.agents.default_config import get_default_agent_config
from app.rag import index_file, index_text, delete_file
from tests.eval_runner import run_eval
from tests.golden_dataset import load_dataset, GoldenSample
from app.core.eval import RAGEvaluator


SYNTHETIC_KB = Path(__file__).parent / "synthetic_kb"
SYNTHETIC_PMS = Path(__file__).parent / "synthetic_pms"
GOLDEN_DATASET = Path(__file__).parent / "golden_dataset.jsonl"
BASELINE_OUT = Path(__file__).parent / "rag_baseline.json"

TENANT_ID = "00000000-0000-0000-0000-000000000001"


async def _index_synthetic() -> None:
    """Index all synthetic KB docs and PMS data into Chroma."""
    loaded: list[str] = []

    for fpath in sorted(SYNTHETIC_KB.iterdir()):
        if fpath.suffix not in (".txt", ".md"):
            continue
        fid = f"synthetic-{fpath.stem}"
        try:
            delete_file(TENANT_ID, fid)
        except Exception:
            pass
        index_file(TENANT_ID, fid, fpath)
        loaded.append(fid)
        print(f"  indexed KB: {fpath.name}")

    for fpath in sorted(SYNTHETIC_PMS.iterdir()):
        if fpath.suffix not in (".txt",):
            continue
        fid = f"synthetic-pms-{fpath.stem}"
        try:
            delete_file(TENANT_ID, fid)
        except Exception:
            pass
        text = fpath.read_text(encoding="utf-8")
        index_text(TENANT_ID, fid, text, fpath.name, section="Pricing")
        loaded.append(fid)
        print(f"  indexed PMS: {fpath.name}")

    print(f"  total indexed: {len(loaded)} files")


async def main() -> None:
    print("=== Baseline RAG Evaluation ===")
    print()

    # 1. Load golden dataset
    print("1. Loading golden dataset...")
    samples = load_dataset(GOLDEN_DATASET)
    print(f"   {len(samples)} samples loaded")

    # 2. Index synthetic data
    print("2. Indexing synthetic data into Chroma...")
    await _index_synthetic()

    # 3. Run eval
    print("3. Running evaluation...")
    agent_config = get_default_agent_config()
    evaluator = RAGEvaluator()

    result = await run_eval(samples, TENANT_ID, agent_config, evaluator)

    print()
    print("=== Results ===")
    for k, v in result.items():
        if k == "num_samples":
            print(f"  Samples: {v}")
        else:
            print(f"  {k}: {v:.4f}" if v is not None else f"  {k}: N/A")

    # 4. Save baseline
    from app.core.eval import EvalResult
    r = EvalResult(
        faithfulness=result.get("faithfulness"),
        answer_relevancy=result.get("answer_relevancy"),
        context_precision=result.get("context_precision"),
        context_recall=result.get("context_recall"),
    )
    evaluator.save_baseline(r, BASELINE_OUT)
    print(f"\nBaseline saved to: {BASELINE_OUT}")


if __name__ == "__main__":
    asyncio.run(main())
