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


def _extract_html_structured(html: str, url: str) -> tuple[str, list[tuple[str, str]]]:
    """Extract structured (heading, body) sections from HTML.

    Strategy:
    1. Use trafilatura HTML output to get clean main content (boilerplate removed).
    2. Parse with bs4 to identify heading tags (h1-h6) and group content under them.
    3. If trafilatura unavailable or fails, parse raw HTML with bs4 directly.

    No heuristics — relies on semantic HTML heading structure.
    Returns (page_title, [(heading_text, body_text), ...]).
    """
    page_title = ""
    clean_html: str | None = None

    # Step 1 — try trafilatura HTML output for clean main content
    try:
        import trafilatura
        raw = trafilatura.extract(
            html, url=url, output_format="html",
            include_comments=False, include_tables=True, no_fallback=False,
        )
        if raw:
            clean_html = raw
    except ImportError:
        pass
    except Exception:
        logger.warning("trafilatura HTML extract failed", exc_info=True)

    # Step 2 — parse with bs4
    from bs4 import BeautifulSoup, Tag

    soup = BeautifulSoup(clean_html or html, "lxml")

    if clean_html:
        # Extract title from original HTML (trafilatura HTML output omits <title>)
        try:
            src = BeautifulSoup(html, "lxml")
            t = src.find("title")
            if t and t.get_text(strip=True):
                page_title = t.get_text(strip=True)
        except Exception:
            pass
    else:
        # Fallback: manually strip boilerplate from raw HTML
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()
        t = soup.find("title")
        if t and t.get_text(strip=True):
            page_title = t.get_text(strip=True)

    # Step 3 — walk content children grouping by heading tags
    # Walk the tree manually to avoid processing both a container
    # (e.g. <blockquote>) and its children (<p>), which duplicates text.
    _BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "pre"}

    def _collect_blocks(root: Tag) -> list[Tag]:
        elements: list[Tag] = []
        for child in root.children:
            if isinstance(child, Tag):
                if child.name in _BLOCK_TAGS:
                    elements.append(child)
                else:
                    elements.extend(_collect_blocks(child))
        return elements

    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_body_parts: list[str] = []

    def _flush() -> None:
        nonlocal current_body_parts
        body = "\n\n".join(p for p in current_body_parts if p.strip()).strip()
        if body or current_heading:
            sections.append((current_heading, body))
        current_body_parts = []

    body_el = soup.find("body") or soup.find("html") or soup
    for el in _collect_blocks(body_el):
        if el.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            _flush()
            current_heading = el.get_text(strip=True)
        else:
            text = el.get_text(strip=True)
            if text:
                current_body_parts.append(text)

    _flush()

    if not sections:
        # No heading structure found — return single unnamed section
        text = soup.get_text(separator="\n", strip=True)
        if not text:
            raise ValueError("No readable content found at this URL")
        if len(text) > MAX_EXTRACTED_CHARS:
            text = text[:MAX_EXTRACTED_CHARS]
        return page_title, [("", text)]

    return page_title, sections


async def fetch_url_structured(url: str) -> tuple[str, list[tuple[str, str]]]:
    """Fetch a URL and return structured (heading, body) sections.

    Returns (title, [(heading_text, body_text), ...]).
    Only HTML pages support structured extraction; PDF and plain text
    return a single unnamed section.
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
        text, _ = _extract_pdf_url(raw)
        return "", [(text, "")]
    body = raw.decode("utf-8", errors="replace")[:MAX_EXTRACTED_CHARS * 4]
    if is_text:
        return "", [(body[:MAX_EXTRACTED_CHARS], "")]
    return _extract_html_structured(body, url)


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
