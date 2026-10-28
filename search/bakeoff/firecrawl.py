"""Firecrawl Search (v2) adapter for the Exa benchmark harness.

Calls ``POST https://api.firecrawl.dev/v2/search`` with a bearer token. The
request searches the web only (``sources: ["web"]``) and sends no
``scrapeOptions``, so no page is scraped: each result's ``description`` is the
query-relevant highlight Firecrawl returns by default (top-level ``highlights``
defaults to true). That is the fast, snippet-returning setting, the closest
match to Exa highlights, Parallel excerpts and Perplexity snippets.

Cost is ``creditsUsed`` times ``usd_per_credit`` (default: the Standard plan,
$99 for 100,000 credits a month). Without ``creditsUsed``, a search is priced
at the published 2 credits per 10 results.

API reference: https://docs.firecrawl.dev/api-reference/endpoint/search
Search guide and credits: https://docs.firecrawl.dev/features/search
Pricing: https://www.firecrawl.dev/pricing
"""

from __future__ import annotations

import logging
import math
import os
import time
from typing import Any

import httpx
from harness.searchers import Searcher, SearchResponse, SearchResult

from ._http import post_with_backoff

FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v2/search"
# https://www.firecrawl.dev/pricing — Standard: $99 / month for 100,000 credits.
FIRECRAWL_USD_PER_CREDIT = 99 / 100_000
# https://docs.firecrawl.dev/features/search — "2 credits per 10 results, rounded up".
FIRECRAWL_SEARCH_CREDITS_PER_10 = 2
FIRECRAWL_MAX_LIMIT = 100
_MAX_QUERY_CHARS = 500
logger = logging.getLogger(__name__)


class FirecrawlSearcher(Searcher):
    name = "firecrawl"

    def __init__(
        self,
        api_key: str | None = None,
        sources: list[str] | None = None,
        usd_per_credit: float = FIRECRAWL_USD_PER_CREDIT,
        max_attempts: int = 4,
        timeout: float = 120.0,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY")
        if not self.api_key:
            raise ValueError("FIRECRAWL_API_KEY required")
        self.sources = list(sources) if sources is not None else ["web"]
        self.usd_per_credit = usd_per_credit
        self.max_attempts = max_attempts
        self._client = httpx.AsyncClient(timeout=timeout)

    def search_payload(self, query: str, num_results: int) -> dict[str, Any]:
        """Build the ``/v2/search`` body within the API's query and limit bounds."""
        if num_results < 1:
            raise ValueError("num_results must be positive")
        if len(query) > _MAX_QUERY_CHARS:
            logger.warning("Firecrawl query exceeds %s characters; truncating", _MAX_QUERY_CHARS)
            query = query[:_MAX_QUERY_CHARS].rsplit(" ", 1)[0]
        return {
            "query": query,
            "limit": min(num_results, FIRECRAWL_MAX_LIMIT),
            "sources": list(self.sources),
        }

    async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        return (await self.run(query, num_results)).results

    async def run(
        self,
        query: str,
        num_results: int = 10,
        *,
        objective: str | None = None,
        search_queries: list[str] | None = None,
    ) -> SearchResponse:
        del objective, search_queries
        start = time.perf_counter()
        payload = self.search_payload(query, num_results)
        data = await self._post(payload)
        results = parse_results(data)[:num_results]
        return SearchResponse(
            results=results,
            cost_usd=search_credits(data, payload["limit"]) * self.usd_per_credit,
            latency_ms=(time.perf_counter() - start) * 1000,
            request_id=data.get("id"),
            queries=[payload["query"]],
        )

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST with backoff (``bakeoff._http``) on rate limits, server errors and timeouts."""
        response = await post_with_backoff(
            self._client,
            FIRECRAWL_SEARCH_URL,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            payload=payload,
            provider="Firecrawl",
            max_attempts=self.max_attempts,
        )
        data = response.json()
        if not isinstance(data, dict) or data.get("success") is False:
            raise ValueError(f"Firecrawl search failed: {response.text[:500]}")
        if data.get("warning"):
            logger.warning("Firecrawl warning: %s", data["warning"])
        return data

    async def close(self) -> None:
        await self._client.aclose()


def search_credits(data: dict[str, Any], limit: int) -> float:
    """Reported credits, else the published rate for this request."""
    reported = data.get("creditsUsed")
    if isinstance(reported, (int, float)) and not isinstance(reported, bool):
        return float(reported)
    return float(FIRECRAWL_SEARCH_CREDITS_PER_10 * math.ceil(limit / 10))


def parse_results(data: dict[str, Any]) -> list[SearchResult]:
    """Map Firecrawl's web results (``data.web``) to rows, the description as the evidence."""
    body = data.get("data")
    web = (body.get("web") or []) if isinstance(body, dict) else []
    results = []
    for rank, row in enumerate(row for row in web if isinstance(row, dict)):
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        results.append(
            SearchResult(
                url=row.get("url") or metadata.get("sourceURL") or metadata.get("url") or "",
                title=row.get("title") or metadata.get("title") or "",
                text=row.get("description") or row.get("snippet") or "",
                metadata={
                    "rank": rank,
                    "position": row.get("position"),
                    "published_date": row.get("date") or metadata.get("publishedTime"),
                    "scraped": False,  # no scrapeOptions are sent; kept for the stored runs' metadata shape
                    "status_code": metadata.get("statusCode"),
                },
            )
        )
    return results
