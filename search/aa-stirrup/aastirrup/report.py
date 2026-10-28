"""Aggregate a run directory into the results table and a full-public-set (600) extrapolation.

Headline OI and accuracy count a question that ended in an execution error (after every retry) as
NOT_ATTEMPTED over all ``expected`` questions, with 95 % task-bootstrap CIs (upstream
``harness.statistics.bootstrap_mean``: 10,000 resamples, seed 0); the graded-only figures are kept as
``omniscience_index`` / ``accuracy``.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from bakeoff.pricing import search_usd
from harness.statistics import bootstrap_mean

from .omniscience import CORRECT, INCORRECT, NOT_ATTEMPTED, score
from .systems import SYSTEMS

FULL_SET = 600


def load_records(run_dir: Path, system: str) -> list[dict[str, Any]]:
    folder = run_dir / system
    if not folder.exists():
        return []
    return [json.loads(path.read_text()) for path in sorted(folder.glob("aao-*.json"))]


def record_search_usd(system: str, record: dict[str, Any]) -> float:
    """Search cost of a question record, list-priced for the searchers in ``bakeoff.pricing``
    (billed searches are the calls with a non-zero stored cost)."""
    searcher = SYSTEMS[system].searcher if system in SYSTEMS else None
    searches = record.get("tools", {}).get("searches", [])
    billed = sum(1 for s in searches if (s["cost_usd"] or 0.0) > 0)
    return search_usd(searcher, record["search"]["cost_usd"], billed)


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _ci(values: list[float]) -> dict[str, float | None]:
    interval = bootstrap_mean(values)
    return {"mean": interval.estimate, "low": interval.low, "high": interval.high}


def failed_as_zero(grades: list[str], errors: int) -> dict[str, Any]:
    """OI and accuracy (percent) with each errored question scored NOT_ATTEMPTED, plus CIs."""
    all_grades = grades + [NOT_ATTEMPTED] * errors
    scored = score(all_grades)
    oi = [100.0 * ((g == CORRECT) - (g == INCORRECT)) for g in all_grades]
    acc = [100.0 * (g == CORRECT) for g in all_grades]
    return {
        "n_failed_as_zero": scored["n"],
        "omniscience_index_failed_as_zero": scored["omniscience_index"],
        "accuracy_failed_as_zero": scored["accuracy"],
        "omniscience_index_failed_as_zero_ci": _ci(oi) if oi else None,
        "accuracy_failed_as_zero_ci": _ci(acc) if acc else None,
    }


def summarize(run_dir: Path, system: str, expected: int) -> dict[str, Any] | None:
    records = load_records(run_dir, system)
    if not records:
        return None
    if len(records) > expected:
        raise ValueError(f"{system}: {len(records)} records exceed the manifest's {expected} questions")
    missing = expected - len(records)
    done = [r for r in records if r["status"] == "complete"]
    errors = [r for r in records if r["status"] != "complete"]
    summary: dict[str, Any] = {
        "system": system,
        "label": SYSTEMS[system].label if system in SYSTEMS else system,
        "expected": expected,
        "complete": len(done),
        "errors": len(errors),
        "missing": missing,
        "error_samples": sorted({r.get("error", "")[:200] for r in errors})[:3],
        **score([r["grade"] for r in done]),
        **failed_as_zero([r["grade"] for r in done], len(errors) + missing),
        "unfinished": sum(not r["finished"] for r in done),
    }
    if not done:
        return summary
    n = len(done)
    answer = [r["usage"]["answer"] for r in done]
    grader = [r["usage"]["grader"] for r in done]
    search_cost = sum(record_search_usd(system, r) for r in done)
    model_cost = sum(u["cost_usd"] for u in answer)
    grader_cost = sum(u["cost_usd"] for u in grader)
    starts = [r["started_at"] for r in records]
    ends = [r["started_at"] + r["wall_seconds"] for r in records]
    summary.update(
        {
            "searches_per_q": sum(r["search"]["calls"] for r in done) / n,
            "fetches_per_q": sum(r["search"]["fetches"] for r in done) / n,
            "turns_per_q": sum(r["turns"] for r in done) / n,
            "filtered_results": sum(r["search"]["filtered_results"] for r in done),
            "input_tokens_per_q": sum(u["input_tokens"] for u in answer) / n,
            "cached_tokens_per_q": sum(u["cached_tokens"] for u in answer) / n,
            "output_tokens_per_q": sum(u["output_tokens"] for u in answer) / n,
            "reasoning_tokens_per_q": sum(u["reasoning_tokens"] for u in answer) / n,
            "grader_tokens_per_q": sum(u["input_tokens"] + u["output_tokens"] for u in grader) / n,
            "search_usd_per_q": search_cost / n,
            "model_usd_per_q": model_cost / n,
            "grader_usd_per_q": grader_cost / n,
            "total_usd_per_q": (search_cost + model_cost + grader_cost) / n,
            "cost_missing_calls": sum(u["cost_missing_calls"] for u in answer + grader)
            + sum(r["search"]["cost_missing_calls"] for r in done),
            "wall_s_mean": _mean([r["wall_seconds"] for r in done]),
            "wall_s_p50": statistics.median([r["wall_seconds"] for r in done]),
            "wall_s_max": max(r["wall_seconds"] for r in done),
            "search_s_per_q": sum(r["search"]["seconds"] for r in done) / n,
            "s_per_search": (
                sum(r["search"]["seconds"] for r in done) / max(1, sum(r["search"]["calls"] for r in done))
            ),
            "model_s_per_q": _mean([r["model_seconds"] for r in done if r.get("model_seconds") is not None]),
            "elapsed_s": max(ends) - min(starts),
        }
    )
    concurrency = SYSTEMS[system].concurrency if system in SYSTEMS else 10
    summary["full_set_usd"] = summary["total_usd_per_q"] * FULL_SET
    summary["full_set_search_usd"] = summary["search_usd_per_q"] * FULL_SET
    summary["full_set_hours_at_concurrency"] = summary["wall_s_mean"] * FULL_SET / concurrency / 3600
    summary["concurrency"] = concurrency
    return summary


def _f(value: Any, digits: int = 1) -> str:
    if value is None:
        return "–"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _with_ci(interval: dict[str, Any] | None) -> str:
    if not interval or interval.get("mean") is None:
        return "–"
    if interval.get("low") is None:
        return f"{interval['mean']:.1f}"
    return f"{interval['mean']:.1f} [{interval['low']:.1f}–{interval['high']:.1f}]"


def markdown(summaries: list[dict[str, Any]]) -> str:
    lines = [
        "| System | n | OI [95% CI] | Acc % [95% CI] | C / I / P / NA | Halluc. % | Searches/q | Fetches/q | Turns/q "
        "| In tok/q (cached) | Out tok/q (reasoning) | Search $/q | Model $/q | Grader $/q | Total $/q "
        "| Wall s/q mean (p50) | s/search | Errors |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in summaries:
        if not s.get("complete"):
            lines.append(f"| {s['label']} | 0 | | | | | | | | | | | | | | | | {s['errors']} |")
            continue
        lines.append(
            f"| {s['label']} | {s['n_failed_as_zero']} | {_with_ci(s['omniscience_index_failed_as_zero_ci'])} "
            f"| {_with_ci(s['accuracy_failed_as_zero_ci'])} "
            f"| {s['correct']} / {s['incorrect']} / {s['partial']} / {s['not_attempted']} "
            f"| {_f(s['hallucination_rate'])} | {_f(s['searches_per_q'])} | {_f(s['fetches_per_q'])} "
            f"| {_f(s['turns_per_q'])} | {s['input_tokens_per_q']:,.0f} ({s['cached_tokens_per_q']:,.0f}) "
            f"| {s['output_tokens_per_q']:,.0f} ({s['reasoning_tokens_per_q']:,.0f}) "
            f"| {s['search_usd_per_q']:.4f} | {s['model_usd_per_q']:.4f} | {s['grader_usd_per_q']:.4f} "
            f"| {s['total_usd_per_q']:.4f} | {_f(s['wall_s_mean'], 0)} ({_f(s['wall_s_p50'], 0)}) "
            f"| {_f(s['s_per_search'], 2)} | {s['errors']} |"
        )
    incomplete = [s for s in summaries if s.get("missing", 0)]
    if incomplete:
        lines += [
            "",
            "INCOMPLETE RUN: " + "; ".join(
                f"{s['label']} is missing {s['missing']} of {s['expected']} question records"
                for s in incomplete
            ) + ". Missing questions count as not attempted; these are not final benchmark results.",
        ]
    failed = [s for s in summaries if s.get("complete") and s["errors"]]
    if failed:
        lines += [
            "",
            "OI and accuracy count each question that ended in an execution error as not attempted, over all "
            "questions; C / I / P / NA are the graded questions. Graded only: "
            + "; ".join(
                f"{s['label']} OI {_f(s['omniscience_index'])}, accuracy {_f(s['accuracy'])} on {s['complete']}"
                for s in failed
            )
            + ".",
        ]
    lines += [
        "",
        f"| System | Full public set ({FULL_SET}) $ | of which search $ | Hours at concurrency | Concurrency |",
        "|---|---|---|---|---|",
    ]
    for s in summaries:
        if s.get("complete"):
            lines.append(
                f"| {s['label']} | {s['full_set_usd']:.2f} | {s['full_set_search_usd']:.2f} "
                f"| {s['full_set_hours_at_concurrency']:.2f} | {s['concurrency']} |"
            )
    return "\n".join(lines)
