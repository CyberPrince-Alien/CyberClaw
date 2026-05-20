"""Link Understanding -- auto-detect and read URLs in messages."""

import re, logging
from typing import Any

logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(
    r'https?://[^\s<>\[\](){}\'"`,;!]+(?<![.,;:!?\)\]])',
    re.IGNORECASE,
)

def extract_urls(text: str, max_links: int = 5) -> list[str]:
    """Extract URLs from a message."""
    urls = URL_PATTERN.findall(text)
    seen = []; 
    for u in urls:
        if u not in seen: seen.append(u)
        if len(seen) >= max_links: break
    return seen

async def fetch_url_content(url: str, timeout: int = 15, max_bytes: int = 100_000) -> dict[str, Any]:
    """Fetch and extract text content from a URL."""
    import httpx
    headers = {
        "User-Agent": "CyberClaw-LinkUnderstanding/1.0",
        "Accept": "text/*,application/json,application/xhtml+xml",
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, headers=headers, timeout=timeout)
            content_type = resp.headers.get("content-type", "")
            raw = resp.text[:max_bytes]
            if "html" in content_type:
                text = _strip_html(raw)
            elif "json" in content_type:
                text = raw[:5000]
            else:
                text = raw[:5000]
            return {"url": url, "final_url": str(resp.url), "status": resp.status_code,
                    "content_type": content_type, "text": text[:5000],
                    "title": _extract_title(raw) if "html" in content_type else ""}
    except Exception as e:
        return {"url": url, "error": str(e), "text": ""}

def _strip_html(html: str) -> str:
    """Basic HTML to text."""
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:5000]

def _extract_title(html: str) -> str:
    m = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else ""

async def understand_links(message: str, max_links: int = 3) -> list[dict[str, Any]]:
    """Extract URLs from message and fetch their content."""
    urls = extract_urls(message, max_links)
    if not urls: return []
    results = []
    for url in urls:
        result = await fetch_url_content(url)
        if result.get("text"): results.append(result)
    return results

LINK_TOOL_SCHEMA = {"type": "function", "function": {
    "name": "read_link", "description": "Read and extract text content from a URL.",
    "parameters": {"type": "object", "properties": {
        "url": {"type": "string", "description": "URL to read"}},
    "required": ["url"]}}}
