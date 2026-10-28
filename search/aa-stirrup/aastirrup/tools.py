"""One Stirrup tool provider that puts any bakeoff searcher behind Stirrup's ``web_search`` tool.

``web_search`` keeps Stirrup's tool name and parameter schema (one ``query`` string; Stirrup ``tools/web.py``
at the pinned commit) and renders results exactly as Stirrup renders Brave results::

    <results>
    <result>
    <title>…</title>
    <url>…</url>
    <description>…</description>
    </result>
    …
    </results>

HTML-escaped and truncated to Stirrup's 40,000 characters. ``description`` is the searcher's evidence for
that row (``SearchResult.evidence``: highlights / excerpts / passage, else text / snippet / summary), the
same text the bakeoff's RAG answerer sees. Ten results per search (AA: ``max_results=10``). A system may
set ``max_evidence_chars`` (``systems.SystemDef.evidence_chars``) to clip each description; only the
page-text provider Brave LLM Context does (4,000 characters).

``web_fetch`` is Stirrup's own fetch-and-extract tool (trafilatura → markdown, 40,000-character cap,
public-address checks) with AA's settings: a 15-second deadline and only URLs that ``web_search`` returned
in this task (AA lists any other URL as a recoverable, failed tool call). Stirrup names its tool
``fetch_web_page``; AA's methodology calls it ``web_fetch``, which we use.

Contamination filter (AA filters inside both tools, rules unpublished): drop search rows whose URL, title or
description point at the benchmark itself (``BLOCKED_URL_PATTERNS``) or contain the question verbatim; a
fetched page with the same signals comes back as a failed fetch. Every drop is counted.

Search failures: the searcher's own retries run first; then this tool retries the whole call
(``SEARCH_ATTEMPTS``) on 429/5xx/timeouts. A search that still fails, or fails with another 4xx
(e.g. Exa 402), raises, which ends the task as an execution error (not graded, re-run on resume), because AA
retries fatal provider errors until success rather than scoring them.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import asdict, dataclass, field
from html import escape, unescape
from types import TracebackType
from typing import Annotated, Any

import httpx
from bakeoff.official_rag import normalize_text
from harness.searchers import Searcher, SearchResult
from pydantic import BaseModel, Field
from stirrup.core.models import Tool, ToolProvider, ToolResult
from stirrup.tools.web import (
    MAX_LENGTH_WEB_SEARCH_RESULTS,
    WebFetchMetadata,
    WebSearchMetadata,
    _get_fetch_web_page_tool,  # private in Stirrup; reused so fetch behaves exactly like Stirrup's
)
from stirrup.utils.text import truncate_msg

NUM_RESULTS = 10
FETCH_TIMEOUT_S = 15.0
SEARCH_ATTEMPTS = 4
_RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})

BLOCKED_URL_PATTERNS = (
    re.compile(r"artificialanalysis\.ai", re.I),
    re.compile(r"aa[-_ ]?omniscience", re.I),
    re.compile(r"arxiv\.org/(abs|pdf|html)/2511\.13029", re.I),
    re.compile(r"huggingface\.co/datasets/ArtificialAnalysis", re.I),
)
_MIN_QUESTION_CHARS = 40


class WebSearchParams(BaseModel):
    """Stirrup's ``web_search`` parameters, with the Brave-specific wording removed."""

    query: Annotated[str, Field(description="Natural language search query (similar to Google search syntax)")]


class WebFetchParams(BaseModel):
    url: Annotated[str, Field(description="Full HTTP or HTTPS URL of a page returned by web_search")]


@dataclass
class SearchCall:
    query: str
    latency_s: float
    cost_usd: float | None
    results: int
    filtered: int
    attempts: int
    error: str | None = None


@dataclass
class FetchCall:
    url: str
    latency_s: float
    success: bool
    allowed: bool
    filtered: bool = False


@dataclass
class Telemetry:
    searches: list[SearchCall] = field(default_factory=list)
    fetches: list[FetchCall] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def url_key(url: str) -> str:
    """Match key for "was this URL returned?": HTML entities undone (the model sometimes copies ``&amp;`` from
    the XML), fragment dropped (Stirrup's fetch drops it too), surrounding whitespace removed."""
    return unescape(url).strip().split("#", 1)[0]


class ContaminationFilter:
    def __init__(self, question: str = "") -> None:
        normalized = normalize_text(question)
        self._question = normalized if len(normalized) >= _MIN_QUESTION_CHARS else ""

    def url_blocked(self, url: str) -> bool:
        return any(pattern.search(url) for pattern in BLOCKED_URL_PATTERNS)

    def text_blocked(self, text: str) -> bool:
        if not text:
            return False
        if any(pattern.search(text) for pattern in BLOCKED_URL_PATTERNS[1:2]):  # "AA-Omniscience" mentions
            return True
        return bool(self._question) and self._question in normalize_text(text)

    def keep(self, result: SearchResult) -> bool:
        return not (
            self.url_blocked(result.url)
            or self.text_blocked(result.title)
            or self.text_blocked(result.evidence)
        )


TRUNCATION_MARKER = " [truncated]"


def clip_evidence(text: str, max_chars: int | None) -> str:
    """Clip one result's evidence to ``max_chars`` (marker included); ``None`` leaves it untouched."""
    if max_chars is None or len(text) <= max_chars:
        return text
    return text[: max(max_chars - len(TRUNCATION_MARKER), 0)].rstrip() + TRUNCATION_MARKER


