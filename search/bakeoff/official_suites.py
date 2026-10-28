"""FRAMES, SimpleQA Verified and SealQA under their designers' graders and metrics.

Same pinned datasets as upstream ``frames`` and the overlay ``simpleqa-verified`` /
``seal-0`` / ``seal-hard`` loaders; the ``revision`` strings differ so run directories never
mix with the SimpleQA-prompt/gpt-6-luna runs. Answers come from ``official_rag`` (each
suite's ``answer_protocol``); grades from ``official_graders``.

The CLI's ``--judge-model`` must name each suite's official judge (it is part of the run
hash and of ``config.json``); the suite refuses any other value so a directory label can
never disagree with the grader that produced it.

Per-task scores: the one-hot label, ``score`` (the headline accuracy), ``attempted``,
``avg_citation_tokens`` and ``num_citations`` (no judge call), ``filtered_results``.
``SimpleQAVerifiedOfficial.aggregate`` adds the official F1, accuracy given attempted,
attempted and hedged shares. F1 is a set statistic, so its CI is computed in
``runs/official/report.py`` (task bootstrap of the statistic), not by the harness.
"""

from __future__ import annotations

from typing import Any

import tiktoken
from benchmarks.frames import Frames
from data import loaders
from harness.llm.judge import Judge
from harness.suite import Grade, Suite, Task

from . import suites
from .official_graders import (
    FRAMES_JUDGE,
    SEALQA_JUDGE,
    SEALQA_JUDGE_MAX_TOKENS,
    SEALQA_JUDGE_TEMPERATURE,
    SIMPLEQA_VERIFIED_JUDGE,
    OfficialJudge,
    grade_frames,
    grade_sealqa,
    grade_simpleqa_verified,
    simpleqa_verified_metrics,
)
from .official_rag import AnswerProtocol

OFFICIAL_VERSION = "official-v1"
DEFAULT_EFFORT = AnswerProtocol(name="neutral-single-search")
HIGH_EFFORT = AnswerProtocol(name="neutral-single-search-high-reasoning", reasoning_effort="high")

_encoding = None


def citation_tokens(citations: list[dict[str, Any]]) -> dict[str, float]:
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding("o200k_base")
    counts = [len(_encoding.encode(c.get("text") or "")) for c in citations]
    return {
        "num_citations": float(len(counts)),
        "avg_citation_tokens": round(sum(counts) / len(counts), 1) if counts else 0.0,
        "total_citation_tokens": float(sum(counts)),
    }


class OfficialSuite(Suite):
    """Shared plumbing: judge check, official judge construction, citation accounting."""

    system_kinds = ("rag",)
    primary_metric = "score"
    answer_protocol: AnswerProtocol = DEFAULT_EFFORT
    judge_model: str
    judge_temperature: float | None = None
    judge_max_output_tokens: int = 16_000

    def official_judge(self, judge: Judge) -> OfficialJudge:
        if judge.model != self.judge_model:
            raise ValueError(
                f"{self.name} grades with {self.judge_model}; run with --judge-model {self.judge_model} "
                f"(got {judge.model})"
            )
        return OfficialJudge(
            self.judge_model,
            temperature=self.judge_temperature,
            max_output_tokens=self.judge_max_output_tokens,
            client=judge._client,  # tests inject a scripted client; None → real client
        )

    async def grade_answer(self, task: Task, answer: str, judge: OfficialJudge) -> Grade:
        raise NotImplementedError

    async def grade_result(self, task: Task, result: dict[str, Any], judge: Judge) -> Grade:
        grade = await self.grade_answer(task, result["answer"], self.official_judge(judge))
        grade.scores.update(citation_tokens(result.get("citations", [])))
        grade.scores["filtered_results"] = float(len(result.get("filtered_results", [])))
        grade.scores["query_clipped"] = 1.0 if result.get("query_clipped") else 0.0
        return grade


