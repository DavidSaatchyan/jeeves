from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Patterns that indicate elaborative/generative text not from KB
_KNOWN_HALLUCINATION_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:capital|largest|known for|famous for|located in|is a \w+ (?:city|state|country|hub))", re.IGNORECASE),
    re.compile(r"(?:skyline|landmark|iconic|Petronas|tropical rainforest climate|humidity|culinary scene)", re.IGNORECASE),
    re.compile(r"(?:modern skyline|shopping districts|historical landmarks)", re.IGNORECASE),
    re.compile(r"(?:also known as|commonly called|often referred to)", re.IGNORECASE),
    re.compile(r"(?:was discovered|was invented|was founded)", re.IGNORECASE),
]

# Skip phrases that are safe conversational elements
_SAFE_PHRASES: set[str] = {
    "thank you", "please", "your", "would", "medical emergency",
    "i don't have", "i'm sorry", "i am sorry", "here are", "the following",
    "available", "call your local", "this is", "yes", "no", "i can help",
    "let me know", "feel free", "you have", "based on", "according to",
    "the cost", "the price", "the service", "the procedure",
}


class GroundingResult:
    __slots__ = ("passed", "confidence", "failures", "ungrounded_entities")

    def __init__(
        self,
        passed: bool,
        confidence: float = 1.0,
        failures: list[str] | None = None,
        ungrounded_entities: list[str] | None = None,
    ) -> None:
        self.passed = passed
        self.confidence = confidence
        self.failures = failures or []
        self.ungrounded_entities = ungrounded_entities or []

    def __repr__(self) -> str:
        return (
            f"GroundingResult(passed={self.passed}, confidence={self.confidence:.2f}, "
            f"failures={len(self.failures)}, entities={self.ungrounded_entities})"
        )


def _build_context_index(context_chunks: list[dict]) -> str:
    """Build a single searchable text from all context chunks."""
    parts: list[str] = []
    for c in context_chunks:
        text = c.get("text", "") or ""
        section = c.get("section", "") or ""
        filename = c.get("filename", "") or ""
        parts.append(f"{section} {filename} {text}")
    return " ".join(parts).lower()


