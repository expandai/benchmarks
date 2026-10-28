"""Firecrawl adapter contract: request shape, citation mapping, cost, errors, empty results."""

from __future__ import annotations

import json

import httpx
import pytest
from conftest import fixture, mock_client
from harness.tools import normalize_results

from bakeoff.firecrawl import FIRECRAWL_USD_PER_CREDIT, FirecrawlSearcher


def recording(response_json, seen: dict, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(status, json=response_json)

    return handler


async def test_default_request_is_web_search_without_scraping():
    seen: dict = {}
    searcher = FirecrawlSearcher(api_key="k")
    searcher._client = mock_client(recording(fixture("firecrawl_search.json"), seen))
    response = await searcher.run("Slackware ispell.words dictionary size", 10)
    assert seen["url"] == "https://api.firecrawl.dev/v2/search"
    assert seen["headers"]["authorization"] == "Bearer k"
    assert seen["body"] == {
        "query": "Slackware ispell.words dictionary size",
        "limit": 10,
        "sources": ["web"],
    }
    assert response.request_id == "search-job-1"


def test_missing_key_fails_before_any_request(monkeypatch):
    with pytest.raises(ValueError, match="FIRECRAWL_API_KEY"):
        FirecrawlSearcher()
    monkeypatch.setenv("FIRECRAWL_API_KEY", "env-key")
    assert FirecrawlSearcher().api_key == "env-key"


def test_payload_limits():
    searcher = FirecrawlSearcher(api_key="k")
    payload = searcher.search_payload("word " * 200, 250)
    assert payload["limit"] == 100
    assert len(payload["query"]) <= 500 and not payload["query"].endswith(" ")
    with pytest.raises(ValueError):
        searcher.search_payload("q", 0)


async def test_snippet_results_map_to_citations_and_reported_credits():
    searcher = FirecrawlSearcher(api_key="k")
    searcher._client = mock_client(recording(fixture("firecrawl_search.json"), {}))
    response = await searcher.run("q", 10)
    first = response.results[0]
    assert first.url == "https://gnu.huihoo.com/textutils-1.22/html_mono/textutils.html"
    assert first.title == "GNU text utilities"
    assert "38,400 word dictionary" in first.text and first.highlights == []
    assert first.evidence == first.text
    assert first.metadata["rank"] == 0 and first.metadata["scraped"] is False
    assert response.cost_usd == pytest.approx(2 * FIRECRAWL_USD_PER_CREDIT)

    kept, skipped = normalize_results(response.results)
    assert [k["url"] for k in kept] == [
        "https://gnu.huihoo.com/textutils-1.22/html_mono/textutils.html",
        "https://www.gnu.org/software/ispell/",
    ]
    assert skipped == [{"reason": "missing_url", "title": "Result without a URL"}]


async def test_published_rate_when_credits_not_reported():
    searcher = FirecrawlSearcher(api_key="k", usd_per_credit=0.01)
    searcher._client = mock_client(
        lambda request: httpx.Response(200, json={"success": True, "data": {"web": []}})
    )
    assert (await searcher.run("q", 10)).cost_usd == pytest.approx(0.02)
    assert (await searcher.run("q", 11)).cost_usd == pytest.approx(0.04)


async def test_empty_results():
    searcher = FirecrawlSearcher(api_key="k")
    searcher._client = mock_client(recording(fixture("firecrawl_empty.json"), {}))
    response = await searcher.run("nothing matches", 10)
    assert response.results == []
    assert response.cost_usd == pytest.approx(2 * FIRECRAWL_USD_PER_CREDIT)


async def test_unsuccessful_body_is_an_error():
    searcher = FirecrawlSearcher(api_key="k")
    searcher._client = mock_client(
        lambda request: httpx.Response(200, json={"success": False, "error": "bad query"})
    )
    with pytest.raises(ValueError, match="bad query"):
        await searcher.run("q")


@pytest.mark.parametrize("status", [400, 401, 402, 403])
async def test_permanent_errors_are_not_retried(status):
    attempts = []

    def handler(request):
        attempts.append(1)
        return httpx.Response(status, json={"success": False, "error": "Payment required"})

    searcher = FirecrawlSearcher(api_key="k", max_attempts=4)
    searcher._client = mock_client(handler)
    with pytest.raises(httpx.HTTPStatusError, match=f"Firecrawl API error {status}"):
        await searcher.run("q")
    assert len(attempts) == 1


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
async def test_transient_errors_are_retried(status):
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(status, text="slow down")
        return httpx.Response(200, json=fixture("firecrawl_search.json"))

    searcher = FirecrawlSearcher(api_key="k", max_attempts=2)
    searcher._client = mock_client(handler)
    assert len((await searcher.run("q")).results) == 3
    assert len(attempts) == 2


async def test_exhausted_retries_raise():
    searcher = FirecrawlSearcher(api_key="k", max_attempts=2)
    searcher._client = mock_client(lambda request: httpx.Response(429, text="rate limited"))
    with pytest.raises(httpx.HTTPStatusError, match="429"):
        await searcher.run("q")


async def test_timeouts_are_retried_then_raised():
    attempts = []

    def handler(request):
        attempts.append(1)
        raise httpx.ReadTimeout("timed out", request=request)

    searcher = FirecrawlSearcher(api_key="k", max_attempts=3)
    searcher._client = mock_client(handler)
    with pytest.raises(httpx.ReadTimeout):
        await searcher.run("q")
    assert len(attempts) == 3
