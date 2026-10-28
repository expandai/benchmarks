"""Tavily and Brave as comparator systems: the upstream catalog entries resolve through the overlay's
registry, preflight names the right credentials, and the official-grader pipeline (neutral prompt +
leak filter) accepts them unchanged. Offline."""

from __future__ import annotations

import json

import httpx
import pytest
from benchmarks import get_suite
from conftest import mock_client
from harness import cli
from harness import rag as rag_module
from harness.llm.judge import Judge
from harness.runner import Runner
from harness.searchers.brave import BraveSearcher
from harness.searchers.tavily import TavilySearcher
from harness.systems import Catalog
from test_official import TASK, ScriptedAnswerer, ScriptedJudge
from test_registration import run_cli

import bakeoff.register as register

register.install()

COMPARATORS = {
    "rag-tavily-advanced": ("tavily", TavilySearcher, ("TAVILY_API_KEY",)),
    "rag-brave-llm-context": ("brave", BraveSearcher, ("BRAVE_SEARCH_API_KEY", "BRAVE_API_KEY")),
}

TAVILY_BODY = {
    "request_id": "tv-1",
    "results": [
        {"url": "https://example.com/a", "title": "A", "content": "snippet a", "score": 0.9, "published_date": "2026-01-01"},
        {"url": "https://huggingface.co/datasets/google/simpleqa-verified", "title": "SimpleQA Verified", "content": "gold"},
        {"url": "https://example.org/b", "title": "B", "content": "snippet b", "score": 0.5},
    ],
    "usage": {"credits": 2},
}
BRAVE_BODY = {
    "grounding": {
        "generic": [
            {"url": "https://example.com/a", "title": "A", "snippets": ["page text a", "more a"]},
            {"url": "https://huggingface.co/datasets/google/simpleqa-verified", "title": "SimpleQA Verified", "snippets": ["gold"]},
            {"url": "https://example.org/b", "title": "B", "snippets": ["page text b"]},
        ]
    },
    "sources": {"https://example.com/a": {"age": [None, "2026-01-01"]}},
}


@pytest.mark.parametrize("system", sorted(COMPARATORS))
def test_catalog_resolves_upstream_comparators_through_the_overlay(system, monkeypatch):
    provider, cls, env_names = COMPARATORS[system]
    monkeypatch.setenv(env_names[-1], "test")
    spec = Catalog.load().resolve(system)
    assert spec.kind == "rag" and spec.searcher["provider"] == provider
    assert spec.settings.get("num_results", 10) == 10  # upstream [defaults.rag], shared by every system
    from harness import systems

    entry = dict(spec.searcher)
    entry.pop("name")
    searcher = systems.build_searcher(entry.pop("provider"), entry)
    assert isinstance(searcher, cls)


@pytest.mark.parametrize("system", sorted(COMPARATORS))
def test_preflight_names_the_providers_credentials(system):
    provider, _, env_names = COMPARATORS[system]
    assert cli.PROVIDER_KEYS[provider] == env_names
    spec = Catalog.load().resolve(system)
    assert " or ".join(env_names) in cli.missing_credentials(spec, "openai/gpt-4o-mini")


def test_dry_run_without_keys_names_tavily_and_brave_variables(capsys, tmp_path):
    # webcode-rag ships with the upstream clone, so this needs no dataset download; the official suites
    # take the same path once `make download` has filled .hf-cache.
    code, out = run_cli(
        ["run", "--suite", "webcode-rag", "--system", "rag-tavily-advanced", "rag-brave-llm-context",
         "--dry-run", "--runs-dir", str(tmp_path)],
        capsys,
    )  # fmt: skip
    assert code == 2
    assert "rag-tavily-advanced × webcode-rag: 307 tasks" in out
    assert "rag-brave-llm-context × webcode-rag: 307 tasks" in out
    flat = " ".join(out.split())  # the console wraps long lines
    assert "rag-tavily-advanced × webcode-rag: missing OPENAI_API_KEY, TAVILY_API_KEY" in flat
    assert "rag-brave-llm-context × webcode-rag: missing BRAVE_SEARCH_API_KEY or BRAVE_API_KEY, OPENAI_API_KEY" in flat
    assert not list(tmp_path.iterdir())


def _offline(cls, body, seen: list[dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"url": str(request.url), "body": json.loads(request.content) if request.content else dict(request.url.params)})
        return httpx.Response(200, json=body)

    def build(**options):
        searcher = cls(**options)
        searcher._client = mock_client(handler)
        return searcher

    return build


@pytest.mark.parametrize(
    ("system", "cls", "body", "key"),
    [
        ("rag-tavily-advanced", TavilySearcher, TAVILY_BODY, "TAVILY_API_KEY"),
        ("rag-brave-llm-context", BraveSearcher, BRAVE_BODY, "BRAVE_API_KEY"),
    ],
)
async def test_official_suite_runs_comparators_with_the_leak_filter(monkeypatch, tmp_path, system, cls, body, key):
    monkeypatch.setenv(key, "test")
    provider = COMPARATORS[system][0]
    seen: list[dict] = []
    monkeypatch.setitem(register.PROVIDERS, provider, _offline(cls, body, seen))
    monkeypatch.setattr(rag_module, "create_client", lambda *a, **k: ScriptedAnswerer())
    judge_client = ScriptedJudge("openai/gpt-4o-mini", ["A"])

    runner = Runner(
        Catalog.load().resolve(system),
        get_suite("seal-0-official"),
        judge=Judge("openai/gpt-4o-mini", client=judge_client),
        runs_root=tmp_path,
    )
    summary = await runner.run([TASK])

    assert len(seen) == 1  # one search per question
    assert summary["graded"] == 1 and summary["failed"] == 0
    assert summary["metrics"]["score"] == 1.0
    assert summary["metrics"]["num_citations"] == 2.0  # the Hugging Face dataset page was leak-filtered
    assert summary["metrics"]["filtered_results"] == 1.0
    result = json.loads(next(tmp_path.rglob("result.json")).read_text())
    assert result["search_cost_usd"] == pytest.approx(0.016 if cls is TavilySearcher else 0.005)
    assert [c["url"] for c in result["citations"]] == ["https://example.com/a", "https://example.org/b"]
