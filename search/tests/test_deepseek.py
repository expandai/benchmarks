"""DeepSeek Search adapter: request shape, parsing, cost rule, retries. Offline."""

from __future__ import annotations

import json

import httpx
import pytest
from conftest import mock_client

from bakeoff.deepseek import (
    DEEPSEEK_SEARCH_URL,
    DEEPSEEK_USD_PER_SUCCESSFUL_REQUEST,
    DeepSeekSearcher,
    clip_query,
)

BODY = {
    "results": [
        {
            "rerank_score": 2.4,
            "title": "GNU text utilities",
            "url": "https://gnu.example/textutils",
            "snippet": "Short UI summary.",
            "summary": "A sorted, 38,400 word dictionary lives in /usr/lib/ispell/ispell.words.",
            "content": "",
            "site_name": "GNU",
            "site_icon": None,
            "date": "2026-06-01T00:00:00+00:00",
            "authority": 3,
        },
        {"title": "Ispell", "url": "https://gnu.example/ispell", "snippet": "Spell checker.",
         "summary": "", "date": None},
        {"title": "No url", "url": "", "snippet": "x", "summary": "y"},
    ]
}  # fmt: skip


def searcher(handler, **kwargs) -> DeepSeekSearcher:
    instance = DeepSeekSearcher(api_key="test", **kwargs)
    instance._client = mock_client(handler)
    return instance


def test_requires_key():
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        DeepSeekSearcher()


def test_query_is_clipped_to_128_chars_at_a_word_boundary():
    long = "word " * 40
    clipped = clip_query(long)
    assert len(clipped) <= 128 and not clipped.endswith(" ") and clipped.startswith("word word")
    assert clip_query("short question?") == "short question?"
    assert len(clip_query("x" * 300)) == 128  # no space: hard cut


async def test_request_shape_parsing_and_cost():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers["authorization"], json.loads(request.content)))
        return httpx.Response(200, json=BODY)

    response = await searcher(handler).run("How many words?", 20)
    assert seen == [(DEEPSEEK_SEARCH_URL, "Bearer test", {"query": "How many words?", "count": 20})]
    assert [r.url for r in response.results] == [
        "https://gnu.example/textutils",
        "https://gnu.example/ispell",
        "",
    ]
    assert response.results[0].text.startswith("A sorted, 38,400")  # summary preferred
    assert response.results[1].text == "Spell checker."  # snippet when summary is empty
    assert response.results[0].metadata["rerank_score"] == 2.4
    assert response.cost_usd == DEEPSEEK_USD_PER_SUCCESSFUL_REQUEST == 0.00075
    assert response.queries == ["How many words?"]


async def test_empty_results_are_not_billed():
    response = await searcher(lambda request: httpx.Response(200, json={"results": []})).run("q", 10)
    assert response.results == [] and response.cost_usd == 0.0


async def test_count_out_of_range_is_refused():
    with pytest.raises(ValueError, match="1-50"):
        await searcher(lambda request: httpx.Response(200, json=BODY)).run("q", 51)


async def test_429_and_5xx_are_retried_then_succeed():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "1"}, json={"error": {}})
        if len(calls) == 2:
            return httpx.Response(504, json={"error": {}})
        return httpx.Response(200, json=BODY)

    response = await searcher(handler).run("q", 10)
    assert len(calls) == 3 and len(response.results) == 3


@pytest.mark.parametrize("status", [400, 401, 402])
async def test_client_errors_are_not_retried(status):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, json={"error": {"message": "nope"}})

    with pytest.raises(httpx.HTTPStatusError, match=str(status)):
        await searcher(handler).run("q", 10)
    assert len(calls) == 1


async def test_retries_are_bounded():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, json={"error": {}})

    with pytest.raises(httpx.HTTPStatusError, match="429"):
        await searcher(handler, max_attempts=3).run("q", 10)
    assert len(calls) == 3
