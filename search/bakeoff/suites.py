"""Extra RAG suites for the bakeoff on upstream's graders, registered beside the upstream ones
without an edit. The official-grader variants (``official_suites``) reuse these loaders.

* ``simpleqa-verified`` — Google DeepMind's 1,000-question SimpleQA Verified
  (HF ``google/simpleqa-verified``).
* ``seal-hard`` / ``seal-0`` — SealQA's 254 and 111 questions where search returns
  conflicting or stale evidence (HF ``vtllms/sealqa``). SEAL-0 is a subset of SEAL-Hard.
  Answers are refreshed upstream every few weeks, so the revision pin matters.
* ``aa-omniscience-public`` — Artificial Analysis' 600 public Omniscience questions
  (HF ``ArtificialAnalysis/AA-Omniscience-Public``). Not comparable to AA's private 600.

Every source is pinned to a Hugging Face commit and its bytes are checked against a
SHA-256 recorded here, the way upstream pins BrowseComp. AA-Omniscience reads the
repository copy (``data/``) when present, checked against the same SHA-256. Task ids are
stable per pin.

Grading:

* SimpleQA Verified and SealQA are graded exactly as upstream grades FRAMES (the
  simple-evals SimpleQA prompt pair via ``Frames.grade``: ``score`` = CORRECT), plus
  the groundedness judgment of upstream's ``GroundedRAGGrader`` over the citations the
  system retrieved (``grounded`` = not UNGROUNDED), with the same citation metrics.
  The two judge calls run concurrently.
* AA-Omniscience is graded by ``GroundedRAGGrader`` unchanged, exactly as WebCode RAG.

All four suites are ``rag``-only: groundedness needs the retrieved citations.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any

import pandas as pd
import tiktoken
from benchmarks.frames import Frames
from benchmarks.graders import Citation, GroundedRAGGrader
from benchmarks.graders.base import gather_judgments
from data.sources import SourceError, csv_rows, hf_file, require_count
from harness.llm.judge import Judge
from harness.suite import Grade, Suite, Task

GRADER_VERSION = "grader-v1"

SIMPLEQA_VERIFIED_REPO = "google/simpleqa-verified"
SIMPLEQA_VERIFIED_REVISION = "0dc97e0d28d8233463e005cdc4475cc2a13ba2dc"  # 2026-03-09
SIMPLEQA_VERIFIED_FILE = "simpleqa_verified.csv"
SIMPLEQA_VERIFIED_SHA256 = "b5db21155444763543fe31b67e7cf28ce2bb225742a5b889421c5f182e2f92f5"
SIMPLEQA_VERIFIED_ROWS = 1000

SEALQA_REPO = "vtllms/sealqa"
SEALQA_REVISION = "0c298f519c871579c75920189b3858da29fe2c81"  # 2026-09-21, "update 092126"
SEAL_HARD_FILE = "seal-hard.parquet"
SEAL_HARD_SHA256 = "5bc6df2bf5012782675cbfc36a991d264320e4edcb332db60da2119b61383beb"
SEAL_HARD_ROWS = 254
SEAL_0_FILE = "seal-0.parquet"
SEAL_0_SHA256 = "381c9f86039c16570ee8d74ecbc3e687b553b21f7ebd7828a3d6a9e8f4705e7c"
SEAL_0_ROWS = 111

AA_OMNISCIENCE_REPO = "ArtificialAnalysis/AA-Omniscience-Public"
AA_OMNISCIENCE_REVISION = "e4883edbb9f5ccf2b2a8fdc6fb65e01a58e99849"  # 2026-08-24
AA_OMNISCIENCE_FILE = "AA-Omniscience_dataset_public.csv"
AA_OMNISCIENCE_SHA256 = "1e04603dafa3bd0d16d8151f07a5eb74c43d90c3a85d2fca120da2359174d02f"
AA_OMNISCIENCE_ROWS = 600
# The same bytes, already in this repository (checked 2026-10-26: identical SHA-256).
AA_OMNISCIENCE_LOCAL = (
    Path(__file__).resolve().parents[1]
    / "data"
    / AA_OMNISCIENCE_FILE
)


def verified_bytes(data: bytes, sha256: str, label: str) -> bytes:
    actual = hashlib.sha256(data).hexdigest()
    if actual != sha256:
        raise SourceError(f"SHA-256 mismatch for {label}: expected {sha256}, got {actual}")
    return data


def pinned_hf_bytes(repo_id: str, filename: str, revision: str, sha256: str) -> bytes:
    """One file from a dataset repo at a pinned commit, verified against its SHA-256."""
    path = hf_file(repo_id, filename, revision)
    return verified_bytes(path.read_bytes(), sha256, f"{repo_id}@{revision}/{filename}")


def pin(repo_id: str, revision: str, filename: str, sha256: str) -> str:
    return f"{repo_id}@{revision}/{filename}#sha256={sha256[:16]}+{GRADER_VERSION}"


# ---------------------------------------------------------------------------
# Parsing (pure; unit-tested on fixture rows)
# ---------------------------------------------------------------------------


def as_list(value: Any) -> list[str]:
    """Parquet list cells arrive as numpy arrays; CSV cells as comma-joined strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [part for part in value.split(",") if part]
    return [str(item) for item in value]


