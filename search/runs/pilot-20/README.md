# WebCode RAG pilot, 20 tasks, 2026-10-26

Status: **ran end to end for all six systems** (search + answer + judge), 20/20 tasks graded
each, no failed tasks, no runner retries, no transport retries. Answer model `openai/gpt-5.6-luna`
and judge `openai/gpt-6-luna` were served by OpenAI **through OpenRouter**
(`bakeoff/openrouter.py`, `BAKEOFF_LLM_TRANSPORT=openrouter`); all OpenAI models were called
through OpenRouter. The harness model names are unchanged; these `config.json` files use
upstream's format, which does not record the transport (new runs do, `bakeoff/provenance.py`).

## Tasks

`webcode-rag`, first 20 in file order (`upstream/data/webcode/rag.jsonl`; `--limit 20` takes
`tasks[:20]`): `rag_001` … `rag_020`. Every system saw the same set, searched in the same
2-minute window (six processes in parallel, concurrency 5 each). The run directories resume, so
the full 307-task run skips these 20.

## Results (measured)

Primary metric `grounded` (GroundedRAGGrader: groundedness ≠ UNGROUNDED). "Correct" is the
harness's `score` (correctness == CORRECT). CI is the harness's bootstrap 95% over tasks. Costs
are what the harness recorded: Exa's reported `costDollars`, Perplexity/Parallel list prices,
Firecrawl credits × $0.00099, and OpenRouter's `usage.cost` for every answer and judge call.
Latency is the harness `latency_ms` (search + answer, not judge). Wall is the process wall time
÷ 20 at concurrency 5, judge included.

| System | Grounded | Correct | Grounded (CI) | Cit. tokens | Search $/task | Answer $/task | Judge $/task | Total $/task | Latency s (mean / p90) | Wall s/task | Errors / retries |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| rag-perplexity-fast | **18/20** | **15/20** (2 not attempted) | 90% [75–100] | 373 | $0.0010 | $0.0012 | $0.0008 | **$0.0031** | **2.9 / 4.4** | 1.9 | 0 / 0 |
| rag-parallel-turbo | 17/20 | **15/20** (3 not attempted) | 85% [70–100] | 531 | $0.0010 | $0.0018 | $0.0011 | $0.0039 | 3.6 / 5.5 | 2.1 | 0 / 0 |
| rag-exa-fast-highlights | 16/20 | 13/20 (3 not attempted) | 80% [60–95] | 381 | $0.0070 | $0.0014 | $0.0009 | $0.0093 | 3.6 / 5.3 | 1.9 | 0 / 0 |
| rag-exa-webcode | 16/20 | 13/20 (3 not attempted) | 80% [60–95] | 364 | $0.0070 | $0.0013 | $0.0009 | $0.0092 | 14.2 / 17.3 | 4.6 | 0 / 0 |
| rag-exa-instant-highlights | 14/20 | 11/20 (4 not attempted) | 70% [50–90] | 400 | $0.0040 | $0.0015 | $0.0010 | $0.0065 | 4.0 / 6.6 | 2.7 | 0 / 0 |
| rag-firecrawl-search | 10/20 | 10/20 (9 not attempted) | 50% [30–70] | 87 | $0.0020 | $0.0005 | $0.0005 | $0.0030 | 3.7 / 5.9 | 2.1 | 0 / 0 |

No PARTIAL groundedness verdicts in any system. With 20 tasks the CIs overlap heavily: nothing
here separates Perplexity, Parallel and Exa fast; only Firecrawl snippets (87 tokens per
citation) are clearly behind, mostly as NOT_ATTEMPTED answers.

Answer-model usage per task (o200k): input 4.4–6.4k tokens (Firecrawl 1.7k), output 100–170
tokens of which 50–110 are reasoning; model+judge together cost $0.001–0.003 per task.

Pilot spend: search $0.44 (Exa $0.36, Firecrawl $0.04 = 40 credits, Perplexity $0.02, Parallel
$0.02), answer $0.155, judge $0.105. The harness's `model_usd + judge_usd` per system equals
OpenRouter's reported total for that process to the cent (e.g. exa-fast $0.0285 + $0.0182 =
$0.0467 reported), and OpenRouter's per-call `usage.cost` matched upstream's pricing table
exactly in the smoke run ($0.0001487 both ways), so the cost columns are directly comparable
with a direct-OpenAI run.

Per-task artifacts: `<system>-webcode-rag-<hash>/tasks/rag_0NN/{result,grade,cost}.json`;
per-system summaries with CIs: `<system>.json`; this table: `pilot-report.json` from
`pilot_report.py`. Transport counters are the last line of each `logs/<system>.log`
(`openrouter: 60 calls, 0 retries, 0 failed, $… reported cost`).

## Full run

The same six run directories hold the full 307-task runs (the 20 pilot tasks resumed into them);
results are in [`../RESULTS.md`](../RESULTS.md).

## Transport: OpenRouter instead of direct OpenAI

`bakeoff/openrouter.py` replaces upstream's `OpenAIClient` (Responses API, direct key) for
`openai/*` models when `BAKEOFF_LLM_TRANSPORT=openrouter`. What is the same and what differs:

