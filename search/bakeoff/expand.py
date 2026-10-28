"""Expand Search adapter for the Exa benchmark harness.

Calls ``POST {base_url}/v1/search`` with ``x-expand-api-key``. The body is
``{query, maxResults}``; the response is ``{results: [{url, title, excerpt, score}]}``,
most relevant first, **one result per page** with the provider's excerpt for that page.
Each result becomes one ``SearchResult`` (one citation) with the excerpt as its only
highlight, so the grader sees exactly what the API returned.

Priced at its list price of $1.50 per 1,000 searches (2026-10-28); a search that finds nothing is refunded.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
from harness.searchers import Searcher, SearchResponse, SearchResult

from ._http import post_with_backoff

DEFAULT_BASE_URL = "https://api.expand.ai"
SEARCH_PATH = "/v1/search"
EXPAND_SEARCH_COST_PER_REQUEST = 0.0015
MAX_RESULTS = 10
_MAX_QUERY_CHARS = 2000
# Expand's API documents 503 as retryable and 500 as permanent, so 500 is not retried.
_RETRYABLE_STATUS = frozenset({429, 502, 503, 504})
logger = logging.getLogger(__name__)


class ExpandSearcher(Searcher):
    name = "expand"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        max_attempts: int = 4,
        timeout: float = 60.0,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.api_key = api_key or os.getenv("EXPAND_API_KEY")
        if not self.api_key:
            raise ValueError("EXPAND_API_KEY required")
        self.base_url = (
            base_url or os.getenv("EXPAND_SEARCH_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self.max_attempts = max_attempts
        self._client = httpx.AsyncClient(timeout=timeout)

    def search_payload(self, query: str, num_results: int) -> dict[str, Any]:
        """Build the ``/v1/search`` body within the API's limits: ``{query, maxResults}`` only."""
        if num_results < 1:
            raise ValueError("num_results must be positive")
        if num_results > MAX_RESULTS:
            logger.warning(
                "Expand returns at most %s results; requested %s", MAX_RESULTS, num_results
            )
        if len(query) > _MAX_QUERY_CHARS:
            logger.warning("Expand query exceeds %s characters; truncating", _MAX_QUERY_CHARS)
            query = query[:_MAX_QUERY_CHARS].rsplit(" ", 1)[0]
        return {"query": query, "maxResults": min(num_results, MAX_RESULTS)}

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
        data, request_id = await self._post(payload)
        results = parse_results(data)[:num_results]
        return SearchResponse(
            results=results,
            # Expand refunds a search that found nothing.
            cost_usd=EXPAND_SEARCH_COST_PER_REQUEST if data.get("results") else 0.0,
            latency_ms=(time.perf_counter() - start) * 1000,
            request_id=request_id,
            queries=[payload["query"]],
        )

    async def _post(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        """POST with backoff (``bakeoff._http``) on rate limits, 5xx gateway errors and timeouts."""
        response = await post_with_backoff(
            self._client,
            f"{self.base_url}{SEARCH_PATH}",
            headers={"x-expand-api-key": self.api_key, "Content-Type": "application/json"},
            payload=payload,
            provider="Expand",
            max_attempts=self.max_attempts,
            retryable=_RETRYABLE_STATUS,
        )
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise ValueError(f"Expand response has no results list: {response.text[:500]}")
        return data, response.headers.get("x-request-id")

    async def close(self) -> None:
        await self._client.aclose()


def parse_results(data: dict[str, Any]) -> list[SearchResult]:
    """Map Expand results to rows: one row per result (one page), its excerpt as the evidence."""
    rows: list[SearchResult] = []
    for rank, item in enumerate(data.get("results") or []):
        excerpt = item.get("excerpt") or ""
        rows.append(
            SearchResult(
                url=item.get("url") or "",
                title=item.get("title") or "",
                highlights=[excerpt] if excerpt else [],
                metadata={"rank": rank, "score": item.get("score"), "published_date": None},
            )
        )
    return rows