def simpleqa_verified_tasks(rows: list[dict[str, str]]) -> list[Task]:
    """Ids come from ``original_index`` (the row's index in the original SimpleQA)."""
    return [
        Task(
            id=f"sqv-{int(row['original_index']):04d}",
            problem=row["problem"],
            answer=row["answer"],
            metadata={
                "original_index": int(row["original_index"]),
                "topic": row.get("topic", ""),
                "answer_type": row.get("answer_type", ""),
                "multi_step": row.get("multi_step", ""),
                "requires_reasoning": row.get("requires_reasoning", ""),
                "urls": as_list(row.get("urls")),
            },
        )
        for row in rows
    ]


def sealqa_tasks(rows: list[dict[str, Any]], prefix: str) -> list[Task]:
    """SealQA has no id column; ids are the row index at the pinned revision."""
    return [
        Task(
            id=f"{prefix}-{index:03d}",
            problem=str(row["question"]),
            answer=str(row["answer"]),
            metadata={
                "topic": row.get("topic"),
                "freshness": row.get("freshness"),
                "effective_year": row.get("effective_year"),
                "search_results": row.get("search_results"),
                "question_types": as_list(row.get("question_types")),
                "urls": as_list(row.get("urls")),
                "canary": row.get("canary"),
            },
        )
        for index, row in enumerate(rows)
    ]


def aa_omniscience_tasks(rows: list[dict[str, str]]) -> list[Task]:
    return [
        Task(
            id=f"aao-{int(row['question_id']):03d}",
            problem=row["question"],
            answer=row["answer"],
            metadata={
                "domain": row["domain"],
                "topic": row["topic"],
                "subtopic": row["subtopic"],
            },
        )
        for row in rows
    ]


def parquet_rows(data: bytes) -> list[dict[str, Any]]:
    return pd.read_parquet(io.BytesIO(data)).to_dict("records")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_simpleqa_verified() -> list[Task]:
    data = pinned_hf_bytes(
        SIMPLEQA_VERIFIED_REPO,
        SIMPLEQA_VERIFIED_FILE,
        SIMPLEQA_VERIFIED_REVISION,
        SIMPLEQA_VERIFIED_SHA256,
    )
    rows = csv_rows(data)
    require_count("simpleqa-verified", len(rows), SIMPLEQA_VERIFIED_ROWS)
    return simpleqa_verified_tasks(rows)


def load_sealqa(filename: str, sha256: str, rows_expected: int, prefix: str) -> list[Task]:
    data = pinned_hf_bytes(SEALQA_REPO, filename, SEALQA_REVISION, sha256)
    rows = parquet_rows(data)
    require_count(prefix, len(rows), rows_expected)
    return sealqa_tasks(rows, prefix)


def load_aa_omniscience(local: Path = AA_OMNISCIENCE_LOCAL) -> list[Task]:
    """Read the repository copy when present, else the pinned HF file; same SHA-256 either way."""
    if local.exists():
        data = verified_bytes(local.read_bytes(), AA_OMNISCIENCE_SHA256, str(local))
    else:
        data = pinned_hf_bytes(
            AA_OMNISCIENCE_REPO, AA_OMNISCIENCE_FILE, AA_OMNISCIENCE_REVISION, AA_OMNISCIENCE_SHA256
        )
    rows = csv_rows(data)
    require_count("aa-omniscience-public", len(rows), AA_OMNISCIENCE_ROWS)
    return aa_omniscience_tasks(rows)


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------


def citations_of(result: dict[str, Any]) -> list[Citation]:
    return [Citation(url=c["url"], title=c["title"], text=c["text"]) for c in result["citations"]]