- Same model ids (`openai/gpt-5.6-luna`, `openai/gpt-6-luna` are OpenRouter ids), same prompts,
  same `max_output_tokens` (16,000 for the judge), same strict JSON schemas from the graders'
  pydantic models (`response_format: json_schema, strict: true`), same pricing table as the
  fallback. Upstream's run-directory hash inputs are untouched (the overlay adds the transport
  to new runs' hashes, `bakeoff/provenance.py`).
- Endpoint is Chat Completions (`POST /chat/completions` with `messages`), not the Responses API;
  system prompts go as `system` messages. `provider: {require_parameters: true}` makes OpenRouter
  refuse any provider that would ignore `response_format`; every call in the pilot reports
  `"provider": "OpenAI"`.
- Reasoning effort: forwarded as `reasoning.effort` only when the harness sets one. Neither the
  RAG answer nor the judge does, so both ran at the model default (answers used 50–110 reasoning
  tokens, the judge ~30 in the smoke). A direct Responses-API run also sends no effort, so the
  default applies there too, but OpenAI does not promise the two APIs share a default.
- Cost: `usage.cost` from OpenRouter (`usage: {include: true}`) is recorded as `cost_usd`;
  `Generation.raw.transport` keeps both the reported and the table-priced figure. OpenRouter's
  5.5% credit-purchase fee is not in `usage.cost`.
- Retries: 408/409/425/429/5xx, provider errors wrapped in a 200, and transport errors are
  retried 3 times with exponential backoff (honouring `Retry-After`); 4xx otherwise fails at
  once; a 400 mentioning the context window raises upstream's `ContextWindowExceeded`. Counters
  are printed at the end of each `bench` run.
- Not supported: `hosted_web_search` (OpenAI's Responses `web_search` tool, used only by
  `scout-openai-*` systems) raises; Scout systems with plain function tools do work.

20 offline tests cover the request shape, schema passthrough, usage/cost mapping, retry policy,
install/uninstall and a `Judge.complete_json` round trip (`tests/test_openrouter.py`).

## Commands

```sh
cd benchmarks/search   # the bakeoff root
export EXA_BENCH_VENV="$PWD/.venv"      # the `bench` wrapper's default; created by `uv sync` (README)

# Offline tests: adapters, registration, OpenRouter transport.
"$EXA_BENCH_VENV/bin/python" -m pytest -q -p no:cacheprovider

# Live smoke of the transport alone: one strict-schema judge call + one answer call (~$0.0003).
set -a; . .env; set +a; unset OPENAI_API_KEY      # OPENROUTER_API_KEY
PYTHONPATH="$PWD:$PWD/upstream" "$EXA_BENCH_VENV/bin/python" runs/pilot-20/openrouter_smoke.py

# The pilot: sources .env, sets BAKEOFF_LLM_TRANSPORT=openrouter, unsets OPENAI_API_KEY,
# one `bench run` process per system in parallel, logs in logs/, wall time in logs/wall.txt.
# This is what produced the table (LIMIT=20, CONCURRENCY=5). Resumable: rerun the same command.
runs/pilot-20/run-pilot.sh
# Equivalent single command per system:
#   BAKEOFF_LLM_TRANSPORT=openrouter ./bench run --suite webcode-rag --system rag-perplexity-fast \
#     --limit 20 --concurrency 5 --runs-dir runs/pilot-20 -o runs/pilot-20/rag-perplexity-fast.json

# The table above:
"$EXA_BENCH_VENV/bin/python" runs/pilot-20/pilot_report.py

# Full 307-task run, same directories (skips the 20 graded tasks):
LIMIT=307 runs/pilot-20/run-pilot.sh
```

## History

- First attempt (earlier on 2026-10-26): an initial smoke failed on credentials; logs in
  `logs/smoke-401/`. A search-only latency probe from then is not in this repository; for measured
  per-search latencies see the AA agent's `s/search` column (`aa-stirrup/runs/full-600/summary.md`).
- The six stale `tasks/rag_001` directories from that smoke (error.json + a `cost.json` with
  `system_cost_known: false`, no result, no grade) were deleted before the pilot so the resumed
  runs report `system_cost_known: true`. Their only spend was one search per system (~$0.02).

## System choices

- Parallel: `rag-parallel-turbo` is the fastest tier in `systems.toml` (`mode = "turbo"`, $0.001);
  `rag-parallel-fast` ($0.001), `-basic` and `-advanced` ($0.005) also exist. Its citations are
  the longest (531 tokens), which is why its answer and judge cost are the highest.
- Perplexity: upstream's `perplexity` searcher calls the **Search API** (`POST /search`,
  `search_type: fast`), not a Sonar chat model. `rag-perplexity-web` is the same endpoint
  without `search_type` ($0.005).
- Exa: the three README systems. `rag-exa-webcode` is Exa's own WebCode preset (`type: fast`,
  query highlights, `maxAgeHours: 0`); it scored the same as fast highlights here at 4× the
  latency.
