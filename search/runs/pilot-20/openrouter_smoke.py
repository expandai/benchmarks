"""Live smoke of the OpenRouter transport: one judge-shaped call (strict JSON schema,
``openai/gpt-6-luna``) and one answer-shaped call (``openai/gpt-5.6-luna``).

Prints usage, OpenRouter's reported cost next to the harness pricing table, the provider
that served the call and whether the reply validated. Never prints a key. Run from the
bakeoff root (``search/``), with ``OPENROUTER_API_KEY`` in ``.env``:

    set -a; . ./.env; set +a
    PYTHONPATH="$PWD:$PWD/upstream" .venv/bin/python runs/pilot-20/openrouter_smoke.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from benchmarks.graders.rag import GROUNDEDNESS_SYSTEM_PROMPT, GroundednessResult
from harness.llm.judge import strict_schema
from harness.rag import RAG_SYSTEM_PROMPT, RAG_USER_PROMPT

from bakeoff.openrouter import OpenRouterClient

CITATIONS = [
    {
        "url": "https://docs.python.org/3/library/json.html",
        "title": "json — JSON encoder and decoder",
        "text": "json.dumps(obj, *, skipkeys=False, ensure_ascii=True, ...) Serialize obj to a "
        "JSON formatted str. If ensure_ascii is true (the default), the output is guaranteed "
        "to have all incoming non-ASCII characters escaped.",
        "published_date": None,
    }
]
QUESTION = "What is the default value of ensure_ascii in Python's json.dumps?"
GOLD = "True"


def report(label: str, generation, served_model: str | None) -> None:
    transport = generation.raw["transport"]
    body = generation.raw["response"]
    print(
        json.dumps(
            {
                "call": label,
                "openrouter_model": transport["model"],
                "served_model": served_model,
                "provider": body.get("provider"),
                "attempts": transport["attempts"],
                "finish_reason": (body.get("choices") or [{}])[0].get("finish_reason"),
                "usage": generation.usage.to_dict(),
                "reported_cost_usd": transport["reported_cost_usd"],
                "table_cost_usd": transport["table_cost_usd"],
                "reasoning_text_returned": bool(generation.reasoning),
                "text_chars": len(generation.text),
            },
            indent=2,
        )
    )


async def main() -> int:
    judge = OpenRouterClient("openai/gpt-6-luna")
    parts = [f"[{i}] URL: {c['url']}\nTitle: {c['title']}\n{c['text']}" for i, c in enumerate(CITATIONS, 1)]
    prompt = (
        f"Question: {QUESTION}\n\nRetrieved citations:\n{'---'.join(parts)}\n\n"
        f"Gold target answer: {GOLD}"
    )
    schema = {
        "name": "GroundednessResult",
        "schema": strict_schema(GroundednessResult.model_json_schema()),
    }
    generation = await judge.generate(
        [
            {"role": "system", "content": GROUNDEDNESS_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_output_tokens=16_000,
        response_schema=schema,
    )
    report("judge/groundedness", generation, generation.raw["response"].get("model"))
    parsed = GroundednessResult.model_validate_json(generation.text)
    print(json.dumps({"parsed": parsed.model_dump()}, indent=2))

    answerer = OpenRouterClient("openai/gpt-5.6-luna")
    generation = await answerer.generate(
        [
            {"role": "system", "content": RAG_SYSTEM_PROMPT.replace("{current_date}", "October 26, 2026")},
            {
                "role": "user",
                "content": RAG_USER_PROMPT.format(
                    question=QUESTION,
                    search_results="\n".join(json.dumps(c) for c in CITATIONS),
                ),
            },
        ]
    )
    report("answer/rag", generation, generation.raw["response"].get("model"))
    print(json.dumps({"answer": generation.text[:300]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