def _normalize(text: str) -> str:
    """Normalize text for comparison."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _extract_entities(text: str) -> list[str]:
    """Extract named entities (capitalized phrases) from answer text."""
    entities: list[str] = []
    # Multi-word capitalized phrases
    for m in re.finditer(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", text):
        entity = m.group(0).strip()
        if entity.lower() not in _SAFE_PHRASES and len(entity) > 3:
            entities.append(entity)
    # Single capitalized words that could be proper nouns (min 4 chars)
    for m in re.finditer(r"\b[A-Z][a-z]{3,}\b", text):
        word = m.group(0)
        if word.lower() not in _SAFE_PHRASES:
            entities.append(word)
    return list(set(entities))


def _extract_numbers(text: str) -> list[tuple[str, float]]:
    """Extract numeric claims like prices ($150), durations (5 min), counts."""
    results: list[tuple[str, float]] = []
    # Prices
    for m in re.finditer(r"\$\d+(?:,\d{3})*(?:\.\d{2})?", text):
        val = float(m.group(0).replace("$", "").replace(",", ""))
        results.append(("price", val))
    # Numbers with units
    for m in re.finditer(r"(\d+[-\s]?)(minute|minutes|min|hours?|days?|weeks?|months?|years?)", text, re.IGNORECASE):
        val = float(re.sub(r"[^\d]", "", m.group(1)))
        results.append(("duration", val))
    # Bare numbers that could be prices or counts
    for m in re.finditer(r"\b\d{2,4}\b", text):
        val = float(m.group(0))
        if 10 <= val <= 10000:
            results.append(("numeric", val))
    return results


def _check_location_elaboration(answer: str, context_text: str) -> list[str]:
    """Detect elaborative location descriptions not present in context."""
    failures: list[str] = []
    answer_lower = answer.lower()
    for pattern in _KNOWN_HALLUCINATION_PATTERNS:
        for m in pattern.finditer(answer_lower):
            fragment = answer[m.start():m.end()].strip()
            if fragment and fragment.lower() not in context_text:
                failures.append(f"Elaborative text: '{fragment}' not in context")
    return failures


def _check_entities_in_context(entities: list[str], context_text: str) -> list[str]:
    """Check that all named entities appear in context. Return ungrounded ones."""
    ungrounded: list[str] = []
    for entity in entities:
        entity_lower = entity.lower()
        # Check if entity appears directly or as part of a longer phrase
        if entity_lower not in context_text:
            # Check if entity is a known safe location/landmark that could be context
            ungrounded.append(entity)
    return ungrounded


def _check_numbers_in_context(numbers: list[tuple[str, float]], context_text: str) -> list[str]:
    """Check numeric claims against context. Prices and durations must match."""
    failures: list[str] = []
    for kind, val in numbers:
        val_str = f"{val:.0f}" if val == int(val) else f"{val:.2f}"
        if kind == "price":
            # Check if this price exists in context
            patterns = [f"${val_str}", f"${val:.2f}", f"${int(val)}"]
            if not any(p in context_text for p in patterns):
                failures.append(f"Price ${val_str} not found in context")
        elif kind == "duration":
            patterns = [f"{int(val)} min", f"{val_str} min", f"{int(val)} minute"]
            if not any(p in context_text for p in patterns):
                failures.append(f"Duration {int(val)} min not found in context")
        elif kind == "numeric":
            val_str_int = str(int(val))
            if val_str_int not in context_text:
                failures.append(f"Numeric value {int(val)} not found in context")
    return failures


def _extract_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]


def _check_each_sentence_grounded(answer: str, context_text: str) -> list[str]:
    """Check each sentence has at least some overlap with context."""
    failures: list[str] = []
    sentences = _extract_sentences(answer)
    for sent in sentences:
        sent_lower = sent.lower()
        if len(sent_lower) < 20:
            continue
        # Skip standard response templates
        if any(sent_lower.startswith(skip) for skip in ("i'm sorry", "i don't", "yes", "no", "here are", "the following", "thank", "please")):
            continue
        # Check for token overlap
        tokens = set(re.findall(r"\b[a-z]{4,}\b", sent_lower))
        if not tokens:
            continue
        context_tokens = set(re.findall(r"\b[a-z]{4,}\b", context_text))
        overlap = len(tokens & context_tokens)
        ratio = overlap / len(tokens) if tokens else 1.0
        if ratio < 0.3:
            failures.append(f"Sentence has low grounding ({ratio:.0%}): '{sent[:80]}...'")
    return failures


def validate_grounding(answer: str, context_chunks: list[dict]) -> GroundingResult:
    """Comprehensive grounding validation: entity check, number check, elaboration detection.

    Returns a GroundingResult with pass/fail, confidence score, and failure details.
    """
    if not answer or not context_chunks:
        return GroundingResult(passed=True, confidence=1.0)

    context_text = _build_context_index(context_chunks)
    failures: list[str] = []
    all_ungrounded: list[str] = []

    # 1. Entity grounding
    entities = _extract_entities(answer)
    if entities:
        ungrounded = _check_entities_in_context(entities, context_text)
        all_ungrounded.extend(ungrounded)
        if ungrounded:
            for e in ungrounded:
                failures.append(f"Entity '{e}' not found in context")
                logger.warning("Grounding: entity '%s' not in context", e)

    # 2. Numeric grounding (prices, durations)
    numbers = _extract_numbers(answer)
    if numbers:
        num_failures = _check_numbers_in_context(numbers, context_text)
        failures.extend(num_failures)
        for f in num_failures:
            logger.warning("Grounding: %s", f)

    # 3. Location elaboration check
    elaboration_issues = _check_location_elaboration(answer, context_text)
    failures.extend(elaboration_issues)
    for f in elaboration_issues:
        logger.warning("Grounding: %s", f)

    # 4. Sentence-level grounding
    sentence_issues = _check_each_sentence_grounded(answer, context_text)
    failures.extend(sentence_issues)

    # Compute confidence score
    if not failures:
        confidence = 1.0
    else:
        sentence_count = max(len(_extract_sentences(answer)), 1)
        confidence = max(0.0, 1.0 - (len(failures) / sentence_count))

    passed = len(failures) == 0

    return GroundingResult(
        passed=passed,
        confidence=confidence,
        failures=failures,
        ungrounded_entities=all_ungrounded,
    )