def citation_scores(citations: list[Citation], source_indices: list[int]) -> dict[str, float]:
    """The citation metrics ``GroundedRAGGrader.grade`` computes, computed the same way."""
    matching = GroundedRAGGrader._extract_source_urls(source_indices, citations)
    encoding = tiktoken.get_encoding("o200k_base")
    counts = [len(encoding.encode(c.text)) for c in citations]
    return {
        "citation_precision": round(len(matching) / len(citations), 3) if citations else 0.0,
        "avg_citation_tokens": round(sum(counts) / len(counts), 1) if counts else 0.0,
        "total_citation_tokens": float(sum(counts)),
    }


class SimpleQAStyleRAG(Frames):
    """FRAMES' SimpleQA-prompt correctness plus GroundedRAGGrader groundedness."""

    primary_metric = "score"
    system_kinds = ("rag",)

    async def grade_result(self, task: Task, result: dict[str, Any], judge: Judge) -> Grade:
        citations = citations_of(result)
        grader = GroundedRAGGrader(judge)
        # ``_call_groundedness`` is the exact groundedness call GroundedRAGGrader.grade makes
        # (prompt, citation numbering, schema); the upstream pin keeps it stable.
        correctness, groundedness = await gather_judgments(
            self.grade(task, result["answer"], judge),
            grader._call_groundedness(task.problem, str(task.answer), citations),
        )
        grounded = 0.0 if groundedness.groundedness == "UNGROUNDED" else 1.0
        scores = {
            **correctness.scores,
            "grounded": grounded,
            **citation_scores(citations, groundedness.source_indices),
        }
        details = {
            **correctness.details,
            "correctness": correctness.details.get("label", "NOT_ATTEMPTED"),
            "groundedness": groundedness.groundedness,
            "groundedness_reasoning": groundedness.reasoning,
            "evidence": groundedness.evidence,
            "answer_source_urls": GroundedRAGGrader._extract_source_urls(
                groundedness.source_indices, citations
            ),
            "judge_calls": correctness.details.get("judge_calls", 0) + 1,
        }
        return Grade(scores=scores, details=details, judge_cost_usd=correctness.judge_cost_usd)


class SimpleQAVerified(SimpleQAStyleRAG):
    name = "simpleqa-verified"
    description = "SimpleQA Verified: 1,000 short factual questions (Google DeepMind)"
    revision = pin(
        SIMPLEQA_VERIFIED_REPO,
        SIMPLEQA_VERIFIED_REVISION,
        SIMPLEQA_VERIFIED_FILE,
        SIMPLEQA_VERIFIED_SHA256,
    )

    def load(self) -> list[Task]:
        return load_simpleqa_verified()


class SealHard(SimpleQAStyleRAG):
    name = "seal-hard"
    description = "SealQA SEAL-Hard: 254 questions with conflicting search evidence"
    revision = pin(SEALQA_REPO, SEALQA_REVISION, SEAL_HARD_FILE, SEAL_HARD_SHA256)

    def load(self) -> list[Task]:
        return load_sealqa(SEAL_HARD_FILE, SEAL_HARD_SHA256, SEAL_HARD_ROWS, "seal-hard")


class Seal0(SimpleQAStyleRAG):
    name = "seal-0"
    description = "SealQA SEAL-0: 111 SEAL-Hard questions frontier models got 0/10 on"
    revision = pin(SEALQA_REPO, SEALQA_REVISION, SEAL_0_FILE, SEAL_0_SHA256)

    def load(self) -> list[Task]:
        return load_sealqa(SEAL_0_FILE, SEAL_0_SHA256, SEAL_0_ROWS, "seal-0")


class AAOmnisciencePublic(Suite):
    """GroundedRAGGrader unchanged, as WebCode RAG uses it."""

    name = "aa-omniscience-public"
    description = "AA-Omniscience public: 600 questions, 6 domains (not AA's private 600)"
    primary_metric = "score"
    system_kinds = ("rag",)
    revision = pin(
        AA_OMNISCIENCE_REPO, AA_OMNISCIENCE_REVISION, AA_OMNISCIENCE_FILE, AA_OMNISCIENCE_SHA256
    )

    def load(self) -> list[Task]:
        return load_aa_omniscience()

    async def grade_result(self, task: Task, result: dict[str, Any], judge: Judge) -> Grade:
        return await GroundedRAGGrader(judge).grade(
            task.problem, str(task.answer), result["answer"], citations_of(result)
        )


SUITES: dict[str, type[Suite]] = {
    suite.name: suite for suite in (SimpleQAVerified, SealHard, Seal0, AAOmnisciencePublic)
}
