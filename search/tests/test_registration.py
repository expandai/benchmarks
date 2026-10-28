"""Registration: catalog merge, preflight, CLI listing, and one offline WebCode RAG run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from benchmarks import get_suite
from conftest import fixture, mock_client
from harness import cli
from harness import rag as rag_module
from harness.llm.clients import ModelClient
from harness.llm.judge import Judge
from harness.llm.types import Generation, Usage
from harness.runner import Runner
from harness.systems import DEFAULT_CATALOG, Catalog, System

import bakeoff.register as register
from bakeoff.__main__ import main
from bakeoff.expand import ExpandSearcher
from bakeoff.firecrawl import FirecrawlSearcher

register.install()

UPSTREAM_SYSTEMS = 45  # systems.toml at 0d817af
OVERLAY = register.load_overlay()


def run_cli(argv: list[str], capsys) -> tuple[int, str]:
    with pytest.raises(SystemExit) as exit_info:
        main(argv)
    return exit_info.value.code, capsys.readouterr().out


def test_overlay_only_adds_entries_and_keeps_upstream_defaults():
    import tomllib

    upstream = tomllib.loads(Path(DEFAULT_CATALOG).read_text())
    catalog = Catalog.load()
    assert len(upstream["systems"]) == UPSTREAM_SYSTEMS
    assert set(upstream["systems"]) < set(catalog.systems)
    assert set(catalog.systems) - set(upstream["systems"]) == set(OVERLAY["systems"])
    assert catalog.defaults == upstream["defaults"]
    for name in upstream["systems"]:
        assert catalog.systems[name] == upstream["systems"][name]


def test_bakeoff_rag_systems_use_upstream_rag_defaults():
    catalog = Catalog.load()
    for name in ("rag-expand", "rag-firecrawl-search", "rag-exa-fast-highlights"):
        spec = catalog.resolve(name)
        assert spec.model == "openai/gpt-5.6-luna"
        assert spec.settings == {"num_results": 10}


def test_overlay_cannot_replace_upstream_entries():
    catalog = Catalog.load()
    clash = {"systems": {"rag-exa-auto-highlights": {"kind": "rag", "searcher": "expand"}}}
    with pytest.raises(ValueError, match="collides"):
        register.merge_overlay(catalog, clash)


async def test_every_bakeoff_system_builds_its_adapter(monkeypatch):
    for name in (
        "EXPAND_API_KEY",
        "FIRECRAWL_API_KEY",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "PERPLEXITY_API_KEY",
        "EXA_API_KEY",
    ):
        monkeypatch.setenv(name, "test")
    from harness.searchers.exa import ExaSearcher

    from bakeoff.deepseek import DeepSeekSearcher

    catalog = Catalog.load()
    for name in OVERLAY["systems"]:
        system = System(catalog.resolve(name))
        if "deepseek" in name:
            expected = DeepSeekSearcher
        elif "expand" in name:
            expected = ExpandSearcher
        elif "exa" in name:
            expected = ExaSearcher
        elif name == "rag-model-only":
            from bakeoff.official_rag import NullSearcher

            expected = NullSearcher
        else:
            expected = FirecrawlSearcher
        assert isinstance(system._searcher, expected)
        await system.close()


def test_list_shows_bakeoff_systems(monkeypatch, capsys):
    from rich.console import Console

    monkeypatch.setattr(cli, "console", Console(width=200))
    code, out = run_cli(["list"], capsys)
    assert code == 0
    for name in ("rag-expand", "rag-firecrawl-search", "rag-exa-fast-highlights"):
        assert name in out
    assert "(expand)" in out and "(firecrawl)" in out


def test_help_names_bakeoff_systems_and_credentials(capsys):
    code, out = run_cli(["--help"], capsys)
    assert code == 0
    assert "rag-expand" in out and "rag-firecrawl-search" in out
    assert "EXPAND_API_KEY" in out and "FIRECRAWL_API_KEY" in out


def test_dry_run_reports_missing_credentials(capsys, tmp_path):
    argv = [
        "run",
        "--suite",
        "webcode-rag",
        "--system",
        "rag-expand",
        "rag-firecrawl-search",
        "--dry-run",
        "--runs-dir",
        str(tmp_path),
    ]
    code, out = run_cli(argv, capsys)
    assert code == 2
    assert "EXPAND_API_KEY" in out and "FIRECRAWL_API_KEY" in out and "OPENAI_API_KEY" in out
    assert not list(tmp_path.iterdir())


def test_dry_run_passes_with_credentials_and_makes_no_calls(monkeypatch, capsys, tmp_path):
    for name in (
        "EXPAND_API_KEY",
        "FIRECRAWL_API_KEY",
        "OPENAI_API_KEY",
        "EXA_API_KEY",
        "PARALLEL_API_KEY",
        "PERPLEXITY_API_KEY",
    ):
        monkeypatch.setenv(name, "test")

    def no_runner(*args, **kwargs):
        raise AssertionError("dry run must not build a runner")

    monkeypatch.setattr(cli, "Runner", no_runner)
    argv = [
        "run",
        "--suite",
        "webcode-rag",
        "--system",
        "rag-expand",
        "rag-firecrawl-search",
        "rag-exa-fast-highlights",
        "rag-perplexity-fast",
        "rag-parallel-fast",
        "--dry-run",
        "--runs-dir",
        str(tmp_path),
    ]
    code, out = run_cli(argv, capsys)
    assert code == 0, out
    assert "rag-expand × webcode-rag: 307 tasks" in out
    assert "rag-firecrawl-search × webcode-rag: 307 tasks" in out
    assert "Preflight passed; no paid API calls made." in out


class ScriptedModel(ModelClient):
    """Answers RAG prompts and both GroundedRAGGrader judgments; records each request."""

    provider = "openai"
    supports_response_schema = True

    def __init__(self, model: str = "openai/gpt-5.6-luna") -> None:
        super().__init__(model)
        self.requests: list[dict[str, Any]] = []

    async def generate(self, messages, **kwargs) -> Generation:
        self.requests.append({"messages": messages, **kwargs})
        schema = (kwargs.get("response_schema") or {}).get("schema", {}).get("properties", {})
        if "groundedness" in schema:
            text = json.dumps(
                {
                    "evidence": "38,400 word dictionary",
                    "reasoning": "citation 1 states it",
                    "groundedness": "GROUNDED",
                    "source_indices": [1],
                }
            )
        elif "correctness" in schema:
            text = json.dumps({"reasoning": "matches", "correctness": "CORRECT"})
        else:
            text = "38,400 words [1]"
        return Generation(text=text, tool_calls=[], usage=Usage(100, 10), cost_usd=0.0001)


async def test_webcode_rag_runs_offline_through_the_real_runner(monkeypatch, tmp_path):
    monkeypatch.setenv("EXPAND_API_KEY", "test")
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=fixture("expand_search.json"))

    def offline_expand(**options):
        searcher = ExpandSearcher(**options)
        searcher._client = mock_client(handler)
        return searcher

    monkeypatch.setitem(register.PROVIDERS, "expand", offline_expand)
    answerer = ScriptedModel()
    monkeypatch.setattr(rag_module, "create_client", lambda *args, **kwargs: answerer)
    judge_model = ScriptedModel("openai/gpt-6-luna")

    suite = get_suite("webcode-rag")
    task = suite.load()[0]
    runner = Runner(
        Catalog.load().resolve("rag-expand"),
        suite,
        judge=Judge("openai/gpt-6-luna", client=judge_model),
        runs_root=tmp_path,
    )
    summary = await runner.run([task])

    assert seen == [{"query": task.problem, "maxResults": 10}]
    assert summary["graded"] == 1 and summary["failed"] == 0
    assert summary["metrics"]["grounded"] == 1.0
    # Three non-empty excerpts become three citations, one per page.
    assert summary["metrics"]["citation_precision"] == pytest.approx(round(1 / 3, 3))
    result = json.loads((runner.task_dir(task) / "result.json").read_text())
    assert [c["url"] for c in result["citations"]] == [
        "https://gnu.huihoo.com/textutils-1.22/html_mono/textutils.html",
        "https://www.gnu.org/software/ispell/",
        "https://www.gnu.org/software/coreutils/manual/html_node/sort-invocation.html",
    ]
    assert result["search_cost_usd"] == 0.0015 and result["cost_known"] is True
    # The answer model saw every citation.
    prompt = answerer.requests[0]["messages"][1]["content"]
    assert "38,400 word dictionary" in prompt and "The sort command" in prompt
    # The groundedness judge numbered the same three citations.
    assert "[3] URL: https://www.gnu.org/software/coreutils" in json.dumps(judge_model.requests)
