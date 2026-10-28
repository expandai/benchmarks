"""Per-suite results tables for every bakeoff suite under runs/ (other than official/) and total spend.

Run directories (``<system>-<suite>-<hash>/`` with ``config.json`` and ``tasks/*/{result,grade,
cost,error}.json``) are collected per suite from:

* ``runs/pilot-20/`` (WebCode only: the six competitors' 307-task runs),
* ``runs/<suite>/`` (run-suite.sh output).

If two directories hold the same system for a suite, reporting fails until exactly one run
is selected in these roots; keep reruns in a separate output root. OpenRouter
transport counters come from ``<dir>/logs/<system>.log``.

CIs are recomputed from the per-task grades with upstream's ``harness.statistics.bootstrap_mean``
(percentile bootstrap over tasks, 10,000 resamples, seed 0), so they match ``summary.json``. The
table's headline columns count terminal failures (a task that ended in ``error.json`` after every
pass) as zero over the full suite; ``grounded`` / ``score`` in report.json are over graded tasks.

    "$EXA_BENCH_VENV/bin/python" runs/report.py            # tables -> stdout, runs/report.json
    "$EXA_BENCH_VENV/bin/python" runs/report.py --spend    # spend only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
from _records import by_system_order, ci, citation_count, mean, p90, pct, read, read_all, result_search_usd, run_dirs, searcher_name, task_dirs, transport  # noqa: E402
import tiktoken  # noqa: E402

SUITE_TASKS: dict[str, int] = {
    "webcode-rag": 307,
    "frames": 824,
    "simpleqa-verified": 1000,
    "seal-hard": 254,
    "seal-0": 111,
    "aa-omniscience-public": 600,
}


def citation_tokens(encoding: Any, citation: dict[str, Any]) -> int:
    """o200k tokens of one citation of a fresh run (``text``, or ``text_tokens`` once redacted)."""
    if "text" in citation:
        return len(encoding.encode(citation.get("text") or "", disallowed_special=()))
    return int(citation.get("text_tokens", 0))


def mean_citation_tokens(encoding: Any, result: dict[str, Any]) -> float:
    """Mean o200k tokens per citation of a ``result.json``. Stored records keep only the per-record
    totals ``num_citations`` / ``citation_text_tokens`` (runs/EXCLUDED.md)."""
    if "citations" in result:
        return mean([citation_tokens(encoding, c) for c in result["citations"]])
    count = citation_count(result)
    return result.get("citation_text_tokens", 0) / count if count else 0.0


def suite_dirs(suite: str) -> list[str]:
    return (["pilot-20"] if suite == "webcode-rag" else []) + [suite]


def system_row(run_dir: Path, suite_tasks: int, log_dir: Path) -> dict[str, Any]:
    config = read(run_dir / "config.json")
    system = config["system"]["name"]
    tasks = task_dirs(run_dir)
    results = read_all([p / "result.json" for p in tasks if (p / "result.json").exists()])
    grades = read_all([p / "grade.json" for p in tasks if (p / "grade.json").exists()])
    costs = read_all([p / "cost.json" for p in tasks if (p / "cost.json").exists()])
    errors = [p.name for p in tasks if (p / "error.json").exists() and not (p / "grade.json").exists()]
    n = len(tasks)
    has_grounded = any("grounded" in g["scores"] for g in grades)

    def label(g: dict[str, Any]) -> str:
        return g["details"].get("correctness") or g["details"].get("label") or ""

    score = [g["scores"].get("score", 0.0) for g in grades]
    grounded = [g["scores"].get("grounded", 0.0) for g in grades]
    # Terminal failures (error.json after every pass, no grade) count as zero on the full denominator.
    failed_zeros = [0.0] * len(errors)
    searcher = searcher_name(config)
    search_usd = sum(result_search_usd(searcher, r) for r in results)
    model_usd = sum(r.get("model_cost_usd", 0.0) for r in results)
    judge_usd = sum(c.get("judge_cost_usd", 0.0) for c in costs)
    latency = [r.get("latency_ms", 0.0) / 1000 for r in results]
    cit_tokens = [g["scores"]["avg_citation_tokens"] for g in grades if "avg_citation_tokens" in g["scores"]]
    if not cit_tokens:  # FRAMES grades carry no citation metrics: count them the grader's way
        encoding = tiktoken.get_encoding("o200k_base")
        cit_tokens = [mean_citation_tokens(encoding, r) for r in results]
    per_task = (search_usd + model_usd + judge_usd) / n if n else 0.0
    return {
        "suite": config["suite"],
        "suite_revision": config["suite_revision"],
        "system": system,
        "run_dir": str(run_dir.relative_to(HERE)),
        "suite_tasks": suite_tasks,
        "tasks": n,
        "graded": len(grades),
        "failed": n - len(grades),
        "errors_open": errors,
        "tasks_retried_by_runner": sum(1 for r in results if r.get("attempt", 1) > 1),
        "correct": sum(1 for g in grades if label(g) == "CORRECT"),
        "incorrect": sum(1 for g in grades if label(g) == "INCORRECT"),
        "not_attempted": sum(1 for g in grades if label(g) == "NOT_ATTEMPTED"),
        "score": ci(score) if grades else None,
        "score_failed_as_zero": sum(score) / n if n else 0.0,
        "score_failed_as_zero_ci": ci(score + failed_zeros) if grades else None,
        "grounded": ci(grounded) if has_grounded else None,
        "grounded_failed_as_zero_ci": ci(grounded + failed_zeros) if has_grounded else None,
        "grounded_count": int(sum(grounded)) if has_grounded else None,
        "partial": sum(1 for g in grades if g["details"].get("groundedness") == "PARTIAL"),
        "avg_citation_tokens": mean(cit_tokens),
        "citations_per_task": mean([citation_count(r) for r in results]),
        "search_usd": search_usd,
        "model_usd": model_usd,
        "judge_usd": judge_usd,
        "total_usd": search_usd + model_usd + judge_usd,
        "search_usd_per_task": search_usd / n if n else 0.0,
        "model_usd_per_task": model_usd / n if n else 0.0,
        "judge_usd_per_task": judge_usd / n if n else 0.0,
        "total_usd_per_task": per_task,
        "system_cost_known": all(r.get("cost_known", False) for r in results) and len(results) == n,
        "latency_s_mean": mean(latency),
        "latency_s_p90": p90(latency),
        "transport": transport(log_dir, system),
    }


def suite_rows(suite: str) -> list[dict[str, Any]]:
    found = run_dirs([HERE / d for d in suite_dirs(suite)], suite)
    rows = [system_row(run_dir, SUITE_TASKS[suite], root / "logs") for run_dir, root in found.values()]
    return by_system_order(rows)


def errors_text(r: dict[str, Any]) -> str:
    text = f"{r['failed']} failed"
    if r["errors_open"]:
        text += f" (counted as zero; graded only: grounded {pct(r['grounded'], '%')}, correct {pct(r['score'], '%')})"
    if r["tasks_retried_by_runner"]:
        text += f", {r['tasks_retried_by_runner']} recovered on retry"
    if r["transport"].get("retries"):
        text += f", {r['transport']['retries']} LLM retries"
    return text


def table(rows: list[dict[str, Any]]) -> str:
    head = (
        "| System | Grounded % [95% CI] | Correct % [95% CI] | C / I / NA | Cit. tokens | "
        "Search $/task | Model $/task | Judge $/task | Total $ | Latency s mean / p90 | Errors |\n"
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"
    )
    lines = [head]
    for r in rows:
        incomplete = "" if r["tasks"] == r["suite_tasks"] else f" ({r['tasks']}/{r['suite_tasks']} tasks)"
        lines.append(
            f"| {r['system']}{incomplete} | {pct(r['grounded_failed_as_zero_ci'], '%')} | {pct(r['score_failed_as_zero_ci'], '%')} | "
            f"{r['correct']} / {r['incorrect']} / {r['not_attempted']} | {r['avg_citation_tokens']:.0f} | "
            f"${r['search_usd_per_task']:.4f} | ${r['model_usd_per_task']:.4f} | ${r['judge_usd_per_task']:.4f} | "
            f"${r['total_usd']:.2f} | {r['latency_s_mean']:.1f} / {r['latency_s_p90']:.1f} | {errors_text(r)} |"
        )
    return "\n".join(lines)


def spend(all_rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Spend over every run directory on disk (smokes and pilots included), in total and by system."""
    by_pair = {(r["system"], s): r for s, rows in all_rows.items() for r in rows}
    by_system: dict[str, float] = {}
    for (system, _), r in by_pair.items():
        by_system[system] = by_system.get(system, 0.0) + r["total_usd"]
    return {"spent_usd": sum(r["total_usd"] for r in by_pair.values()), "spent_by_system": by_system}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spend", action="store_true", help="print spend only")
    args = parser.parse_args()

    all_rows = {suite: suite_rows(suite) for suite in SUITE_TASKS}
    spent = spend(all_rows)
    print(f"All runs (every suite and system, smokes included): spent ${spent['spent_usd']:.2f}.")
    if args.spend:
        for system, usd in sorted(spent["spent_by_system"].items(), key=lambda kv: -kv[1]):
            print(f"- {system}: ${usd:.2f}")
        return 0

    for suite, rows in all_rows.items():
        if not rows:
            continue
        print(f"\n### {suite} ({SUITE_TASKS[suite]} tasks; {rows[0]['suite_revision']})\n")
        print(table(rows))
    print("\n### Spend by system ($, all suites)\n")
    for system, usd in sorted(spent["spent_by_system"].items(), key=lambda kv: -kv[1]):
        print(f"- {system}: ${usd:.2f}")
    (HERE / "report.json").write_text(json.dumps({"suites": all_rows, "spend": spent}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
