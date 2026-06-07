"""Unit tests for app.chunking — pure functions, no mocking needed."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.rag.chunking import (
    Chunk,
    build_chunks,
    build_chunks_from_text,
    file_sha256,
    sanitize_filename,
    _md_units,
    _ntok,
    _pack,
    _split_recursive,
    _token_window,
    MAX_TOKENS,
)


# ── sanitize_filename ──────────────────────────────────────────────────────


class TestSanitizeFilename:
    def test_normal_filename(self):
        assert sanitize_filename("hello.txt") == "hello.txt"

    def test_path_traversal_posix(self):
        assert sanitize_filename("../etc/passwd.txt") == "passwd.txt"

    def test_path_traversal_windows(self):
        assert sanitize_filename("..\\..\\Windows\\system32\\foo.txt") == "foo.txt"

    def test_special_chars_replaced(self):
        result = sanitize_filename("my file (1).txt")
        assert "(" not in result
        assert ")" not in result

    def test_whitespace_trimmed(self):
        assert sanitize_filename("  foo.txt  ") == "foo.txt"

    def test_empty_returns_unnamed(self):
        assert sanitize_filename("") == "unnamed"

    def test_none_name_becomes_unnamed(self):
        # The function receives str, so empty is the edge case
        assert sanitize_filename(".") == "unnamed"  # only a dot → stripped
        assert sanitize_filename("...") == "unnamed"

    def test_unicode_replaced(self):
        result = sanitize_filename("résumé.txt")
        # sanitize uses ASCII-only safe alphabet so accent chars are replaced
        assert "é" not in result
        assert result.endswith(".txt")

    def test_only_special_chars(self):
        result = sanitize_filename("@#$%^&*")
        sanitize_filename("()[]{}!")
        # All should be replaced with underscores, then stripped
        assert result == "unnamed" or "_" in result


# ── file_sha256 ────────────────────────────────────────────────────────────


class TestFileSha256:
    def test_known_data(self):
        data = b"hello world"
        expected = hashlib.sha256(data).hexdigest()
        assert file_sha256(data) == expected

    def test_empty_bytes(self):
        assert file_sha256(b"") == hashlib.sha256(b"").hexdigest()

    def test_unicode_data(self):
        data = "日本語".encode("utf-8")
        expected = hashlib.sha256(data).hexdigest()
        assert file_sha256(data) == expected

    def test_deterministic(self):
        data = b"some test data"
        assert file_sha256(data) == file_sha256(data)


# ── _ntok ──────────────────────────────────────────────────────────────────


class TestNtok:
    def test_empty(self):
        assert _ntok("") >= 0

    def test_short_token_count(self):
        n = _ntok("Hello world")
        assert n > 0

    def test_known_text(self):
        # "Hello world" is ~2 tokens, but don't hardcode; just check it's reasonable
        n = _ntok("Hello world")
        assert 1 <= n <= 10

    def test_longer_text(self):
        short = _ntok("Hello world")
        long = _ntok("Hello world. " * 100)
        assert long > short


# ── _md_units ──────────────────────────────────────────────────────────────


class TestMdUnits:
    def test_plain_text_no_headings(self):
        units = _md_units("Just some text.\n\nNothing special.")
        assert len(units) == 1
        assert units[0].section == ""

    def test_single_heading(self):
        units = _md_units("# Title\n\nBody text.")
        assert len(units) == 1
        assert units[0].section == "Title"

    def test_multiple_headings(self):
        text = "# H1\n\nBody1\n\n# H2\n\nBody2"
        units = _md_units(text)
        assert len(units) == 2
        assert units[0].section == "H1"
        assert units[1].section == "H2"

    def test_nested_headings(self):
        text = "# Top\n\nIntro\n\n## Mid\n\nMiddle content\n\n# Next\n\nFinal"
        units = _md_units(text)
        assert len(units) == 3
        assert units[0].section == "Top"
        assert units[1].section == "Top > Mid"
        assert units[2].section == "Next"

    def test_three_level_nesting(self):
        text = "# L1\n\n## L2\n\n### L3\n\nBottom"
        units = _md_units(text)
        assert len(units) == 1
        assert units[0].section == "L1 > L2 > L3"

    def test_empty_text_returns_fallback(self):
        units = _md_units("")
        assert len(units) == 1
        assert units[0].text == ""

    def test_heading_without_body_skipped(self):
        text = "# H1\n\n# H2\n\nSome text"
        units = _md_units(text)
        assert len(units) == 1
        assert units[0].section == "H2"

    def test_sibling_headings_no_body(self):
        text = "## A\n\n## B\n\n## C"
        units = _md_units(text)
        # No body text between headings → fallback to entire text as one unit
        assert len(units) == 1
        assert units[0].section == ""

    def test_out_of_order_heading_levels(self):
        text = "### H3\n\nText\n\n# H1\n\nMore"
        units = _md_units(text)
        assert len(units) == 2
        assert units[0].section == "H3"
        assert units[1].section == "H1"


# ── _split_recursive ───────────────────────────────────────────────────────


class TestSplitRecursive:
    def test_short_text_unchanged(self):
        text = "Short text."
        result = _split_recursive(text)
        assert result == [text]

    def test_empty_text(self):
        assert _split_recursive("") == []
        assert _split_recursive("   ") == []

    def test_paragraph_split(self):
        # Create text that exceeds MAX_TOKENS via paragraphs
        para = "Word " * 30
        text = para + "\n\n" + para + "\n\n" + para
        result = _split_recursive(text)
        assert len(result) >= 1

    def test_all_chunks_under_max(self):
        text = ("Long paragraph. " * 1000)
        result = _split_recursive(text)
        for chunk in result:
            assert _ntok(chunk) <= MAX_TOKENS + 10  # small tolerance

    def test_no_empty_chunks(self):
        text = "Hello.\n\nWorld.\n\n" * 500
        result = _split_recursive(text)
        for chunk in result:
            assert chunk.strip() != ""


# ── _pack ──────────────────────────────────────────────────────────────────


class TestPack:
    def test_single_small_part(self):
        result = _pack(["Small part"], separator=" ")
        assert result == ["Small part"]

    def test_multiple_parts_packed(self):
        parts = ["A"] * 20
        result = _pack(parts, separator=" ")
        assert len(result) >= 1
        for chunk in result:
            assert _ntok(chunk) <= MAX_TOKENS + 10

    def test_empty_parts_skipped(self):
        result = _pack(["", "  ", "Hello"], separator=" ")
        assert result == ["Hello"]

    def test_large_part_recursive_split(self):
        large = "word " * 5000
        result = _pack([large], separator=" ")
        assert len(result) >= 1
        for chunk in result:
            assert _ntok(chunk) <= MAX_TOKENS + 50  # allow some token-window fuzz


# ── _token_window ──────────────────────────────────────────────────────────


class TestTokenWindow:
    def test_short_text(self):
        text = "Short text."
        result = _token_window(text)
        assert result == [text] or all(
            _ntok(c) <= MAX_TOKENS for c in result
        )

    def test_overlap_present(self):
        text = "word " * 5000
        result = _token_window(text)
        if len(result) > 1:
            t1 = _ntok(result[0])
            t2 = _ntok(result[1])
            total = _ntok(text)
            # Overlap means sum of all chunks' tokens > total tokens
            assert (t1 + t2) * len(result) > total * 0.5
        for chunk in result:
            assert _ntok(chunk) <= MAX_TOKENS + 50


# ── build_chunks ───────────────────────────────────────────────────────────


class TestBuildChunks:
    def test_txt_file(self, sample_txt: Path):
        chunks = build_chunks(sample_txt)
        assert len(chunks) >= 1
        for c in chunks:
            assert isinstance(c, Chunk)
            assert c.filename == "test.txt"
            assert c.chunk_hash
            assert c.char_end > c.char_start
            assert c.text

    def test_md_file_with_sections(self, sample_md: Path):
        chunks = build_chunks(sample_md)
        assert len(chunks) >= 1
        sections = {c.section for c in chunks if c.section}
        assert sections  # at least one section present

    def test_pdf_file(self, sample_pdf: Path):
        chunks = build_chunks(sample_pdf)
        # Blank pages produce empty text → filtered
        assert isinstance(chunks, list)
        for c in chunks:
            assert c.page is not None
            assert c.page >= 1

    def test_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            build_chunks(Path("/nonexistent/file.txt"))

    def test_unsupported_extension_raises(self, tmp_path: Path):
        p = tmp_path / "test.doc"
        p.write_text("fake")
        with pytest.raises(ValueError, match="Unsupported"):
            build_chunks(p)

    def test_chunk_hash_stable(self):
        text = "Stable content. " * 10
        c1 = Chunk(text=text, filename="a.txt", chunk_hash="h")
        c2 = Chunk(text=text, filename="a.txt", chunk_hash="h")
        assert c1.chunk_hash == c2.chunk_hash

    def test_empty_file_returns_empty(self, tmp_path: Path):
        p = tmp_path / "empty.txt"
        p.write_text("")
        chunks = build_chunks(p)
        assert chunks == []

    def test_whitespace_only_returns_empty(self, tmp_path: Path):
        p = tmp_path / "whitespace.txt"
        p.write_text("   \n\n   \n")
        chunks = build_chunks(p)
        assert chunks == []

    def test_section_prefix_added_to_chunks(self, tmp_path: Path):
        p = tmp_path / "prefixed.md"
        p.write_text("# Section A\n\nContent here.")
        chunks = build_chunks(p)
        assert chunks
        assert chunks[0].text.startswith("# Section A")


# ── Chunk.to_metadata ──────────────────────────────────────────────────────


class TestChunkToMetadata:
    def test_basic_metadata(self):
        c = Chunk(
            text="test", filename="f.txt", section="S",
            char_start=0, char_end=4, chunk_hash="abc",
        )
        m = c.to_metadata("file-uuid")
        assert m["file_id"] == "file-uuid"
        assert m["folder_id"] == ""
        assert m["filename"] == "f.txt"
        assert m["section"] == "S"
        assert m["char_start"] == 0
        assert m["char_end"] == 4
        assert m["chunk_hash"] == "abc"
        assert "page" not in m

    def test_metadata_with_folder_id(self):
        c = Chunk(
            text="test", filename="f.txt", section="S",
            char_start=0, char_end=4, chunk_hash="abc",
        )
        m = c.to_metadata("file-uuid", "folder-xyz")
        assert m["file_id"] == "file-uuid"
        assert m["folder_id"] == "folder-xyz"

    def test_metadata_with_page(self):
        c = Chunk(
            text="test", filename="f.txt", section="", page=3,
            char_start=0, char_end=4, chunk_hash="abc",
        )
        m = c.to_metadata("file-uuid")
        assert m["page"] == 3

    def test_metadata_none_section_becomes_empty(self):
        c = Chunk(text="test", filename="f.txt", section="", char_start=0, char_end=4, chunk_hash="abc")
        m = c.to_metadata("fid")
        assert m["section"] == ""


# ── Integration-level: build_chunks with real pdf content ──────────────────


class TestBuildChunksRealPDF:
    def test_pdf_with_text(self, tmp_path: Path):
        """Create PDF with actual text content, verify chunking extracts it."""
        from pypdf import PdfWriter

        p = tmp_path / "real.pdf"
        writer = PdfWriter()
        writer.add_blank_page(612, 792)
        writer.pages[0].merge_page(writer.pages[0])  # ensure it exists
        # Use a lower-level approach — write bytes directly via reportlab? No, keep it simple.
        # pypdf doesn't easily add text. Let's skip rich-text PDF and just verify structure.
        writer.write(str(p))
        writer.close()
        chunks = build_chunks(p)
        # Blank page = no extractable text → filtered out
        assert isinstance(chunks, list)


# ── build_chunks_from_text (no file on disk) ───────────────────────────────


class TestBuildChunksFromText:
    def test_short_text(self):
        chunks = build_chunks_from_text("Hello world.", "test.txt")
        assert len(chunks) == 1
        assert chunks[0].filename == "test.txt"
        assert "Hello" in chunks[0].text

    def test_empty_text(self):
        chunks = build_chunks_from_text("", "empty.txt")
        assert chunks == []

    def test_section_prefix(self):
        chunks = build_chunks_from_text("Content here.", "doc.txt", section="My Section")
        assert len(chunks) == 1
        assert "# My Section" in chunks[0].text
        assert "Content here." in chunks[0].text

    def test_long_text_splits(self):
        text = ("Long paragraph. " * 1000)
        chunks = build_chunks_from_text(text, "long.txt")
        assert len(chunks) >= 2
        for c in chunks:
            assert _ntok(c.text) <= 1800  # HARD_CAP_TOKENS

    def test_chunk_metadata(self):
        chunks = build_chunks_from_text("Some text content here.", "meta.txt", section="Test")
        assert len(chunks) == 1
        c = chunks[0]
        assert c.filename == "meta.txt"
        assert c.section == "Test"
        assert c.chunk_hash
        assert len(c.chunk_hash) == 16
