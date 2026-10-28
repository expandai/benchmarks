"""Overlay suites: parsing, pinned counts, registration, and one fixture task per suite
through the real runner with mocked search HTTP and a scripted judge. Offline."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pandas as pd
import pytest
from benchmarks import get_suite, list_suites
from benchmarks.frames import SIMPLEQA_GRADER_USER_TEMPLATE
from benchmarks.graders.rag import CORRECTNESS_SYSTEM_PROMPT, GROUNDEDNESS_SYSTEM_PROMPT
from conftest import fixture, mock_client
from data.sources import SourceError
from harness import rag as rag_module
from harness.llm.judge import Judge
from harness.runner import Runner
from harness.searchers.perplexity import PerplexitySearcher
from harness.suite import Task
from harness.systems import Catalog
from test_registration import ScriptedModel, run_cli

import bakeoff.register as register
import bakeoff.suites as suites
from bakeoff.expand import ExpandSearcher

register.install()

NEW_SUITES = ("simpleqa-verified", "seal-hard", "seal-0", "aa-omniscience-public")
COUNTS = {"simpleqa-verified": 1000, "seal-hard": 254, "seal-0": 111, "aa-omniscience-public": 600}

SIMPLEQA_CSV = (
    "original_index,problem,answer,topic,answer_type,multi_step,requires_reasoning,urls\n"
    '5,"How much money, in euros, was the surgeon ordered to pay?","120,000 euros",Politics,'
    'Number,True,False,"https://a.example/x,https://b.example/y"\n'
    "8,Who is it?,Jóhanna Sigurðardóttir,Politics,Person,True,False,https://c.example/z\n"
)
AA_CSV = (
    "domain,topic,subtopic,question_id,question,answer\n"
    "Finance,Accounting,Accounting,1,Which ASC reference lists the two criteria?,ASC 606-10-25-15\n"
    "Law,Tax,Tax,42,How many categories?,4\n"
)


def sealqa_parquet() -> bytes:
    frame = pd.DataFrame(
        [
            {
                "question": "Who holds the all-time Album of the Year record?",
                "answer": "Serban Ghenea",
                "urls": np.array(["https://en.wikipedia.org/wiki/Grammy"], dtype=object),
                "freshness": "fast-changing",
                "question_types": np.array(["entity/event disambiguation"], dtype=object),
                "effective_year": "2024",
                "search_results": "conflicting",
                "topic": "Entertainment",
                "canary": "sealqa:canary",
            },
            {
                "question": "What is the current age of the oldest solo Pacific sailor?",
                "answer": "88 years old",
                "urls": np.array([], dtype=object),
                "freshness": "fast-changing",
                "question_types": np.array(["advanced reasoning", "x"], dtype=object),
                "effective_year": "2026",
                "search_results": "conflicting",
                "topic": "Sports",
                "canary": "sealqa:canary",
            },
        ]
    )
    buffer = io.BytesIO()
    frame.to_parquet(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_simpleqa_verified_rows_become_tasks():
    from data.sources import csv_rows

    tasks = suites.simpleqa_verified_tasks(csv_rows(SIMPLEQA_CSV.encode()))
    assert [t.id for t in tasks] == ["sqv-0005", "sqv-0008"]
    assert tasks[0].answer == "120,000 euros"
    assert tasks[0].metadata["urls"] == ["https://a.example/x", "https://b.example/y"]
    assert tasks[1].answer == "Jóhanna Sigurðardóttir"


def test_sealqa_parquet_rows_become_tasks():
    tasks = suites.sealqa_tasks(suites.parquet_rows(sealqa_parquet()), "seal-hard")
    assert [t.id for t in tasks] == ["seal-hard-000", "seal-hard-001"]
    assert tasks[0].problem.startswith("Who holds") and tasks[0].answer == "Serban Ghenea"
    assert tasks[1].metadata["question_types"] == ["advanced reasoning", "x"]
    assert tasks[1].metadata["urls"] == []
    json.dumps(tasks[1].metadata)  # plain Python values, no numpy arrays


def test_aa_omniscience_rows_become_tasks():
    from data.sources import csv_rows

    tasks = suites.aa_omniscience_tasks(csv_rows(AA_CSV.encode()))
    assert [t.id for t in tasks] == ["aao-001", "aao-042"]
    assert tasks[1].answer == "4" and tasks[1].metadata["domain"] == "Law"


def test_checksum_mismatch_is_refused(tmp_path):
    bad = tmp_path / "aa.csv"
    bad.write_text(AA_CSV)
    with pytest.raises(SourceError, match="SHA-256 mismatch"):
        suites.load_aa_omniscience(bad)


def test_revisions_name_the_pin_and_checksum():
    assert suites.SEALQA_REVISION in get_suite("seal-hard").revision
    assert suites.SEAL_0_SHA256[:16] in get_suite("seal-0").revision
    assert suites.SIMPLEQA_VERIFIED_REVISION in get_suite("simpleqa-verified").revision
    assert get_suite("aa-omniscience-public").revision.endswith("+grader-v1")


# ---------------------------------------------------------------------------
# Pinned counts (repository copy of AA-Omniscience; HF cache for the others)
# ---------------------------------------------------------------------------


def test_aa_omniscience_repository_copy_has_600_rows():
    tasks = suites.load_aa_omniscience()
    assert len(tasks) == 600 and len({t.id for t in tasks}) == 600
    assert {t.metadata["domain"] for t in tasks} >= {"Finance", "Law", "Software Engineering"}


def cached_hf_file(repo_id: str, filename: str, revision: str, **_: Any) -> Path:
    """Read the pinned file from the local HF cache only; skip if it was never downloaded."""
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    cache = os.environ.get("BAKEOFF_HF_CACHE", str(Path(__file__).resolve().parents[1] / ".hf-cache" / "hub"))
    try:
        return Path(
            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                revision=revision,
                repo_type="dataset",
                cache_dir=cache,
                local_files_only=True,
            )
        )
    except LocalEntryNotFoundError:
        pytest.skip(f"{repo_id}@{revision} not in {cache}; run ./bench download --suite …")


@pytest.mark.parametrize("name", ["simpleqa-verified", "seal-hard", "seal-0"])
def test_pinned_hf_sources_have_expected_counts(monkeypatch, name):
    monkeypatch.setattr(suites, "hf_file", cached_hf_file)
    tasks = get_suite(name).load()
    assert len(tasks) == COUNTS[name]
    assert len({t.id for t in tasks}) == COUNTS[name]
    assert all(t.problem.strip() and str(t.answer).strip() for t in tasks)


def test_seal_0_is_a_subset_of_seal_hard(monkeypatch):
    monkeypatch.setattr(suites, "hf_file", cached_hf_file)
    hard = {t.problem for t in get_suite("seal-hard").load()}
    zero = {t.problem for t in get_suite("seal-0").load()}
    assert zero <= hard


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_suites_are_registered_beside_upstream():
    names = list_suites()
    for name in NEW_SUITES:
        assert name in names
        assert get_suite(name).system_kinds == ("rag",)
    assert "frames" in names and "webcode-rag" in names


def test_suite_collision_is_refused(monkeypatch):
    import benchmarks

    monkeypatch.setitem(benchmarks.SUITES, "seal-0", benchmarks.SUITES["frames"])
    with pytest.raises(ValueError, match="collides"):
        register.register_suites()


def test_dry_run_covers_new_suites_including_rag_expand(monkeypatch, capsys, tmp_path):
    from harness import cli

    monkeypatch.setattr(suites, "hf_file", cached_hf_file)
    for name in ("EXPAND_API_KEY", "OPENAI_API_KEY", "PERPLEXITY_API_KEY"):
        monkeypatch.setenv(name, "test")
    monkeypatch.setattr(cli, "Runner", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    argv = ["run", "--suite", "aa-omniscience-public", "--system", "rag-expand",
            "rag-perplexity-fast", "--dry-run", "--runs-dir", str(tmp_path)]  # fmt: skip
    code, out = run_cli(argv, capsys)
    assert code == 0, out
    assert "rag-expand × aa-omniscience-public: 600 tasks" in out


# ---------------------------------------------------------------------------
# One fixture task per suite through the real runner
# ---------------------------------------------------------------------------

FIXTURE_TASK = Task(
    id="fixture-001",
    problem="How many words are in the Slackware ispell dictionary?",
    answer="38,400",
)


def offline_expand(seen: list[dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=fixture("expand_search.json"))

    def build(**options):
        searcher = ExpandSearcher(**options)
        searcher._client = mock_client(handler)
        return searcher

    return build


def offline_perplexity(seen: list[dict]):
    body = {
        "id": "px-1",
        "results": [
            {"url": "https://gnu.example/textutils", "title": "GNU text utilities",
             "snippet": "/usr/lib/ispell/ispell.words is a sorted, 38,400 word dictionary."},
            {"url": "https://gnu.example/ispell", "title": "Ispell", "snippet": "A spelling checker."},
        ],
    }  # fmt: skip

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=body)

    def build(**options):
        searcher = PerplexitySearcher(**options)
        searcher._client = mock_client(handler)
        return searcher

    return build


@pytest.mark.parametrize("suite_name", NEW_SUITES)
@pytest.mark.parametrize("system", ["rag-expand", "rag-perplexity-fast"])
async def test_fixture_task_runs_through_the_runner(monkeypatch, tmp_path, suite_name, system):
    monkeypatch.setenv("EXPAND_API_KEY", "test")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test")
    seen: list[dict] = []
    provider = "expand" if system == "rag-expand" else "perplexity"
    factory = offline_expand(seen) if provider == "expand" else offline_perplexity(seen)
    monkeypatch.setitem(register.PROVIDERS, provider, factory)
    answerer = ScriptedModel()
    monkeypatch.setattr(rag_module, "create_client", lambda *args, **kwargs: answerer)
    judge_model = ScriptedModel("openai/gpt-6-luna")

    suite = get_suite(suite_name)
    runner = Runner(
        Catalog.load().resolve(system),
        suite,
        judge=Judge("openai/gpt-6-luna", client=judge_model),
        runs_root=tmp_path,
    )
    summary = await runner.run([FIXTURE_TASK])

    assert seen and seen[0]["query"] == FIXTURE_TASK.problem
    assert summary["graded"] == 1 and summary["failed"] == 0
    assert summary["primary_metric"] == "score"
    assert summary["metrics"]["score"] == 1.0
    assert summary["metrics"]["grounded"] == 1.0
    assert summary["metrics"]["avg_citation_tokens"] > 0
    grade = json.loads((runner.task_dir(FIXTURE_TASK) / "grade.json").read_text())
    assert grade["details"]["correctness"] == "CORRECT"
    assert grade["details"]["groundedness"] == "GROUNDED"
    # Two judge calls: correctness and groundedness, each priced by the scripted client.
    assert len(judge_model.requests) == 2
    assert summary["cost"]["judge_usd"] == pytest.approx(0.0002)
    systems_prompts = [r["messages"][0]["content"] for r in judge_model.requests]
    assert GROUNDEDNESS_SYSTEM_PROMPT in systems_prompts
    assert CORRECTNESS_SYSTEM_PROMPT in systems_prompts
    correctness_user = next(
        r["messages"][-1]["content"]
        for r in judge_model.requests
        if r["messages"][0]["content"] == CORRECTNESS_SYSTEM_PROMPT
    )
    simpleqa_wrapper = SIMPLEQA_GRADER_USER_TEMPLATE.splitlines()[0]
    if suite_name == "aa-omniscience-public":
        # GroundedRAGGrader's own correctness message, as WebCode RAG.
        assert simpleqa_wrapper not in correctness_user
        assert correctness_user.startswith("Question: ")
    else:
        # FRAMES grading: the simple-evals SimpleQA user template.
        assert simpleqa_wrapper in correctness_user
        assert "Gold target: 38,400" in correctness_user
