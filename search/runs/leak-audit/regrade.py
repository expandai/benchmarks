"""Re-run the WebCode groundedness judge on the tasks that had a leaked citation.

Same call the runs made: ``GroundedRAGGrader._call_groundedness`` (prompt, citation numbering,
schema unchanged) with ``Judge("openai/gpt-6-luna")`` through the OpenRouter transport
(``bakeoff.openrouter.install``; default reasoning effort, 16k max output tokens). Only the
groundedness call is repeated: correctness does not depend on the citations. A task whose
citations are all leaked is UNGROUNDED without a judge call.

Reads  runs/leak-audit/regrade_plan.json (from audit.py)
Writes runs/leak-audit/regrades.json (resumable: pairs already present are skipped)

Usage (from the bakeoff root, keys sourced, never printed):
  set -a; . .env; set +a            # OPENROUTER_API_KEY
  .venv/bin/python -I runs/leak-audit/regrade.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path[:0] = ["upstream", "."]
from bakeoff import openrouter  # noqa: E402
from benchmarks.graders.rag import Citation, GroundedRAGGrader  # noqa: E402
from harness.llm.judge import Judge, track_judge_usage  # noqa: E402

OUT = Path("runs/leak-audit")
PLAN = OUT / "regrade_plan.json"
RESULTS = OUT / "regrades.json"
JUDGE_MODEL = "openai/gpt-6-luna"
CONCURRENCY = 4


def key_of(pair: dict[str, Any]) -> str:
    return f"{pair['system']}/{pair['task_id']}"


async def regrade(grader: GroundedRAGGrader, pair: dict[str, Any]) -> dict[str, Any]:
    citations = [Citation(**c) for c in pair["remaining_citations"]]
    base = {
        "system": pair["system"],
        "task_id": pair["task_id"],
        "leaked_indices": pair["leaked_indices"],
        "remaining_citations": len(citations),
        "recorded_groundedness": pair["recorded_groundedness"],
        "recorded_grounded": pair["recorded_grounded"],
    }
    if not citations:
        return {**base, "groundedness": "UNGROUNDED", "grounded": 0.0, "judge_calls": 0,
                "judge_cost_usd": 0.0, "cost_known": True, "note": "no citations left"}
    with track_judge_usage() as usage:
        parsed = await grader._call_groundedness(pair["query"], pair["expected_answer"], citations)
    return {
        **base,
        "groundedness": parsed.groundedness,
        "grounded": 0.0 if parsed.groundedness == "UNGROUNDED" else 1.0,
        "source_indices": parsed.source_indices,
        "answer_source_urls": GroundedRAGGrader._extract_source_urls(parsed.source_indices, citations),
        "evidence": parsed.evidence,
        "reasoning": parsed.reasoning,
        "judge_calls": usage.calls,
        "judge_cost_usd": usage.total_usd,
        "cost_known": usage.known,
    }


async def main() -> None:
    openrouter.install()
    openrouter.api_key()  # fail early if the key is missing; never printed
    plan = json.loads(PLAN.read_text())
    done: dict[str, Any] = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    todo = [p for p in plan if key_of(p) not in done]
    print(f"plan: {len(plan)} pairs, already graded: {len(done)}, to grade: {len(todo)}")
    grader = GroundedRAGGrader(Judge(JUDGE_MODEL))
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def one(pair: dict[str, Any]) -> None:
        async with semaphore:
            try:
                done[key_of(pair)] = await regrade(grader, pair)
            except Exception as error:  # keep going; the pair stays absent and can be re-run
                print(f"FAILED {key_of(pair)}: {type(error).__name__}: {str(error)[:200]}")
                return
            RESULTS.write_text(json.dumps(done, indent=2, ensure_ascii=False))
            r = done[key_of(pair)]
            print(f"{key_of(pair):48s} {r['recorded_groundedness']:>10s} -> {r['groundedness']:<10s} "
                  f"${r['judge_cost_usd']:.5f}")

    await asyncio.gather(*(one(p) for p in todo))
    RESULTS.write_text(json.dumps(done, indent=2, ensure_ascii=False))
    total = sum(r["judge_cost_usd"] for r in done.values())
    print(f"\n{len(done)}/{len(plan)} graded; judge cost ${total:.4f}; {openrouter.STATS.summary()}")


if __name__ == "__main__":
    asyncio.run(main())
