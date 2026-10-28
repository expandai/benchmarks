from __future__ import annotations

import httpx
import pytest
from harness.searchers import SearchResult
from stirrup.core.models import Tool, ToolResult
from stirrup.tools.web import WebFetchMetadata, _get_websearch_tool

from aastirrup.tools import (
    ContaminationFilter,
    SearchToolProvider,
    WebFetchParams,
    render_results,
    url_key,
)

from .conftest import FakeSearcher

BRAVE_ROWS = [
    {"title": "Title <1> & co", "url": "https://a.example/x?y=1&z=2", "description": "Desc \"quoted\" <b>bold</b>"},
    {"title": "", "url": "https://b.example/", "description": ""},
]


async def test_rendering_matches_stirrup_brave_rendering_byte_for_byte() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"web": {"results": BRAVE_ROWS}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tool = _get_websearch_tool("test-key", client)
        stirrup_result = await tool.executor(tool.parameters(query="q"))
    ours = render_results(
        [SearchResult(url=r["url"], title=r["title"], text=r["description"]) for r in BRAVE_ROWS]
    )
    assert ours == stirrup_result.content


def test_description_is_the_rows_evidence(rows: list[SearchResult]) -> None:
    xml = render_results(rows[:2])
    assert "<description>first &lt;hl&gt;\nsecond</description>" in xml  # highlights joined
    assert "<description>snippet text</description>" in xml  # text when no highlights
    assert "<title>A &amp; B</title>" in xml


def test_contamination_filter(rows: list[SearchResult]) -> None:
    question = "Under U.S. GAAP (ASC Topic 606), which reference explicitly lists the two criteria?"
    flt = ContaminationFilter(question)
    assert flt.keep(rows[0]) and flt.keep(rows[1])
    assert not flt.keep(rows[2])
    assert not flt.keep(SearchResult(url="https://artificialanalysis.ai/evaluations/omniscience", title="x"))
    assert not flt.keep(SearchResult(url="https://x.example", title="t", text=f"Q: {question.upper()} A: ..."))
    assert flt.keep(SearchResult(url="https://x.example", title="t", text="ASC Topic 606 overview"))
    assert not ContaminationFilter("").text_blocked("")


async def test_search_filters_records_urls_and_telemetry(rows: list[SearchResult]) -> None:
    searcher = FakeSearcher(rows)
    provider = SearchToolProvider(searcher, question="", fetch_tool=_stub_fetch_tool())
    async with provider:
        result = await provider.search("query one")
    assert searcher.calls == [("query one", 10)]
    assert "huggingface.co" not in result.content
    assert provider.returned_urls == {"https://example.com/a", "https://example.org/b"}
    assert url_key("https://x.example/p?a=1&amp;b=2#frag") == "https://x.example/p?a=1&b=2"
    call = provider.telemetry.searches[0]
    assert (call.results, call.filtered, call.attempts, call.cost_usd) == (2, 1, 1, 0.001)


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://search.example")
    return httpx.HTTPStatusError("boom", request=request, response=httpx.Response(status, request=request))


async def test_search_retries_retryable_errors(rows: list[SearchResult]) -> None:
    searcher = FakeSearcher(rows, fail_times=2, error=_status_error(503))
    provider = SearchToolProvider(searcher, retry_base_s=0.0, fetch_tool=_stub_fetch_tool())
    async with provider:
        await provider.search("q")
    assert len(searcher.calls) == 3
    assert provider.telemetry.searches[0].attempts == 3


async def test_search_fatal_error_raises_immediately(rows: list[SearchResult]) -> None:
    searcher = FakeSearcher(rows, fail_times=5, error=_status_error(402))
    provider = SearchToolProvider(searcher, retry_base_s=0.0, fetch_tool=_stub_fetch_tool())
    async with provider:
        with pytest.raises(httpx.HTTPStatusError):
            await provider.search("q")
    assert len(searcher.calls) == 1
    assert provider.telemetry.searches[0].error.startswith("HTTPStatusError")


async def test_search_gives_up_after_attempts(rows: list[SearchResult]) -> None:
    searcher = FakeSearcher(rows, fail_times=99, error=httpx.ReadTimeout("slow"))
    provider = SearchToolProvider(searcher, retry_base_s=0.0, search_attempts=3, fetch_tool=_stub_fetch_tool())
    async with provider:
        with pytest.raises(httpx.ReadTimeout):
            await provider.search("q")
    assert len(searcher.calls) == 3


def _stub_fetch_tool(body: str = "page body") -> Tool:
    from stirrup.tools.web import FetchWebPageParams

    fetched: list[str] = []

    async def executor(params: FetchWebPageParams) -> ToolResult[WebFetchMetadata]:
        fetched.append(params.url)
        return ToolResult(
            content=f"<web_fetch><url>{params.url}</url><body>{body}</body></web_fetch>",
            metadata=WebFetchMetadata(pages_fetched=[params.url]),
        )

    tool = Tool(name="fetch_web_page", description="stub", parameters=FetchWebPageParams, executor=executor)
    tool.__dict__["fetched"] = fetched
    return tool


async def test_fetch_only_returned_urls(rows: list[SearchResult]) -> None:
    stub = _stub_fetch_tool()
    provider = SearchToolProvider(FakeSearcher(rows), fetch_tool=stub)
    async with provider as tools:
        assert [t.name for t in tools] == ["web_search", "web_fetch"]
        refused = await provider.fetch(WebFetchParams(url="https://example.com/a"))
        assert not refused.success and "only accepts URLs returned by web_search" in refused.content
        await provider.search("q")
        ok = await provider.fetch(WebFetchParams(url="https://example.com/a"))
        assert ok.success and "page body" in ok.content
        also = await provider.fetch(WebFetchParams(url="https://example.com/a#section"))
        assert also.success
    assert stub.__dict__["fetched"] == ["https://example.com/a", "https://example.com/a#section"]
    assert [f.allowed for f in provider.telemetry.fetches] == [False, True, True]


async def test_fetch_screens_page_text(rows: list[SearchResult]) -> None:
    question = "Which reference explicitly lists the two criteria for a series of distinct goods?"
    provider = SearchToolProvider(
        FakeSearcher(rows), question=question, fetch_tool=_stub_fetch_tool(f"dump: {question}")
    )
    async with provider:
        await provider.search("q")
        result = await provider.fetch(WebFetchParams(url="https://example.org/b"))
    assert not result.success and "Page unavailable" in result.content
    assert provider.telemetry.fetches[0].filtered


async def test_real_stirrup_fetch_tool_is_wired_with_15s_deadline(rows: list[SearchResult]) -> None:
    provider = SearchToolProvider(FakeSearcher(rows))
    async with provider:
        assert provider._fetch_tool is not None
        assert provider._fetch_tool.name == "fetch_web_page"  # Stirrup's own executor behind web_fetch
        assert provider._fetch_client is not None and provider._fetch_client.timeout.read == 15.0
    assert provider._fetch_client is None
