"""Offline fixtures: no test opens a network connection or reads a real key."""

from __future__ import annotations

import os

import pytest
from harness.searchers import Searcher, SearchResponse, SearchResult

os.environ["HF_HUB_OFFLINE"] = "1"

KEY_ENV = (
    "OPENROUTER_API_KEY",
    "OPEN_ROUTER_API_KEY",
    "OPENAI_API_KEY",
    "EXA_API_KEY",
    "PARALLEL_API_KEY",
    "PERPLEXITY_API_KEY",
    "EXPAND_API_KEY",
    "FIRECRAWL_API_KEY",
    "DEEPSEEK_API_KEY",
    "BRAVE_API_KEY",
)


@pytest.fixture(autouse=True)
def no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in KEY_ENV:
        monkeypatch.delenv(name, raising=False)


class FakeSearcher(Searcher):
    """Returns canned rows; can fail the first ``fail_times`` calls with ``error``."""

    name = "fake"

    def __init__(self, rows: list[SearchResult], *, fail_times: int = 0, error: Exception | None = None):
        self.rows = rows
        self.fail_times = fail_times
        self.error = error
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        return (await self.run(query, num_results)).results

    async def run(self, query: str, num_results: int = 10, **_: object) -> SearchResponse:
        self.calls.append((query, num_results))
        if len(self.calls) <= self.fail_times and self.error is not None:
            raise self.error
        return SearchResponse(results=self.rows[:num_results], cost_usd=0.001, latency_ms=5.0, queries=[query])


@pytest.fixture
def rows() -> list[SearchResult]:
    return [
        SearchResult(url="https://example.com/a", title="A & B", highlights=["first <hl>", "second"]),
        SearchResult(url="https://example.org/b", title="Plain", text="snippet text"),
        SearchResult(url="https://huggingface.co/datasets/ArtificialAnalysis/AA-Omniscience-Public",
                     title="AA-Omniscience-Public", text="leak"),  # fmt: skip
    ]
