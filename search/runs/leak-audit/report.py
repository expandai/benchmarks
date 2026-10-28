"""Build the leak-audit tables from audit.json and regrades.json; writes tables.md.

Recomputed groundedness = recorded grounded sum, minus the tasks whose re-grade went from
grounded to UNGROUNDED, plus any that went the other way, over the run's graded-task count
(the same denominator RESULTS.md uses; DeepSeek's two failed tasks stay excluded).

Usage: .venv/bin/python -I runs/leak-audit/report.py
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path("runs/leak-audit")
ORDER = [
    "rag-perplexity-fast",
    "rag-exa-fast-highlights",
    "rag-parallel-fast",
    "rag-parallel-turbo",
    "rag-exa-webcode",
    "rag-exa-instant-highlights",
    "rag-deepseek",
    "rag-firecrawl-search",
]


def main() -> None:
    audit = json.loads((OUT / "audit.json").read_text())
    regrades = json.loads((OUT / "regrades.json").read_text())
    repeats_file = OUT / "regrade_repeats.json"
    repeats = json.loads(repeats_file.read_text()) if repeats_file.exists() else {}
    per_system = audit["per_system"]

    lines = []
    lines.append("### Table 1: leaked citations per system\n")
    lines.append("| System | Citations | Leaked | Leaked % | Tasks with >=1 leak | Tasks where judge used a leaked citation |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    tot = {"citations": 0, "leaked": 0, "tasks": 0, "judge": 0}
    for system in ORDER:
        s = per_system[system]
        lines.append(
            f"| {system} | {s['citations']} | {s['leaked_citations']} | "
            f"{100 * s['leaked_citations'] / s['citations']:.2f} | {s['tasks_with_leak']} | "
            f"{s['tasks_leak_in_judge_sources']} |"
        )
        tot["citations"] += s["citations"]
        tot["leaked"] += s["leaked_citations"]
        tot["tasks"] += s["tasks_with_leak"]
        tot["judge"] += s["tasks_leak_in_judge_sources"]
    lines.append(
        f"| **all {len(ORDER)} runs** | {tot['citations']} | {tot['leaked']} | "
        f"{100 * tot['leaked'] / tot['citations']:.2f} | {tot['tasks']} | {tot['judge']} |"
    )

    lines.append("\n### Table 2: groundedness, recorded vs. recomputed with leaked citations removed\n")
    lines.append("| System | Graded tasks | Grounded (recorded) | Re-graded tasks | Flips (grounded -> ungrounded / ungrounded -> grounded) | Grounded (filtered) | Delta (pp) |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    total_cost = 0.0
    total_calls = 0
    flips_all = []
    summary = {}
    for system in ORDER:
        s = per_system[system]
        pairs = [r for k, r in regrades.items() if r["system"] == system]
        down = [r for r in pairs if r["recorded_grounded"] == 1.0 and r["grounded"] == 0.0]
        up = [r for r in pairs if r["recorded_grounded"] == 0.0 and r["grounded"] == 1.0]
        flips_all += [(system, r["task_id"], r["recorded_groundedness"], r["groundedness"]) for r in down + up]
        graded = s["graded"]
        recorded = s["grounded_recorded_sum"] / graded
        filtered = (s["grounded_recorded_sum"] - len(down) + len(up)) / graded
        total_cost += sum(r["judge_cost_usd"] for r in pairs)
        total_calls += sum(r["judge_calls"] for r in pairs)
        summary[system] = {
            "graded": graded,
            "grounded_recorded": recorded,
            "grounded_filtered": filtered,
            "regraded": len(pairs),
            "flips_down": [r["task_id"] for r in down],
            "flips_up": [r["task_id"] for r in up],
        }
        lines.append(
            f"| {system} | {graded} | {100 * recorded:.1f} | {len(pairs)} | {len(down)} / {len(up)} | "
            f"{100 * filtered:.1f} | {100 * (filtered - recorded):+.1f} |"
        )
    lines.append(
        f"\nRe-grades: {len(regrades)} tasks, {total_calls} judge calls (openai/gpt-6-luna via OpenRouter), "
        f"${total_cost:.4f} reported cost."
    )
    if flips_all:
        lines.append("\nFlips:")
        for system, task, before, after in flips_all:
            extra = ""
            key = f"{system}/{task}"
            if key in repeats:
                verdicts = ", ".join(r["groundedness"] for r in repeats[key])
                extra = f" (repeat judge calls on the same filtered citations: {verdicts})"
            lines.append(f"- {system} {task}: {before} -> {after}{extra}")

    lines.append("\n### Table 3: leaking domains\n")
    lines.append("| Domain | Leaked citations | Reasons |")
    lines.append("|---|---:|---|")
    for domain, d in audit["domains"].items():
        reasons = ", ".join(f"{k} {v}" for k, v in d["reasons"].items())
        lines.append(f"| {domain} | {d['count']} | {reasons} |")
    lines.append(f"\nReasons overall: {audit['reasons']}")

    text = "\n".join(lines) + "\n"
    (OUT / "tables.md").write_text(text)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(text)


if __name__ == "__main__":
    main()
