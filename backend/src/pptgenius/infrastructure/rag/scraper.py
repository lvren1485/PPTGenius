"""Web page scraper — fetches a URL and extracts clean text content."""

from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

from pptgenius.infrastructure.utils.logger import get_logger

_log = get_logger("pptgenius.scraper")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}

# Tags to strip before text extraction
_STRIP_TAGS = ["script", "style", "nav", "footer", "header", "noscript", "iframe"]


def _clean_text(html: str) -> str:
    """Extract readable text from HTML, removing boilerplate."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()

    # Get text
    text = soup.get_text(separator="\n")

    # Clean up
    lines = [line.strip() for line in text.splitlines()]
    lines = [l for l in lines if l and len(l) > 1]  # drop single-char artifacts
    # Collapse excessive blank lines
    result = []
    blanks = 0
    for line in lines:
        if not line:
            blanks += 1
            if blanks <= 2:
                result.append("")
        else:
            blanks = 0
            result.append(line)
    return "\n".join(result)


def _extract_title(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")
        t = soup.title
        return t.get_text(strip=True) if t else ""
    except Exception:
        return ""


def _extract_domain(url: str) -> str:
    m = re.search(r"https?://([^/]+)", url)
    return m.group(1) if m else ""


async def fetch_page(url: str, timeout: int = 15) -> dict:
    """Fetch *url* and return ``{url, title, domain, text, char_count}``."""
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=_HEADERS)
            resp.raise_for_status()
    except Exception as e:
        _log.warning("fetch failed: %s — %s", url, e)
        return {"url": url, "title": "", "domain": _extract_domain(url),
                "text": "", "char_count": 0}

    html = resp.text
    text = _clean_text(html)
    title = _extract_title(html) or url
    domain = _extract_domain(url)

    _log.debug("fetched %s → %d chars", url, len(text))
    return {
        "url": url,
        "title": title,
        "domain": domain,
        "text": text,
        "char_count": len(text),
    }
