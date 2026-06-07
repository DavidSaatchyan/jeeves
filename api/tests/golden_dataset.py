from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GoldenSample:
    query: str
    reference_answer: str
    source_type: str  # kb | hms | general
    language: str       # en | de | fr | es | it
    specialty: str
    difficulty: str     # easy | medium | hard
    applicable_specialties: list[str] = field(default_factory=lambda: ["*"])
    requires_doc: str | None = None


def load_dataset(path: Path) -> list[GoldenSample]:
    samples: list[GoldenSample] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            samples.append(GoldenSample(**data))
    return samples


def filter_by_specialty(samples: list[GoldenSample], specialty: str) -> list[GoldenSample]:
    return [
        s for s in samples
        if "*" in s.applicable_specialties or specialty in s.applicable_specialties
    ]
