"""Document extraction and chunking for Jeeves RAG (Sprint 1).

Goals:
- Token-aware length budgeting via tiktoken (not char/4 heuristic).
- Structure-aware splitting: Markdown by heading hierarchy; PDF merged into one unit.
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
        segments: list[_Unit] = []
        for i, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if text:
                segments.append(_Unit(text=text, page=i + 1))
        if not segments:
            return [_Unit(text="")]
        if len(segments) == 1:
            return segments
        # Merge all pages into one unit — page boundaries are layout artifacts,
        # not semantic chunk boundaries. Chunk at paragraph/sentence level.
        merged_parts: list[str] = []
        for seg in segments:
            merged_parts.append(seg.text)
        return [_Unit(text="\n\n".join(merged_parts))]
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


# Public entry point --------------------------------------------------------
def build_chunks(path: Path) -> list[Chunk]:
    """Open a file, extract units, split into Chunk objects with metadata."""
    filename = path.name
    units = _extract_units(path)
    chunks: list[Chunk] = []

    for u in units:
        text = (u.text or "").strip()
        if not text:
            continue
        parts = _split_recursive(text)
        # Prepend section path to every chunk for richer embeddings + LLM context
        section_prefix = f"# {u.section}\n\n" if u.section else ""
        # Track char offsets inside the unit (approximate, for citations).
        cursor = 0
        for p in parts:
            idx = u.text.find(p, cursor)
            if idx < 0:
                idx = cursor
            start = idx
            end = idx + len(p)
            cursor = end
            chunk_text = section_prefix + p
            # Hard cap defence: if somehow a chunk is still too big, window it.
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
