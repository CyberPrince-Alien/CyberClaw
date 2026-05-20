"""Web Search Providers -- multi-provider registry with auto-detection and fallback."""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

@dataclass
class SearchResult:
    title: str; url: str; snippet: str; source: str = ""

@dataclass
class WebSearchProvider:
    id: str; name: str; requires_key: bool = True
    env_var: str = ""; api_base: str = ""

    async def search(self, query: str, num_results: int = 5, api_key: str = "") -> list[SearchResult]:
        raise NotImplementedError

class BraveSearchProvider(WebSearchProvider):
    def __init__(self):
        super().__init__("brave", "Brave Search", True, "BRAVE_API_KEY",
                         "https://api.search.brave.com/res/v1/web/search")
    async def search(self, query: str, num_results: int = 5, api_key: str = "") -> list[SearchResult]:
        import httpx
        async with httpx.AsyncClient() as c:
            r = await c.get(self.api_base, params={"q": query, "count": num_results},
                           headers={"X-Subscription-Token": api_key}, timeout=15)
            data = r.json(); results = []
            for item in data.get("web", {}).get("results", [])[:num_results]:
                results.append(SearchResult(item.get("title",""), item.get("url",""),
                                           item.get("description",""), "brave"))
            return results

class TavilySearchProvider(WebSearchProvider):
    def __init__(self):
        super().__init__("tavily", "Tavily", True, "TAVILY_API_KEY", "https://api.tavily.com/search")
    async def search(self, query: str, num_results: int = 5, api_key: str = "") -> list[SearchResult]:
        import httpx
        async with httpx.AsyncClient() as c:
            r = await c.post(self.api_base, json={"api_key": api_key, "query": query,
                             "max_results": num_results}, timeout=15)
            data = r.json(); results = []
            for item in data.get("results", [])[:num_results]:
                results.append(SearchResult(item.get("title",""), item.get("url",""),
                                           item.get("content","")[:300], "tavily"))
            return results

class DuckDuckGoSearchProvider(WebSearchProvider):
    def __init__(self):
        super().__init__("duckduckgo", "DuckDuckGo", False)
    async def search(self, query: str, num_results: int = 5, api_key: str = "") -> list[SearchResult]:
        import httpx
        async with httpx.AsyncClient() as c:
            r = await c.get("https://api.duckduckgo.com/", params={"q": query, "format": "json",
                            "no_html": 1}, timeout=15)
            data = r.json(); results = []
            for item in data.get("RelatedTopics", [])[:num_results]:
                if isinstance(item, dict) and "Text" in item:
                    results.append(SearchResult(item.get("Text","")[:80],
                                               item.get("FirstURL",""), item.get("Text",""), "ddg"))
            return results

class WebSearchRegistry:
    """Registry with auto-detection and fallback."""
    def __init__(self):
        self._providers: dict[str, WebSearchProvider] = {}
        self._register_defaults()

    def _register_defaults(self):
        for p in [BraveSearchProvider(), TavilySearchProvider(), DuckDuckGoSearchProvider()]:
            self._providers[p.id] = p

    def register(self, provider: WebSearchProvider):
        self._providers[provider.id] = provider

    def get(self, provider_id: str) -> WebSearchProvider | None:
        return self._providers.get(provider_id)

    def list_providers(self) -> list[WebSearchProvider]:
        return list(self._providers.values())

    def auto_detect(self, api_keys: dict[str, str] = {}) -> WebSearchProvider | None:
        """Find the best available provider based on available keys."""
        import os
        for p in self._providers.values():
            if not p.requires_key: continue
            key = api_keys.get(p.id) or os.environ.get(p.env_var, "")
            if key: return p
        # Fallback to keyless
        for p in self._providers.values():
            if not p.requires_key: return p
        return None

    async def search(self, query: str, provider_id: str = "", num_results: int = 5,
                     api_keys: dict[str, str] = {}) -> list[SearchResult]:
        """Search with provider selection and fallback."""
        import os
        providers = ([self._providers[provider_id]] if provider_id and provider_id in self._providers
                     else list(self._providers.values()))
        for p in providers:
            key = api_keys.get(p.id) or os.environ.get(p.env_var, "")
            if p.requires_key and not key: continue
            try:
                return await p.search(query, num_results, key)
            except Exception as e:
                logger.warning("Search provider %s failed: %s", p.id, e)
        return []

_registry = WebSearchRegistry()
def get_search_registry() -> WebSearchRegistry: return _registry
