"""Document extraction and chunking for Jeeves RAG (Sprint 2).

Goals:
- Token-aware length budgeting via tiktoken (not char/4 heuristic).
- Structure-aware splitting: Markdown by heading hierarchy; PDF by ALL CAPS headings.
- Rich per-chunk metadata: filename, section path, page, char offsets.
- Deterministic chunk IDs so re-indexing is idempotent.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")

    def _ntok(text: str) -> int:
        return len(_enc.encode(text, disallowed_special=()))
except Exception:
    # Fallback: char/4 heuristic. Keeps module importable if tiktoken missing.
    def _ntok(text: str) -> int:
        return max(1, len(text) // 4)


# Budgeting ----------------------------------------------------------------
MAX_TOKENS = 512         # target chunk size
MIN_TOKENS = 80          # below this we try to merge with neighbor
OVERLAP_TOKENS = 64      # overlap between adjacent sliding chunks
HARD_CAP_TOKENS = 1800   # never exceed — OpenAI embed input limit is 8191


@dataclass
class Chunk:
    text: str
    filename: str
    section: str = ""           # e.g. "Pricing > Business plan"
    page: int | None = None     # 1-based for PDFs
    char_start: int = 0
    char_end: int = 0
    chunk_hash: str = ""        # sha1 of text, stable across reindex

    def to_metadata(self, file_id: str) -> dict:
        # Chroma 0.5.x does not accept None in metadata values.
        m = {
            "file_id": file_id,
            "filename": self.filename,
            "section": self.section or "",
            "char_start": int(self.char_start),
            "char_end": int(self.char_end),
            "chunk_hash": self.chunk_hash,
        }
        if self.page is not None:
            m["page"] = int(self.page)
        return m


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


# Extraction ---------------------------------------------------------------
@dataclass
class _Unit:
    """A raw block of text with optional page + section hints, pre-chunking."""
    text: str
    page: int | None = None
    section: str = ""


def _extract_units(path: Path) -> list[_Unit]:
    ext = path.suffix.lower()
    if ext in {".txt"}:
        return [_Unit(text=path.read_text(encoding="utf-8", errors="ignore"))]
    if ext == ".md":
        return _md_units(path.read_text(encoding="utf-8", errors="ignore"))
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        pages_text: list[str] = []
        for i, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if text:
                pages_text.append(text)
        if not pages_text:
            return [_Unit(text="")]
        merged = "\n\n".join(pages_text)
        return _pdf_units(merged)
    raise ValueError(f"Unsupported file type: {ext}")


# Markdown heading-aware splitter ------------------------------------------
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _md_units(text: str) -> list[_Unit]:
    """Split markdown into units anchored at headings; carry H1>H2>H3 path."""
    lines = text.splitlines()
    units: list[_Unit] = []
    stack: list[str] = []   # current heading path (per level)
    buf: list[str] = []

    def flush():
        if not buf:
            return
        body = "\n".join(buf).strip()
        if body:
            units.append(_Unit(text=body, section=" > ".join(s for s in stack if s)))
        buf.clear()

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            flush()
            level = len(m.group(1))
            title = m.group(2).strip()
            # truncate stack to level-1, then set current level
            while len(stack) >= level:
                stack.pop()
            while len(stack) < level - 1:
                stack.append("")
            stack.append(title)
        else:
            buf.append(line)
    flush()
    return units or [_Unit(text=text)]


# PDF heading-aware splitter -------------------------------------------------
# Page boundaries are layout artifacts — merge first, then detect structure.
# Heuristic: lines that are ≥70% uppercase alpha, 2–80 chars, not bullet items,
# and contain at least one letter, are treated as section headings.


def _is_heading(line: str) -> bool:
    st = line.strip()
    if len(st) < 2 or len(st) > 80:
        return False
    if st.startswith(("•", "-", "*", "→", "▪", "●", "○", "§")):
        return False
    alpha = [c for c in st if c.isalpha()]
    if len(alpha) < 2:
        return False
    upper = sum(1 for c in alpha if c.isupper())
    return upper / len(alpha) >= 0.7


def _pdf_units(text: str) -> list[_Unit]:
    """Split merged PDF text into units anchored at section headings."""
    lines = text.splitlines()
    units: list[_Unit] = []
    cur_section = ""
    buf: list[str] = []

    def flush():
        if not buf:
            return
        body = "\n".join(buf).strip()
        if body:
            units.append(_Unit(text=body, section=cur_section))
        buf.clear()

    for line in lines:
        if _is_heading(line):
            flush()
            cur_section = line.strip()
        else:
            buf.append(line)
    flush()
    return units or [_Unit(text=text)]


# Recursive token-aware splitter for a single unit -------------------------
_PARA_SPLIT = re.compile(r"\n\s*\n+")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZА-ЯЁ0-9])")


def _split_recursive(text: str) -> list[str]:
    """Return chunks respecting MAX_TOKENS, splitting at the coarsest
    natural boundary that fits (paragraphs → sentences → hard window)."""
    text = text.strip()
    if not text:
        return []
    if _ntok(text) <= MAX_TOKENS:
        return [text]

    # Paragraphs
    parts = _PARA_SPLIT.split(text)
    if len(parts) > 1:
        return _pack(parts, separator="\n\n")

    # Sentences
    parts = _SENT_SPLIT.split(text)
    if len(parts) > 1:
        return _pack(parts, separator=" ")

    # Hard token window with overlap
    return _token_window(text)


def _pack(parts: Iterable[str], separator: str) -> list[str]:
    """Greedy pack `parts` into MAX_TOKENS-sized chunks."""
    chunks: list[str] = []
    cur: list[str] = []
    cur_tok = 0
    for p in parts:
        p = p.strip()
        if not p:
            continue
        p_tok = _ntok(p)
        if p_tok > MAX_TOKENS:
            # part itself too big — flush, then split recursively
            if cur:
                chunks.append(separator.join(cur))
                cur = []
                cur_tok = 0
            chunks.extend(_split_recursive(p))
            continue
        if cur_tok + p_tok > MAX_TOKENS and cur:
            chunks.append(separator.join(cur))
            cur, cur_tok = [], 0
        cur.append(p)
        cur_tok += p_tok
    if cur:
        chunks.append(separator.join(cur))
    return chunks


def _token_window(text: str) -> list[str]:
    """Last-resort hard window over tokens with overlap. Uses tiktoken if
    available, else falls back to char window calibrated to MAX_TOKENS*4."""
    try:
        toks = _enc.encode(text, disallowed_special=())
        out = []
        step = MAX_TOKENS - OVERLAP_TOKENS
        for i in range(0, len(toks), step):
            piece = _enc.decode(toks[i : i + MAX_TOKENS])
            out.append(piece)
            if i + MAX_TOKENS >= len(toks):
                break
        return out
    except Exception:
        step = (MAX_TOKENS - OVERLAP_TOKENS) * 4
        win = MAX_TOKENS * 4
        return [text[i : i + win] for i in range(0, len(text), step)]


# Text-based heading detection (for URL-extracted clean text) ---------------
def _text_units(text: str, default_section: str = "") -> list[_Unit]:
    """Split clean text into units at heading-like lines.

    Detects:
      - ALL CAPS headings (via _is_heading)
      - Short lines starting with uppercase, not ending with sentence punctuation
    """
    lines = text.splitlines()
    units: list[_Unit] = []
    cur_section = default_section
    buf: list[str] = []

    def flush():
        if buf:
            body = "\n".join(buf).strip()
            if body:
                units.append(_Unit(text=body, section=cur_section))
            buf.clear()

    for line in lines:
        stripped = line.strip()
        if _is_heading(stripped):
            flush()
            cur_section = stripped
        elif (stripped and len(stripped) < 80 and stripped[0].isupper()
              and not stripped.endswith((".", ":", ";", ",", "!"))
              and not stripped.startswith(("•", "-", "*", "→", "▪", "●", "○", "§", "|", "!", '"', "'", "(", "["))
              and sum(1 for c in stripped if c.isalpha()) > 2):
            flush()
            cur_section = stripped
        else:
            buf.append(line)
    flush()
    return units or [_Unit(text=text, section=default_section)]


# Public entry points -------------------------------------------------------
def build_chunks(path: Path) -> list[Chunk]:
    """Open a file, extract units, split into Chunk objects with metadata."""
    return _build_chunks_from_units(_extract_units(path), path.name)


def build_chunks_from_text(text: str, filename: str, section: str = "") -> list[Chunk]:
    """Split raw text into Chunk objects — detects headings to match file behaviour."""
    return _build_chunks_from_units(_text_units(text, section), filename)


def _build_chunks_from_units(units: list[_Unit], filename: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for u in units:
        text = (u.text or "").strip()
        if not text:
            continue
        parts = _split_recursive(text)
        section_prefix = f"# {u.section}\n\n" if u.section else ""
        cursor = 0
        for p in parts:
            idx = u.text.find(p, cursor)
            if idx < 0:
                idx = cursor
            start = idx
            end = idx + len(p)
            cursor = end
            chunk_text = section_prefix + p
            if _ntok(chunk_text) > HARD_CAP_TOKENS:
                for w in _token_window(p):
                    wt = section_prefix + w
                    chunks.append(Chunk(
                        text=wt, filename=filename, section=u.section, page=u.page,
                        char_start=start, char_end=start + len(w), chunk_hash=_hash(wt),
                    ))
                continue
            chunks.append(Chunk(
                text=chunk_text, filename=filename, section=u.section, page=u.page,
                char_start=start, char_end=end, chunk_hash=_hash(chunk_text),
            ))
    return chunks


# File-level helpers --------------------------------------------------------
def sanitize_filename(name: str) -> str:
    """Strip any path components and characters that could enable traversal.

    Keeps only the basename; replaces anything outside a safe alphabet."""
    if not name:
        return "unnamed"
    base = Path(name.replace("\\", "/")).name  # drops POSIX and Windows dirs
    safe = re.sub(r"[^A-Za-z0-9._\- ]+", "_", base).strip().strip(".")
    return safe or "unnamed"


def file_sha256(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()
