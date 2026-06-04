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


class TestFetchUrl:
    def test_empty_url_raises(self):
        with pytest.raises(ValueError, match="url is required"):
            fetch_url("")

    def test_non_200_raises(self):
        with patch("app.knowledge.url_extractor.httpx.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=404, headers={"content-type": "text/html"})
            with pytest.raises(ValueError, match="404"):
                fetch_url("https://example.com/missing")

    def test_401_raises_auth_error(self):
        with patch("app.knowledge.url_extractor.httpx.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=401, headers={"content-type": "text/html"})
            with pytest.raises(ValueError, match="Authentication required"):
                fetch_url("https://example.com/private")

    def test_timeout_raises(self):
        with patch("app.knowledge.url_extractor.httpx.get") as mock_get:
            mock_get.side_effect = httpx.TimeoutException("timed out")
            with pytest.raises(ValueError, match="timed out"):
                fetch_url("https://example.com/slow")

    def test_unsupported_content_type_raises(self):
        with patch("app.knowledge.url_extractor.httpx.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                headers={"content-type": "application/json"},
                text="{}",
            )
            with pytest.raises(ValueError, match="Unsupported content type"):
                fetch_url("https://example.com/data.json")

    def test_html_extraction_via_trafilatura(self):
        with patch("app.knowledge.url_extractor.httpx.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                headers={"content-type": "text/html"},
                text="<html><body><p>Hello world</p></body></html>",
            )
            with _mock_trafilatura("Hello world"):
                text, title = fetch_url("https://example.com")
                assert text == "Hello world"

    def test_html_extraction_fallback_to_bs4(self):
        with patch("app.knowledge.url_extractor.httpx.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                headers={"content-type": "text/html"},
                text="<html><body><p>Fallback content</p></body></html>",
            )
            with _mock_trafilatura(None):
                text, title = fetch_url("https://example.com")
                assert "Fallback content" in text

    def test_html_title_extraction(self):
        html = "<html><head><title>My Page</title></head><body><p>Content</p></body></html>"
        with patch("app.knowledge.url_extractor.httpx.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                headers={"content-type": "text/html"},
                text=html,
            )
            with _mock_trafilatura("Content"):
                _, title = fetch_url("https://example.com")
                assert title == "My Page"

    def test_plain_text_content_type(self):
        with patch("app.knowledge.url_extractor.httpx.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                headers={"content-type": "text/plain"},
                text="Just some plain text",
            )
            text, title = fetch_url("https://example.com/data.txt")
            assert text == "Just some plain text"
            assert title is None

    def test_pdf_url_via_content_type(self):
        with patch("app.knowledge.url_extractor.httpx.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                headers={"content-type": "application/pdf"},
                content=b"%PDF-1.4 junk",
            )
            with patch("pypdf.PdfReader") as mock_reader:
                mock_page = MagicMock()
                mock_page.extract_text.return_value = "PDF text content"
                mock_reader.return_value.pages = [mock_page]
                text, title = fetch_url("https://example.com/doc.pdf")
                assert "PDF text content" in text

    def test_network_error_raises(self):
        with patch("app.knowledge.url_extractor.httpx.get") as mock_get:
            mock_get.side_effect = httpx.RequestError("connection failed")
            with pytest.raises(ValueError, match="connection failed"):
                fetch_url("https://example.com")
