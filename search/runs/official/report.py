"""Tables for the official-grader runs under runs/official/<suite>/ and their spend.

Per system and suite: the official headline metric with a 95% task-bootstrap CI (percentile,
10,000 resamples, seed 0 — upstream ``bootstrap_mean`` for per-task means; the same resampling
applied to the F1 *statistic* for SimpleQA Verified), the secondary official metrics, label
counts, citation tokens, search $/1k, model/judge/total $ per task, latency (search + answer,
judge excluded), failures, DeepSeek-clipped queries, leak-filtered results, transport retries,
and the judge model string the provider reported.

    "$EXA_BENCH_VENV/bin/python" runs/official/report.py            # tables, runs/official/report.json
    "$EXA_BENCH_VENV/bin/python" runs/official/report.py --spend    # spend only
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _records import by_system_order, ci, filtered_by_reason, mean, p90, pct, read, read_all, result_search_usd, run_dirs, searcher_name, task_dirs, transport  # noqa: E402
from bakeoff.official_graders import simpleqa_verified_metrics  # noqa: E402
from harness.statistics import BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED  # noqa: E402

SUITE_TASKS = {
    "simpleqa-verified-official": 1000,
    "seal-0-official": 111,
    "seal-hard-official": 254,
    "frames-official": 824,
}


def f1_ci(labels: list[str]) -> dict[str, float | None] | None:
    """Percentile bootstrap of the F1 statistic over tasks (same resamples/seed as upstream)."""
    if not labels:
        return None
    codes = np.array([{"CORRECT": 0, "INCORRECT": 1, "NOT_ATTEMPTED": 2}[label] for label in labels])
    n = len(codes)
    point = simpleqa_verified_metrics(*(int((codes == k).sum()) for k in range(3)))["f1"]
    if n < 2:
        return {"mean": point, "low": None, "high": None}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    stats = np.empty(BOOTSTRAP_RESAMPLES)
    for start in range(0, BOOTSTRAP_RESAMPLES, 256):
        size = min(256, BOOTSTRAP_RESAMPLES - start)
        sample = codes[rng.integers(n, size=(size, n))]
        c = (sample == 0).sum(axis=1)
        i = (sample == 1).sum(axis=1)
        acc = c / n
        att = c + i
        acc_att = np.divide(c, att, out=np.zeros(size), where=att > 0)
        denom = acc + acc_att
        stats[start : start + size] = np.divide(2 * acc * acc_att, denom, out=np.zeros(size), where=denom > 0)
    low, high = np.quantile(stats, [0.025, 0.975])
    return {"mean": point, "low": float(low), "high": float(high)}


def filtered_reasons(results: list[dict[str, Any]]) -> dict[str, int]:
    """Leak-filter drops by reason over a run, in first-seen order."""
    total: collections.Counter[str] = collections.Counter()
    for result in results:
        total.update(filtered_by_reason(result))
    return dict(total)


def system_row(run_dir: Path, suite: str, log_dir: Path) -> dict[str, Any]:
    config = read(run_dir / "config.json")
    system = config["system"]["name"]
    tasks = task_dirs(run_dir)
    results = read_all([p / "result.json" for p in tasks if (p / "result.json").exists()])
    grades = read_all([p / "grade.json" for p in tasks if (p / "grade.json").exists()])
    costs = read_all([p / "cost.json" for p in tasks if (p / "cost.json").exists()])
    errors = [p.name for p in tasks if (p / "error.json").exists() and not (p / "grade.json").exists()]
    n = len(tasks)
    labels = [g["details"].get("label", "") for g in grades]
    score = [g["scores"].get("score", 0.0) for g in grades]
    # Terminal failures (error.json after every pass, no grade) count as zero / NOT_ATTEMPTED on the full
    # denominator; tasks still ungraded because a run was stopped are not failures (partial rows).
    score_all = score + [0.0] * len(errors)
    labels_all = labels + ["NOT_ATTEMPTED"] * len(errors)
    searcher = searcher_name(config)
    search_usd = sum(result_search_usd(searcher, r) for r in results)
    model_usd = sum(r.get("model_cost_usd", 0.0) for r in results)
    judge_usd = sum(c.get("judge_cost_usd", 0.0) for c in costs)
    latency = [r.get("latency_ms", 0.0) / 1000 for r in results]
    counts = {label: labels.count(label) for label in ("CORRECT", "INCORRECT", "NOT_ATTEMPTED", "TRUE", "FALSE")}
    row: dict[str, Any] = {
        "suite": suite,
        "suite_revision": config["suite_revision"],
        "judge_model": config["judge_model"],
        "judge_model_reported": sorted({g["details"].get("judge_model_reported") or "" for g in grades} - {""}),
        "system": system,
        "run_dir": str(run_dir.relative_to(HERE)),
        "suite_tasks": SUITE_TASKS[suite],
        "tasks": n,
        "graded": len(grades),
        "failed": n - len(grades),
        "errors_open": errors,
        "tasks_retried_by_runner": sum(1 for r in results if r.get("attempt", 1) > 1),
        "judge_reparses": sum(1 for g in grades if g["details"].get("judge_attempts", 1) > 1),
        "labels": counts,
        "accuracy": ci(score_all),
        "accuracy_failed_as_zero": sum(score) / n if n else 0.0,
        "avg_citation_tokens": mean([g["scores"].get("avg_citation_tokens", 0.0) for g in grades]),
        "citations_per_task": mean([g["scores"].get("num_citations", 0.0) for g in grades]),
        "filtered_results_total": int(sum(g["scores"].get("filtered_results", 0.0) for g in grades)),
        "filtered_by_reason": filtered_reasons(results),
        "queries_clipped": sum(1 for r in results if r.get("query_clipped")),
        "answer_reasoning_effort": next((r.get("answer_protocol", {}).get("reasoning_effort") for r in results), None),
        "search_usd": search_usd,
        "model_usd": model_usd,
        "judge_usd": judge_usd,
        "total_usd": search_usd + model_usd + judge_usd,
        "search_usd_per_1k": search_usd / n * 1000 if n else 0.0,
        "model_usd_per_task": model_usd / n if n else 0.0,
        "judge_usd_per_task": judge_usd / n if n else 0.0,
        "total_usd_per_task": (search_usd + model_usd + judge_usd) / n if n else 0.0,
        "system_cost_known": all(r.get("cost_known", False) for r in results) and len(results) == n,
        "latency_s_mean": mean(latency),
        "latency_s_p90": p90(latency),
        "answer_output_tokens_mean": mean([r.get("usage", {}).get("output_tokens", 0) for r in results]),
        "transport": transport(log_dir, system),
    }
    if suite == "simpleqa-verified-official":
        c, i, na = counts["CORRECT"], counts["INCORRECT"], counts["NOT_ATTEMPTED"]
        attempted = c + i
        row["f1"] = f1_ci(labels_all)
        row["accuracy_given_attempted"] = c / attempted if attempted else 0.0
        row["attempted_share"] = attempted / len(labels) if labels else 0.0
        row["hedged_share"] = na / len(labels) if labels else 0.0
    return row


def suite_rows(suite: str) -> list[dict[str, Any]]:
    root = HERE / suite
    found = run_dirs([root], suite)
    return by_system_order([system_row(run_dir, suite, root / "logs") for run_dir, _root in found.values()])


def notes(r: dict[str, Any]) -> str:
    parts = []
    if r["failed"]:
        in_flight = r["failed"] - len(r["errors_open"])
        if r["errors_open"]:
            parts.append(f"{len(r['errors_open'])} failed")
        if in_flight:
            parts.append(f"{in_flight} in flight when stopped (ungraded)")
    if r["tasks_retried_by_runner"]:
        parts.append(f"{r['tasks_retried_by_runner']} recovered on retry")
    if r["transport"]["retries"]:
        parts.append(f"{r['transport']['retries']} LLM retries")
    if r["judge_reparses"]:
        parts.append(f"{r['judge_reparses']} judge re-asks")
    if r["queries_clipped"]:
        parts.append(f"{r['queries_clipped']} queries clipped")
    if r["filtered_results_total"]:
        by = ", ".join(f"{k} {v}" for k, v in sorted(r["filtered_by_reason"].items()))
        parts.append(f"{r['filtered_results_total']} results leak-filtered ({by})")
    return "; ".join(parts) or "—"


def name_with_coverage(r: dict[str, Any]) -> str:
    name = r["system"].removeprefix("rag-")
    if r["tasks"] != r["suite_tasks"]:
        name += f" ({r['tasks']}/{r['suite_tasks']} tasks)"
    return name


def table(suite: str, rows: list[dict[str, Any]]) -> str:
    common_head = (
        "Cit. tokens | Cit./task | Search $/1k | Model $/task | Judge $/task | Total $/task | "
        "Latency s mean / p90 | Notes |"
    )
    lines = []
    if suite == "simpleqa-verified-official":
        lines.append(
            "| System | **F1** [95% CI] | Accuracy [95% CI] | Acc. given attempted | Attempted % | "
            "C / I / NA | " + common_head
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    elif suite == "frames-official":
        lines.append("| System | **Accuracy** [95% CI] | TRUE / FALSE | " + common_head)
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    else:
        lines.append("| System | **Accuracy** (A) [95% CI] | B % | C % | A / B / C | " + common_head)
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for r in rows:
        L = r["labels"]
        common = (
            f"{r['avg_citation_tokens']:.0f} | {r['citations_per_task']:.1f} | ${r['search_usd_per_1k']:.2f} | "
            f"${r['model_usd_per_task']:.4f} | ${r['judge_usd_per_task']:.4f} | ${r['total_usd_per_task']:.4f} | "
            f"{r['latency_s_mean']:.1f} / {r['latency_s_p90']:.1f} | {notes(r)} |"
        )
        if suite == "simpleqa-verified-official":
            lines.append(
                f"| {name_with_coverage(r)} | **{pct(r['f1'])}** | {pct(r['accuracy'])} | "
                f"{r['accuracy_given_attempted'] * 100:.1f} | {r['attempted_share'] * 100:.1f} | "
                f"{L['CORRECT']} / {L['INCORRECT']} / {L['NOT_ATTEMPTED']} | {common}"
            )
        elif suite == "frames-official":
            lines.append(
                f"| {name_with_coverage(r)} | **{pct(r['accuracy'])}** | {L['TRUE']} / {L['FALSE']} | {common}"
            )
        else:
            g = r["graded"] or 1
            lines.append(
                f"| {name_with_coverage(r)} | **{pct(r['accuracy'])}** | {L['INCORRECT'] / g * 100:.1f} | "
                f"{L['NOT_ATTEMPTED'] / g * 100:.1f} | {L['CORRECT']} / {L['INCORRECT']} / {L['NOT_ATTEMPTED']} | {common}"
            )
    return "\n".join(lines)


def spend(all_rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Spend over every run directory under runs/official/ (pilots included): total, by system, by suite."""
    by_pair = {(r["system"], s): r for s, rows in all_rows.items() for r in rows}
    by_system: dict[str, float] = {}
    by_suite: dict[str, float] = {}
    for (system, suite), r in by_pair.items():
        by_system[system] = by_system.get(system, 0.0) + r["total_usd"]
        by_suite[suite] = by_suite.get(suite, 0.0) + r["total_usd"]
    return {
        "spent_usd": sum(r["total_usd"] for r in by_pair.values()),
        "spent_by_system": by_system,
        "spent_by_suite": by_suite,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spend", action="store_true")
    args = parser.parse_args()
    all_rows = {suite: suite_rows(suite) for suite in SUITE_TASKS}
    spent = spend(all_rows)
    print(f"Official runs: spent ${spent['spent_usd']:.2f}.")
    if args.spend:
        for suite, usd in spent["spent_by_suite"].items():
            print(f"- {suite}: ${usd:.2f}")
        return 0
    for suite, rows in all_rows.items():
        if not rows:
            continue
        print(f"\n### {suite} ({SUITE_TASKS[suite]} tasks; revision `{rows[0]['suite_revision']}`; judge `{rows[0]['judge_model']}`, reported as {sorted({m for r in rows for m in r['judge_model_reported']})})\n")
        print(table(suite, rows))
    print("\n### Spend by system ($, all official suites)\n")
    for system, usd in sorted(spent["spent_by_system"].items(), key=lambda kv: -kv[1]):
        print(f"- {system}: ${usd:.2f}")
    (HERE / "report.json").write_text(json.dumps({"suites": all_rows, "spend": spent}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