def render_results(results: list[SearchResult], max_evidence_chars: int | None = None) -> str:
    """Stirrup's Brave rendering, with ``description`` = the row's evidence (optionally clipped)."""
    return (
        "<results>\n"
        + "\n".join(
            "<result>"
            f"\n<title>{escape(result.title or '')}</title>"
            f"\n<url>{escape(result.url or '')}</url>"
            f"\n<description>{escape(clip_evidence(result.evidence or '', max_evidence_chars))}</description>"
            "\n</result>"
            for result in results
        )
        + "\n</results>"
    )


def _retryable(error: BaseException) -> bool:
    if isinstance(error, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in _RETRYABLE_STATUS
    return False


class SearchToolProvider(ToolProvider):
    """``web_search`` backed by ``searcher`` plus AA-style ``web_fetch``; one instance per task."""

    def __init__(
        self,
        searcher: Searcher,
        *,
        question: str = "",
        num_results: int = NUM_RESULTS,
        fetch_timeout_s: float = FETCH_TIMEOUT_S,
        search_attempts: int = SEARCH_ATTEMPTS,
        retry_base_s: float = 2.0,
        fetch_tool: Tool[Any, Any] | None = None,
        max_evidence_chars: int | None = None,
    ) -> None:
        self.searcher = searcher
        self.max_evidence_chars = max_evidence_chars
        self.filter = ContaminationFilter(question)
        self.num_results = num_results
        self.fetch_timeout_s = fetch_timeout_s
        self.search_attempts = search_attempts
        self.retry_base_s = retry_base_s
        self.telemetry = Telemetry()
        self.returned_urls: set[str] = set()
        self._fetch_tool = fetch_tool
        self._fetch_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> list[Tool[Any, Any]]:
        if self._fetch_tool is None:
            # Same client settings as Stirrup's WebToolProvider fetch client.
            self._fetch_client = httpx.AsyncClient(
                timeout=self.fetch_timeout_s, follow_redirects=False, trust_env=False
            )
            self._fetch_tool = _get_fetch_web_page_tool(self._fetch_client, timeout=self.fetch_timeout_s)
        return [self.search_tool(), self.fetch_tool()]

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._fetch_client is not None:
            await self._fetch_client.aclose()
            self._fetch_client = None

    async def search(self, query: str) -> ToolResult[WebSearchMetadata]:
        start = time.perf_counter()
        attempts = 0
        while True:
            attempts += 1
            try:
                response = await self.searcher.run(query, self.num_results)
                break
            except Exception as error:  # noqa: BLE001 - classified below, re-raised when fatal
                if attempts >= self.search_attempts or not _retryable(error):
                    self.telemetry.searches.append(
                        SearchCall(query, time.perf_counter() - start, None, 0, 0, attempts,
                                   f"{type(error).__name__}: {str(error)[:300]}")
                    )  # fmt: skip
                    raise
                await asyncio.sleep(self.retry_base_s * 2 ** (attempts - 1))
        rows = response.results[: self.num_results]
        kept = [row for row in rows if self.filter.keep(row)]
        self.returned_urls.update(url_key(row.url) for row in kept if row.url)
        self.telemetry.searches.append(
            SearchCall(query, time.perf_counter() - start, response.cost_usd, len(kept),
                       len(rows) - len(kept), attempts)
        )  # fmt: skip
        return ToolResult(
            content=truncate_msg(render_results(kept, self.max_evidence_chars), MAX_LENGTH_WEB_SEARCH_RESULTS),
            metadata=WebSearchMetadata(pages_returned=len(kept)),
        )

    async def fetch(self, params: WebFetchParams) -> ToolResult[WebFetchMetadata]:
        start = time.perf_counter()
        url = params.url
        if url_key(url) not in self.returned_urls:
            self.telemetry.fetches.append(FetchCall(url, 0.0, False, allowed=False))
            return ToolResult(
                content=f"<web_fetch><url>{escape(url)}</url><error>web_fetch only accepts URLs returned by "
                "web_search in this task.</error></web_fetch>",
                success=False,
                metadata=WebFetchMetadata(pages_fetched=[url]),
            )
        assert self._fetch_tool is not None, "provider not entered"
        result = await self._fetch_tool.executor(self._fetch_tool.parameters(url=unescape(url).strip()))
        filtered = result.success and self.filter.text_blocked(str(result.content))
        if filtered:
            result = ToolResult(
                content=f"<web_fetch><url>{escape(url)}</url><error>Page unavailable.</error></web_fetch>",
                success=False,
                metadata=WebFetchMetadata(pages_fetched=[url]),
            )
        self.telemetry.fetches.append(
            FetchCall(url, time.perf_counter() - start, result.success, allowed=True, filtered=filtered)
        )
        return result

    def search_tool(self) -> Tool[WebSearchParams, WebSearchMetadata]:
        async def executor(params: WebSearchParams) -> ToolResult[WebSearchMetadata]:
            return await self.search(params.query)

        return Tool[WebSearchParams, WebSearchMetadata](
            name="web_search",
            description=(
                f"Search the web. Returns top {self.num_results} results with title, URL, and description as XML."
            ),
            parameters=WebSearchParams,
            executor=executor,
        )

    def fetch_tool(self) -> Tool[WebFetchParams, WebFetchMetadata]:
        return Tool[WebFetchParams, WebFetchMetadata](
            name="web_fetch",
            description=(
                "Fetch and extract the main content from a web page returned by web_search, as markdown. "
                "Returns body text or error as XML."
            ),
            parameters=WebFetchParams,
            executor=self.fetch,
        )
