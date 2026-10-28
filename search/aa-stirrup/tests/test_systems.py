"""System definitions: every listed searcher resolves in the (overlay-merged) harness catalog, the two
upstream comparators map to the right adapters and credentials, and the Brave per-result clip reaches
the rendered XML. Offline."""

from __future__ import annotations

import pytest
from harness import cli
from harness.searchers import SearchResult
from harness.searchers.brave import BraveSearcher
from harness.searchers.tavily import TavilySearcher

from aastirrup.systems import MODEL_ONLY, SYSTEMS, build_searcher, searcher_entry
from aastirrup.tools import TRUNCATION_MARKER, SearchToolProvider, clip_evidence, render_results

from .conftest import FakeSearcher


def test_every_system_has_a_catalog_searcher() -> None:
    for name, system in SYSTEMS.items():
        if name == MODEL_ONLY:
            assert system.searcher is None
            continue
        entry = searcher_entry(name)
        assert "provider" in entry, name


@pytest.mark.parametrize(
    ("name", "provider", "cls", "env_names", "label"),
    [
        ("tavily-advanced", "tavily", TavilySearcher, ("TAVILY_API_KEY",), "Tavily (advanced)"),
        ("brave-llm-context", "brave", BraveSearcher, ("BRAVE_SEARCH_API_KEY", "BRAVE_API_KEY"), "Brave (LLM context)"),
    ],
)
def test_comparators_resolve_to_upstream_adapters(monkeypatch, name, provider, cls, env_names, label) -> None:
    assert SYSTEMS[name].label == label and SYSTEMS[name].concurrency == 10
    assert searcher_entry(name)["provider"] == provider
    assert cli.PROVIDER_KEYS[provider] == env_names
    with pytest.raises(ValueError):  # no key -> the adapter refuses before any request
        build_searcher(name)
    monkeypatch.setenv(env_names[-1], "test")
    assert isinstance(build_searcher(name), cls)


def test_only_brave_clips_evidence() -> None:
    assert SYSTEMS["brave-llm-context"].evidence_chars == 4000
    assert all(s.evidence_chars is None for n, s in SYSTEMS.items() if n != "brave-llm-context")


def test_clip_evidence() -> None:
    assert clip_evidence("short", None) == "short"
    assert clip_evidence("short", 100) == "short"
    clipped = clip_evidence("x" * 5000, 4000)
    assert len(clipped) == 4000 and clipped.endswith(TRUNCATION_MARKER)
    assert render_results([SearchResult(url="u", title="t", text="y" * 50)], 20).count("y") == 20 - len(TRUNCATION_MARKER)


async def test_provider_applies_the_cap_to_rendered_results() -> None:
    rows = [SearchResult(url="https://example.com/long", title="L", text="z" * 10_000)]
    async with SearchToolProvider(FakeSearcher(rows), max_evidence_chars=4000, fetch_tool=_noop_tool()) as tools:
        result = await tools[0].executor(tools[0].parameters(query="q"))
    assert TRUNCATION_MARKER in result.content and result.content.count("z") == 4000 - len(TRUNCATION_MARKER)
    async with SearchToolProvider(FakeSearcher(rows), fetch_tool=_noop_tool()) as tools:
        result = await tools[0].executor(tools[0].parameters(query="q"))
    assert result.content.count("z") == 10_000  # default: untouched, as in the stored runs


def _noop_tool():
    from stirrup.core.models import Tool, ToolResult

    from aastirrup.tools import WebFetchParams

    async def executor(params: WebFetchParams) -> ToolResult:
        return ToolResult(content="")

    return Tool[WebFetchParams, object](name="web_fetch", description="", parameters=WebFetchParams, executor=executor)