class FramesOfficial(OfficialSuite):
    name = "frames-official"
    description = "FRAMES, Figure 6 TRUE/FALSE grader (gpt-4.1 substitute), accuracy"
    revision = f"{loaders.FRAMES_REVISION}+fig6-{FRAMES_JUDGE.split('/')[1]}-{OFFICIAL_VERSION}"
    judge_model = FRAMES_JUDGE

    def load(self) -> list[Task]:
        return Frames().load()

    async def grade_answer(self, task: Task, answer: str, judge: OfficialJudge) -> Grade:
        return await grade_frames(judge, task.problem, str(task.answer), answer)


class SimpleQAVerifiedOfficial(OfficialSuite):
    name = "simpleqa-verified-official"
    description = "SimpleQA Verified, Appendix A grader on gpt-4.1, F1 headline"
    revision = (
        f"{suites.SIMPLEQA_VERIFIED_REPO}@{suites.SIMPLEQA_VERIFIED_REVISION}/"
        f"{suites.SIMPLEQA_VERIFIED_FILE}#sha256={suites.SIMPLEQA_VERIFIED_SHA256[:16]}"
        f"+appendix-a-{SIMPLEQA_VERIFIED_JUDGE.split('/')[1]}-{OFFICIAL_VERSION}"
    )
    judge_model = SIMPLEQA_VERIFIED_JUDGE

    def load(self) -> list[Task]:
        return suites.load_simpleqa_verified()

    async def grade_answer(self, task: Task, answer: str, judge: OfficialJudge) -> Grade:
        return await grade_simpleqa_verified(judge, task.problem, str(task.answer), answer)

    def aggregate(self, grades: list[Grade]) -> dict[str, float]:
        metrics = super().aggregate(grades)
        counts = {
            key: int(round(sum(g.scores.get(key, 0.0) for g in grades)))
            for key in ("correct", "incorrect", "not_attempted")
        }
        official = simpleqa_verified_metrics(**counts)
        metrics.update({k: v for k, v in official.items() if k != "accuracy"})
        return metrics


class SealQAOfficial(OfficialSuite):
    answer_protocol = HIGH_EFFORT
    judge_model = SEALQA_JUDGE
    judge_temperature = SEALQA_JUDGE_TEMPERATURE
    judge_max_output_tokens = SEALQA_JUDGE_MAX_TOKENS
    sealqa_file: str
    sealqa_sha256: str
    sealqa_rows: int
    sealqa_prefix: str

    def load(self) -> list[Task]:
        return suites.load_sealqa(self.sealqa_file, self.sealqa_sha256, self.sealqa_rows, self.sealqa_prefix)

    async def grade_answer(self, task: Task, answer: str, judge: OfficialJudge) -> Grade:
        return await grade_sealqa(judge, task.problem, str(task.answer), answer)


def _sealqa_revision(filename: str, sha256: str) -> str:
    return (
        f"{suites.SEALQA_REPO}@{suites.SEALQA_REVISION}/{filename}#sha256={sha256[:16]}"
        f"+appendix-c-{SEALQA_JUDGE.split('/')[1]}-{OFFICIAL_VERSION}"
    )


class Seal0Official(SealQAOfficial):
    name = "seal-0-official"
    description = "SealQA Seal-0, Appendix C grader on gpt-4o-mini (temperature 0), accuracy"
    revision = _sealqa_revision(suites.SEAL_0_FILE, suites.SEAL_0_SHA256)
    sealqa_file = suites.SEAL_0_FILE
    sealqa_sha256 = suites.SEAL_0_SHA256
    sealqa_rows = suites.SEAL_0_ROWS
    sealqa_prefix = "seal-0"


class SealHardOfficial(SealQAOfficial):
    name = "seal-hard-official"
    description = "SealQA Seal-Hard, Appendix C grader on gpt-4o-mini (temperature 0), accuracy"
    revision = _sealqa_revision(suites.SEAL_HARD_FILE, suites.SEAL_HARD_SHA256)
    sealqa_file = suites.SEAL_HARD_FILE
    sealqa_sha256 = suites.SEAL_HARD_SHA256
    sealqa_rows = suites.SEAL_HARD_ROWS
    sealqa_prefix = "seal-hard"


SUITES: dict[str, type[Suite]] = {
    suite.name: suite
    for suite in (FramesOfficial, SimpleQAVerifiedOfficial, Seal0Official, SealHardOfficial)
}
