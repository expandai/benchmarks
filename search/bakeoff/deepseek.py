"""DeepSeek Search API adapter for the Exa benchmark harness.

Calls ``POST https://api.deepseek.com/v1/tools/search`` with ``Authorization: Bearer``.
Request: ``query`` (1-128 Unicode characters, operators allowed), ``count`` (1-50,
default 10), ``need_content`` (default false, so ``content`` is empty). Each result has
``title``, ``url``, ``snippet`` (~100-200 chars, UI-facing), ``summary`` (~600-800 chars,
"model-oriented"), ``rerank_score`` (0-3), ``authority``, ``date``. A search with no match
returns 200 with an empty ``results`` list.

Evidence: ``summary`` (the model-facing text), falling back to ``snippet``. Longer
questions are clipped to 128 characters at a word boundary, as other adapters clip to
their provider limits; the clip is logged.

Price: $0.75 per 1,000 successful requests; a request is billed only when it returns a
non-empty ``results`` list, and ``count`` does not change the price. Responses carry no
usage or cost fields, so this adapter records the standalone API's list price. The
docs' 2026-11-01 billing change concerns server-side tool calls through DeepSeek
Harness, Claude Code or Codex, rather than the standalone requests made here.
Retries: 408, 429 and 5xx with backoff (honouring
``Retry-After``); 402 (insufficient balance) and other 4xx fail at once, as the docs say.

API reference: https://api-docs.deepseek.com/guides/search
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
from harness.searchers import Searcher, SearchResponse, SearchResult

from ._http import post_with_backoff

DEEPSEEK_SEARCH_URL = "https://api.deepseek.com/v1/tools/search"
DEEPSEEK_USD_PER_SUCCESSFUL_REQUEST = 0.75 / 1000
MAX_QUERY_CHARS = 128
MAX_COUNT = 50
logger = logging.getLogger(__name__)


def clip_query(query: str, max_chars: int = MAX_QUERY_CHARS) -> str:
    """Clip to DeepSeek's 128-character limit at a word boundary."""
    query = query.strip()
    if len(query) <= max_chars:
        return query
    clipped = query[:max_chars].rsplit(" ", 1)[0].strip()
    return clipped or query[:max_chars]


def parse_results(data: dict[str, Any]) -> list[SearchResult]:
    results = []
    for rank, row in enumerate(data.get("results") or []):
        summary = row.get("summary") or ""
        snippet = row.get("snippet") or ""
        results.append(
            SearchResult(
                url=row.get("url") or "",
                title=row.get("title") or "",
                text=summary or snippet,
                metadata={
                    "rank": rank,
                    "published_date": row.get("date"),
                    "snippet": snippet,
                    "rerank_score": row.get("rerank_score"),
                    "authority": row.get("authority"),
                    "site_name": row.get("site_name"),
                },
            )
        )
    return results


class DeepSeekSearcher(Searcher):
    name = "deepseek"

    def __init__(
        self,
        api_key: str | None = None,
        max_attempts: int = 5,
        timeout: float = 60.0,
    ):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY required")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.max_attempts = max_attempts
        self._client = httpx.AsyncClient(timeout=timeout)

    def search_payload(self, query: str, num_results: int) -> dict[str, Any]:
        if not 1 <= num_results <= MAX_COUNT:
            raise ValueError(f"DeepSeek count must be 1-{MAX_COUNT}, got {num_results}")
        clipped = clip_query(query)
        if clipped != query.strip():
            logger.info("DeepSeek query clipped from %s to %s characters", len(query), len(clipped))
        return {"query": clipped, "count": num_results}

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
            cost_usd=DEEPSEEK_USD_PER_SUCCESSFUL_REQUEST if data.get("results") else 0.0,
            latency_ms=(time.perf_counter() - start) * 1000,
            queries=[payload["query"]],
        )

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await post_with_backoff(
            self._client,
            DEEPSEEK_SEARCH_URL,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            payload=payload,
            provider="DeepSeek",
            max_attempts=self.max_attempts,
        )
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise ValueError(f"DeepSeek response has no results list: {response.text[:500]}")
        return data

    async def close(self) -> None:
        await self._client.aclose()
