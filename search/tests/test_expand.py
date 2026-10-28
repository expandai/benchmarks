"""Expand adapter contract: request shape, citation mapping, cost, errors, empty results."""

from __future__ import annotations

import json

import httpx
import pytest
from conftest import fixture, mock_client
from harness.tools import normalize_results

from bakeoff.expand import EXPAND_SEARCH_COST_PER_REQUEST, ExpandSearcher


def recording(response_json, seen: dict, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(status, json=response_json, headers={"x-request-id": "req-1"})

    return handler


async def test_request_shape_and_default_base_url():
    seen: dict = {}
    searcher = ExpandSearcher(api_key="k")
    searcher._client = mock_client(recording(fixture("expand_search.json"), seen))
    response = await searcher.run("Slackware ispell.words dictionary size", 10)
    assert seen["url"] == "https://api.expand.ai/v1/search"
    assert seen["headers"]["x-expand-api-key"] == "k"
    assert "authorization" not in seen["headers"]
    assert seen["body"] == {
        "query": "Slackware ispell.words dictionary size",
        "maxResults": 10,
    }
    assert response.request_id == "req-1"
    assert response.queries == ["Slackware ispell.words dictionary size"]


async def test_environment_supplies_key_and_base_url(monkeypatch):
    monkeypatch.setenv("EXPAND_API_KEY", "env-key")
    monkeypatch.setenv("EXPAND_SEARCH_BASE_URL", "https://search.example/")
    seen: dict = {}
    searcher = ExpandSearcher()
    searcher._client = mock_client(recording(fixture("expand_empty.json"), seen))
    await searcher.run("q")
    assert seen["url"] == "https://search.example/v1/search"
    assert seen["headers"]["x-expand-api-key"] == "env-key"


def test_missing_key_fails_before_any_request():
    with pytest.raises(ValueError, match="EXPAND_API_KEY"):
        ExpandSearcher()


def test_payload_respects_api_limits():
    searcher = ExpandSearcher(api_key="k")
    # The body is {query, maxResults} only.
    assert searcher.search_payload("q", 10) == {"query": "q", "maxResults": 10}
    assert searcher.search_payload("q", 3) == {"query": "q", "maxResults": 3}
    assert searcher.search_payload("q", 25)["maxResults"] == 10
    long_query = "word " * 600
    clipped = searcher.search_payload(long_query, 10)["query"]
    assert len(clipped) <= 2000 and not clipped.endswith("wor")
    with pytest.raises(ValueError):
        searcher.search_payload("q", 0)


async def test_each_result_is_one_citation_with_its_excerpt():
    searcher = ExpandSearcher(api_key="k")
    searcher._client = mock_client(recording(fixture("expand_search.json"), {}))
    response = await searcher.run("q", 10)
    rows = response.results
    assert [r.url for r in rows] == [
        "https://gnu.huihoo.com/textutils-1.22/html_mono/textutils.html",
        "https://www.gnu.org/software/ispell/",
        "https://www.gnu.org/software/coreutils/manual/html_node/sort-invocation.html",
        "https://example.org/no-excerpt",
    ]
    assert rows[0].title == "GNU text utilities"
    assert rows[0].text == "" and rows[0].highlights == [
        fixture("expand_search.json")["results"][0]["excerpt"]
    ]
    assert "38,400 word dictionary" in rows[0].evidence
    assert rows[1].metadata == {"rank": 1, "score": 0.61, "published_date": None}
    assert response.cost_usd == EXPAND_SEARCH_COST_PER_REQUEST == 0.0015

    # What SingleStepRAG hands the answer model and the grader as citations:
    kept, skipped = normalize_results(rows)
    assert len(kept) == 3
    assert skipped == [{"reason": "empty_text", "url": "https://example.org/no-excerpt"}]
    assert kept[2]["text"].startswith("The sort command")


async def test_result_count_never_exceeds_request():
    searcher = ExpandSearcher(api_key="k")
    searcher._client = mock_client(recording(fixture("expand_search.json"), {}))
    assert len((await searcher.run("q", 2)).results) == 2


async def test_empty_results_are_free_and_empty():
    searcher = ExpandSearcher(api_key="k")
    searcher._client = mock_client(recording(fixture("expand_empty.json"), {}))
    response = await searcher.run("nothing matches", 10)
    assert response.results == [] and response.cost_usd == 0.0


@pytest.mark.parametrize("status", [400, 401, 403, 500])
async def test_permanent_errors_are_not_retried(status):
    attempts = []

    def handler(request):
        attempts.append(1)
        return httpx.Response(status, json={"error": "forbidden"})

    searcher = ExpandSearcher(api_key="k", max_attempts=4)
    searcher._client = mock_client(handler)
    with pytest.raises(httpx.HTTPStatusError, match=f"Expand API error {status}"):
        await searcher.run("q")
    assert len(attempts) == 1


@pytest.mark.parametrize("status", [429, 502, 503, 504])
async def test_transient_errors_are_retried(status):
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(status, text="busy")
        return httpx.Response(200, json=fixture("expand_search.json"))

    searcher = ExpandSearcher(api_key="k", max_attempts=4)
    searcher._client = mock_client(handler)
    assert len((await searcher.run("q")).results) == 4
    assert len(attempts) == 3


async def test_exhausted_retries_raise_last_error():
    searcher = ExpandSearcher(api_key="k", max_attempts=2)
    searcher._client = mock_client(lambda request: httpx.Response(503, text="unavailable"))
    with pytest.raises(httpx.HTTPStatusError, match="503"):
        await searcher.run("q")


async def test_transport_errors_are_retried_then_raised():
    attempts = []

    def handler(request):
        attempts.append(1)
        raise httpx.ConnectError("refused", request=request)

    searcher = ExpandSearcher(api_key="k", max_attempts=3)
    searcher._client = mock_client(handler)
    with pytest.raises(httpx.ConnectError):
        await searcher.run("q")
    assert len(attempts) == 3


async def test_malformed_success_body_is_an_error():
    searcher = ExpandSearcher(api_key="k")
    searcher._client = mock_client(lambda request: httpx.Response(200, json={"data": []}))
    with pytest.raises(ValueError, match="no results list"):
        await searcher.run("q")
