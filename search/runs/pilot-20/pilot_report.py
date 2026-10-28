"""Per-system pilot table from the run directories in this folder.

Reads each ``<system>-webcode-rag-<hash>/`` (``summary.json`` plus ``tasks/*/{result,grade,
cost,error}.json``), the per-system log for OpenRouter transport counters, and ``logs/wall.txt``
for wall time. Prints a Markdown table and writes ``pilot-report.json`` next to it.

    "$EXA_BENCH_VENV/bin/python" runs/pilot-20/pilot_report.py [--full-tasks 307]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _records import STATS_LINE, citation_count, mean, p90, read  # noqa: E402

WALL_LINE = re.compile(r"^(\S+) (\S+) limit=(\d+) exit=(\d+) wall_s=(\d+)$")


def wall_times() -> dict[str, tuple[int, int]]:
    """Latest ``(limit, wall_s)`` per system from logs/wall.txt."""
    out: dict[str, tuple[int, int]] = {}
    path = HERE / "logs" / "wall.txt"
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        match = WALL_LINE.match(line.strip())
        if match:
            out[match.group(2)] = (int(match.group(3)), int(match.group(5)))
    return out


def transport_stats(system: str) -> dict[str, Any]:
    path = HERE / "logs" / f"{system}.log"
    if not path.exists():
        return {}
    text = path.read_text()
    retry_warnings = len(re.findall(r"openrouter .* attempt \d+/\d+ failed", text))
    match = STATS_LINE.search(text)
    if not match:
        return {"retry_warnings": retry_warnings}
    return {
        "calls": int(match.group(1)),
        "retries": int(match.group(2)),
        "retried": match.group(3) or "",
        "failed_calls": int(match.group(4)),
        "reported_cost_usd": float(match.group(5)),
        "retry_warnings": retry_warnings,
    }


def system_row(run_dir: Path, full_tasks: int, walls: dict[str, tuple[int, int]]) -> dict[str, Any]:
    summary = read(run_dir / "summary.json")
    system = summary["system"]
    tasks = sorted(p for p in (run_dir / "tasks").iterdir() if p.is_dir())
    results = [read(p / "result.json") for p in tasks if (p / "result.json").exists()]
    grades = [read(p / "grade.json") for p in tasks if (p / "grade.json").exists()]
    costs = [read(p / "cost.json") for p in tasks if (p / "cost.json").exists()]
    errors = [read(p / "error.json") for p in tasks if (p / "error.json").exists()]
    retried_tasks = sum(1 for r in results if r.get("attempt", 1) > 1)
    n = len(tasks)
    graded = len(grades)
    grounded = sum(g["scores"].get("grounded", 0.0) for g in grades)
    correct = sum(g["scores"].get("score", 0.0) for g in grades)
    partial = sum(1 for g in grades if g["details"].get("groundedness") == "PARTIAL")
    not_attempted = sum(1 for g in grades if g["details"].get("correctness") == "NOT_ATTEMPTED")
    search_usd = sum(r.get("search_cost_usd", 0.0) for r in results)
    model_usd = sum(r.get("model_cost_usd", 0.0) for r in results)
    judge_usd = sum(c.get("judge_cost_usd", 0.0) for c in costs)
    per_task_total = (search_usd + model_usd + judge_usd) / n if n else 0.0
    limit, wall_s = walls.get(system, (n, 0))
    wall_per_task = wall_s / limit if limit else 0.0
    usage = [r.get("usage", {}) for r in results]
    return {
        "system": system,
        "tasks": n,
        "graded": graded,
        "failed": n - graded,
        "grounded": int(grounded),
        "partial": partial,
        "correct": int(correct),
        "not_attempted": not_attempted,
        "grounded_rate": summary["metrics"].get("grounded"),
        "grounded_failed_as_zero": summary.get("grounded_failed_as_zero"),
        "grounded_ci": summary["confidence_intervals"]["metrics"].get("grounded"),
        "score_rate": summary["metrics"].get("score"),
        "citation_precision": summary["metrics"].get("citation_precision"),
        "avg_citation_tokens": mean([g["scores"].get("avg_citation_tokens", 0.0) for g in grades]),
        "citations_per_task": mean([citation_count(r) for r in results]),
        "answer_input_tokens": mean([u.get("input_tokens", 0) for u in usage]),
        "answer_output_tokens": mean([u.get("output_tokens", 0) for u in usage]),
        "answer_reasoning_tokens": mean([u.get("reasoning_tokens", 0) for u in usage]),
        "search_usd_per_task": search_usd / n if n else 0.0,
        "model_usd_per_task": model_usd / n if n else 0.0,
        "judge_usd_per_task": judge_usd / n if n else 0.0,
        "total_usd_per_task": per_task_total,
        "system_cost_known": summary["cost"]["system_cost_known"],
        "judge_cost_known": summary["cost"]["judge_cost_known"],
        "latency_s_mean": mean([r.get("latency_ms", 0.0) for r in results]) / 1000,
        "latency_s_p90": p90([r.get("latency_ms", 0.0) for r in results]) / 1000,
        "wall_s": wall_s,
        "wall_s_per_task": wall_per_task,
        "errors_recorded": len(errors),
        "tasks_retried_by_runner": retried_tasks,
        "transport": transport_stats(system),
        "full_run_usd": per_task_total * full_tasks,
        "full_run_search_usd": (search_usd / n if n else 0.0) * full_tasks,
        "full_run_wall_min": wall_per_task * full_tasks / 60,
    }


def markdown(rows: list[dict[str, Any]], full_tasks: int) -> str:
    head = (
        "| System | Grounded | Correct | Grounded (CI) | Cit. tokens | Search $/task | "
        "Answer $/task | Judge $/task | Total $/task | Latency s (mean / p90) | Wall s/task | "
        "Errors / retries |\n|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---|"
    )
    lines = [head]
    for r in rows:
        ci = r["grounded_ci"] or {}
        t = r["transport"]
        retries = (
            f"{t.get('retries', '?')} ({t['retried']})" if t.get("retried") else str(t.get("retries", "?"))
        )
        lines.append(
            f"| {r['system']} | {r['grounded']}/{r['tasks']}"
            f"{f' (+{r['partial']} partial)' if r['partial'] else ''} | {r['correct']}/{r['tasks']}"
            f"{f' ({r['not_attempted']} not attempted)' if r['not_attempted'] else ''} | "
            f"{(r['grounded_rate'] or 0) * 100:.0f}% [{(ci.get('low') or 0) * 100:.0f}–{(ci.get('high') or 0) * 100:.0f}] | "
            f"{r['avg_citation_tokens']:.0f} | ${r['search_usd_per_task']:.4f} | ${r['model_usd_per_task']:.4f} | "
            f"${r['judge_usd_per_task']:.4f} | ${r['total_usd_per_task']:.4f} | "
            f"{r['latency_s_mean']:.1f} / {r['latency_s_p90']:.1f} | {r['wall_s_per_task']:.1f} | "
            f"{r['failed']} failed, {r['errors_recorded']} error.json, {retries} transport retries |"
        )
    lines.append("")
    lines.append(f"Extrapolation to {full_tasks} tasks (per-task × {full_tasks}; wall at the pilot's concurrency):")
    lines.append("")
    lines.append("| System | Total $ | Search $ | Answer+judge $ | Wall min |\n|---|---:|---:|---:|---:|")
    for r in rows:
        lines.append(
            f"| {r['system']} | ${r['full_run_usd']:.2f} | ${r['full_run_search_usd']:.2f} | "
            f"${(r['model_usd_per_task'] + r['judge_usd_per_task']) * full_tasks:.2f} | {r['full_run_wall_min']:.0f} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-tasks", type=int, default=307)
    args = parser.parse_args()
    walls = wall_times()
    rows = [
        system_row(d, args.full_tasks, walls)
        for d in sorted(HERE.iterdir())
        if d.is_dir() and (d / "config.json").exists() and (d / "summary.json").exists()
    ]
    (HERE / "pilot-report.json").write_text(json.dumps(rows, indent=2))
    print(markdown(rows, args.full_tasks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
