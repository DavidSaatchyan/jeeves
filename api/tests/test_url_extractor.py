"""Tests for app.knowledge.url_extractor — HTTP fetch + HTML extraction."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.knowledge.url_extractor import fetch_url


def _mock_trafilatura(extract_return: str | None = None):
    """Add a mock trafilatura module to sys.modules so lazy import resolves."""
    m = MagicMock()
    m.extract.return_value = extract_return
    return patch.dict("sys.modules", {"trafilatura": m})


class _MockStreamResponse:
    """Plain class mimicking httpx streaming response — no AsyncMock issues."""

    def __init__(self, status_code=200, headers=None, content=b""):
        self.status_code = status_code
        self.headers = headers or {"content-type": "text/html"}
        self._content = content

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def aiter_bytes(self):
        yield self._content


def _mock_client(stream_resp):
    """Build a mock for httpx.AsyncClient that returns stream_resp from .stream()."""
    client = MagicMock()
    client.__aenter__.return_value = client
    client.stream.return_value = stream_resp
    return client


@pytest.mark.asyncio
class TestFetchUrl:
    async def test_empty_url_raises(self):
        with pytest.raises(ValueError, match="url is required"):
            await fetch_url("")

    async def test_404_raises(self):
        resp = _MockStreamResponse(status_code=404)
        with patch("httpx.AsyncClient", return_value=_mock_client(resp)):
            with pytest.raises(ValueError, match="404"):
                await fetch_url("https://example.com/missing")

    async def test_timeout_raises(self):
        client = MagicMock()
        client.__aenter__.return_value = client
        client.stream.side_effect = httpx.TimeoutException("timed out")
        with patch("httpx.AsyncClient", return_value=client):
            with pytest.raises(ValueError, match="timed out"):
                await fetch_url("https://example.com/slow")

    async def test_request_error_raises(self):
        client = MagicMock()
        client.__aenter__.return_value = client
        client.stream.side_effect = httpx.RequestError("connection reset")
        with patch("httpx.AsyncClient", return_value=client):
            with pytest.raises(ValueError, match="connection reset"):
                await fetch_url("https://example.com/broken")

    async def test_401_raises_auth_error(self):
        resp = _MockStreamResponse(status_code=401)
        with patch("httpx.AsyncClient", return_value=_mock_client(resp)):
            with pytest.raises(ValueError, match="Authentication required"):
                await fetch_url("https://example.com/private")

    async def test_unsupported_content_type_raises(self):
        resp = _MockStreamResponse(headers={"content-type": "application/json"})
        with patch("httpx.AsyncClient", return_value=_mock_client(resp)):
            with pytest.raises(ValueError, match="Unsupported content type"):
                await fetch_url("https://example.com/data.json")

    async def test_html_extraction_via_trafilatura(self):
        resp = _MockStreamResponse(content=b"<html><body><p>Hello world</p></body></html>")
        with patch("httpx.AsyncClient", return_value=_mock_client(resp)):
            with _mock_trafilatura("Hello world"):
                text, title = await fetch_url("https://example.com")
                assert text == "Hello world"

    async def test_html_extraction_fallback_to_bs4(self):
        resp = _MockStreamResponse(content=b"<html><body><p>Fallback content</p></body></html>")
        with patch("httpx.AsyncClient", return_value=_mock_client(resp)):
            with _mock_trafilatura(None):
                text, title = await fetch_url("https://example.com")
                assert "Fallback content" in text

    async def test_html_title_extraction(self):
        html = "<html><head><title>My Page</title></head><body><p>Content</p></body></html>"
        resp = _MockStreamResponse(content=html.encode())
        with patch("httpx.AsyncClient", return_value=_mock_client(resp)):
            with _mock_trafilatura("Content"):
                _, title = await fetch_url("https://example.com")
                assert title == "My Page"

    async def test_plain_text_content_type(self):
        resp = _MockStreamResponse(
            headers={"content-type": "text/plain"},
            content=b"Just some plain text",
        )
        with patch("httpx.AsyncClient", return_value=_mock_client(resp)):
            text, title = await fetch_url("https://example.com/data.txt")
            assert text == "Just some plain text"
            assert title is None

    async def test_pdf_url_via_content_type(self):
        resp = _MockStreamResponse(
            headers={"content-type": "application/pdf"},
            content=b"%PDF-1.4 junk",
        )
        with patch("httpx.AsyncClient", return_value=_mock_client(resp)):
            with patch("pypdf.PdfReader") as mock_reader:
                mock_page = MagicMock()
                mock_page.extract_text.return_value = "PDF text content"
                mock_reader.return_value.pages = [mock_page]
                text, title = await fetch_url("https://example.com/doc.pdf")
                assert "PDF text content" in text

    async def test_body_truncation(self):
        from app.knowledge.url_extractor import MAX_BODY_BYTES
        big = b"x" * (MAX_BODY_BYTES + 100_000)
        resp = _MockStreamResponse(
            headers={"content-type": "text/plain"},
            content=big,
        )
        with patch("httpx.AsyncClient", return_value=_mock_client(resp)):
            text, _ = await fetch_url("https://example.com/big")
            assert len(text) <= MAX_BODY_BYTES
