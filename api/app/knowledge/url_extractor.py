"""Fetch and extract readable text from URLs for knowledge base ingestion."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 2_000_000
MAX_EXTRACTED_CHARS = 500_000


async def fetch_url(url: str) -> tuple[str, str | None]:
    """Fetch a URL and extract clean text + optional title.

    Body is streamed with a MAX_BODY_BYTES cap to avoid OOM on large pages.
    Returns (cleaned_text, title_or_None).
    Raises ValueError on non-200, timeouts, unsupported content types.
    """
    if not url.strip():
        raise ValueError("url is required")

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            async with client.stream("GET", url) as resp:
                status = resp.status_code
                if status == 404:
                    raise ValueError("Page not found (404)")
                if status in (401, 403):
                    raise ValueError("Authentication required (the page is behind a login)")
                if status != 200:
                    raise ValueError(f"HTTP {status}")

                content_type = (resp.headers.get("content-type") or "").lower()
                is_pdf = "application/pdf" in content_type or url.rstrip("/").lower().endswith(".pdf")
                is_text = "text/plain" in content_type
                is_html = "text/html" in content_type or "application/xhtml" in content_type

                if not is_pdf and not is_text and not is_html:
                    raise ValueError(f"Unsupported content type: {content_type}")

                # Stream body with size cap
                raw = b""
                async for chunk in resp.aiter_bytes():
                    raw += chunk
                    if len(raw) > MAX_BODY_BYTES:
                        break

    except httpx.TimeoutException:
        raise ValueError("Request timed out")
    except httpx.RequestError as e:
        raise ValueError(f"Request failed: {e}")

    if is_pdf:
        return _extract_pdf_url(raw)
    body = raw.decode("utf-8", errors="replace")[:MAX_EXTRACTED_CHARS * 4]
    if is_text:
        return body[:MAX_EXTRACTED_CHARS], None
    return _extract_html(body, url)


def _extract_html(html: str, url: str) -> tuple[str, str | None]:
    """Extract clean text and title from HTML using trafilatura + bs4 fallback."""
    text: str | None = None
    title: str | None = None

    # Primary: trafilatura for main-content extraction
    try:
        import trafilatura
        text = trafilatura.extract(
            html,
            url=url,
            output_format="txt",
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
    except Exception:
        logger.warning("trafilatura extract failed, falling back to bs4", exc_info=True)

    # Fallback: bs4 manual stripping
    if not text:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
        except Exception:
            raise ValueError("Failed to extract text from HTML")

    # Extract title
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        t = soup.find("title")
        if t and t.get_text(strip=True):
            title = t.get_text(strip=True)
    except Exception:
        pass

    text = text.strip()
    if not text:
        raise ValueError("No readable content found at this URL")

    if len(text) > MAX_EXTRACTED_CHARS:
        text = text[:MAX_EXTRACTED_CHARS]

    return text, title


def _extract_pdf_url(data: bytes) -> tuple[str, str | None]:
    """Download PDF content and extract text via pypdf."""
    from pypdf import PdfReader
    import io
    try:
        reader = PdfReader(io.BytesIO(data))
        pages: list[str] = []
        for page in reader.pages:
            t = (page.extract_text() or "").strip()
            if t:
                pages.append(t)
        if not pages:
            raise ValueError("No text found in PDF")
        text = "\n\n".join(pages)
        if len(text) > MAX_EXTRACTED_CHARS:
            text = text[:MAX_EXTRACTED_CHARS]
        return text, None
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Failed to parse PDF: {e}")
