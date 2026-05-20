"""Browser automation tool using Playwright."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def browser_tool_handler(
    action: str,
    url: str | None = None,
    selector: str | None = None,
    text: str | None = None,
    **kwargs: Any,
) -> str:
    """Execute browser actions.
    
    Actions: navigate, screenshot, click, type, get_text, get_html
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return "Error: playwright not installed. Run: pip install playwright && playwright install chromium"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            if action == "navigate":
                if not url:
                    return "Error: url required for navigate action"
                await page.goto(url, timeout=30000)
                title = await page.title()
                return f"Navigated to {url}. Title: {title}"

            elif action == "screenshot":
                if url:
                    await page.goto(url, timeout=30000)
                screenshot = await page.screenshot(full_page=True)
                # Save to workspace
                import base64
                b64 = base64.b64encode(screenshot).decode()
                return f"Screenshot taken ({len(screenshot)} bytes). Base64 preview: {b64[:200]}..."

            elif action == "click":
                if not selector:
                    return "Error: selector required for click action"
                if url:
                    await page.goto(url, timeout=30000)
                await page.click(selector, timeout=5000)
                return f"Clicked element: {selector}"

            elif action == "type":
                if not selector or not text:
                    return "Error: selector and text required for type action"
                if url:
                    await page.goto(url, timeout=30000)
                await page.fill(selector, text, timeout=5000)
                return f"Typed '{text}' into {selector}"

            elif action == "get_text":
                if url:
                    await page.goto(url, timeout=30000)
                if selector:
                    element = await page.query_selector(selector)
                    if element:
                        text_content = await element.text_content()
                        return text_content or ""
                    return f"Element not found: {selector}"
                # Get full page text
                content = await page.text_content("body") or ""
                # Truncate if too long
                if len(content) > 10000:
                    content = content[:10000] + "\n...[truncated]"
                return content

            elif action == "get_html":
                if url:
                    await page.goto(url, timeout=30000)
                html = await page.content()
                if len(html) > 20000:
                    html = html[:20000] + "\n...[truncated]"
                return html

            else:
                return f"Unknown action: {action}. Use: navigate, screenshot, click, type, get_text, get_html"

        finally:
            await browser.close()


BROWSER_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "browser",
        "description": "Automate web browser actions: navigate to URLs, take screenshots, click elements, type text, and extract page content.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["navigate", "screenshot", "click", "type", "get_text", "get_html"],
                    "description": "The browser action to perform",
                },
                "url": {
                    "type": "string",
                    "description": "URL to navigate to (optional for some actions)",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector for the target element",
                },
                "text": {
                    "type": "string",
                    "description": "Text to type (for type action)",
                },
            },
            "required": ["action"],
        },
    },
}
