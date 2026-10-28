# Search-API bakeoff results, 2026-10-26 to 2026-10-28

Harness: [exa-labs/benchmarks](https://github.com/exa-labs/benchmarks) @ `0d817af` (unedited, `../upstream/`) plus the `../bakeoff/` overlay. Every system uses the same RAG setup: one search with the question verbatim, `num_results = 10`, one answer from `openai/gpt-5.6-luna`, and the judge `openai/gpt-6-luna`. Both models are called through OpenRouter (`BAKEOFF_LLM_TRANSPORT=openrouter`). CIs are bootstrap 95% intervals over tasks (upstream `bootstrap_mean`, 10,000 resamples, seed 0) on graded tasks. Tables are produced by `runs/report.py`, which also writes `runs/report.json`.

**This file covers WebCode RAG**, whose own protocol is Exa's single-search RAG mode. That mode is not the official protocol of FRAMES, SimpleQA Verified, SealQA or AA-Omniscience; the single-search runs on those suites are kept as evidence under [Supplementary](#supplementary-single-search-mode-not-the-benchmarks-official-protocol), and the published results for those benchmarks are the official-grader runs in `official/RESULTS.md` and the AA-Stirrup runs in `../aa-stirrup/`.

## WebCode RAG (307 tasks)

Data: `upstream/data/webcode/rag.jsonl`, suite revision `sha256:9aa83266452b…+grader-v2`. Grader: `GroundedRAGGrader`. **Grounded** means the retrieved citations contain every non-trivial fact in the gold answer (not UNGROUNDED; PARTIAL counts as grounded). **Correct** means the answer is CORRECT. C / I / NA counts correct, incorrect and not-attempted answers. Cit. tokens is o200k tokens per citation. Latency is the harness `latency_ms` (search plus answer, judge excluded). Rows are ordered by grounded; the two percentage columns count a task that failed on every pass as zero over all 307 tasks.

| System | Grounded % [95% CI] | Correct % [95% CI] | C / I / NA | Cit. tokens | Search $/1k | Model + judge $/1k | Total $/1k | Latency s mean / p90 | Failed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| rag-expand | 95.8 [93.5–97.7] | 87.6 [84.0–91.2] | 269 / 29 / 9 | 523 | 1.50 | 2.80 | 4.30 | 3.9 / 6.2 | 0 |
| rag-perplexity-fast | 94.5 [91.9–96.7] | 87.9 [84.4–91.5] | 270 / 27 / 10 | 376 | 1.00 | 2.08 | 3.08 | 2.8 / 4.3 | 0 |
| rag-perplexity-web | 93.5 [90.6–96.1] | 86.0 [82.1–89.9] | 264 / 30 / 13 | 387 | 5.00 | 2.06 | 7.06 | 3.2 / 4.9 | 0 |
| rag-brave-llm-context | 92.2 [88.9–95.1] | 86.6 [82.7–90.2] | 266 / 26 / 15 | 279 | 5.00 | 1.84 | 6.84 | 4.4 / 6.4 | 0 |
| rag-exa-auto-highlights | 88.9 [85.3–92.2] | 81.8 [77.5–86.0] | 251 / 35 / 21 | 415 | 7.00 | 2.56 | 9.56 | 4.7 / 7.2 | 0 |
| rag-exa-fast-highlights | 88.6 [85.0–91.9] | 80.1 [75.6–84.4] | 246 / 45 / 16 | 422 | 7.00 | 2.58 | 9.58 | 3.6 / 5.3 | 0 |
| rag-exa-lite-highlights | 87.6 [83.7–91.2] | 77.9 [73.0–82.4] | 239 / 45 / 23 | 418 | 4.00 | 2.60 | 6.60 | 3.8 / 6.2 | 0 |
| rag-parallel-fast | 87.3 [83.4–90.9] | 84.0 [79.8–87.9] | 258 / 28 / 21 | 255 | 1.00 | 1.77 | 2.77 | 3.5 / 5.4 | 0 |
| rag-parallel-turbo | 87.0 [83.1–90.6] | 80.1 [75.6–84.4] | 246 / 30 / 31 | 498 | 1.00 | 2.72 | 3.72 | 3.3 / 5.1 | 0 |
| rag-exa-webcode | 86.6 [82.7–90.2] | 79.5 [74.9–83.7] | 244 / 40 / 23 | 413 | 7.00 | 2.45 | 9.45 | 11.8 / 19.0 | 0 |
| rag-exa-instant-highlights | 85.7 [81.8–89.6] | 76.5 [71.7–81.1] | 235 / 44 / 28 | 426 | 4.00 | 2.57 | 6.57 | 3.6 / 5.5 | 0 |
| rag-deepseek | 80.8 [76.2–85.0] | 75.2 [70.4–80.1] | 231 / 41 / 33 | 270 | 0.74 | 1.94 | 2.68 | 3.4 / 5.3 | 2 (DeepSeek 500) |
| rag-tavily-advanced | 78.5 [73.9–83.1] | 71.7 [66.4–76.5] | 220 / 41 / 46 | 395 | 16.00 | 2.30 | 18.30 | 6.6 / 8.9 | 0 |
| rag-firecrawl-search | 54.4 [48.9–59.9] | 51.8 [46.3–57.3] | 159 / 24 / 124 | 112 | 1.97 | 1.13 | 3.11 | 3.7 / 5.4 | 0 |

**Expand (2026-10-27).** `rag-expand` is Expand Search, `POST /v1/search` with `{query, maxResults: 10}` and nothing else. Expand is priced at its list price of $1.50 per 1,000 searches (2026-10-28). The report generators apply it to each billed search (`../bakeoff/pricing.py`). Run `webcode-rag/rag-expand-webcode-rag-09e2964740`, summary `webcode-rag/rag-expand.json`, 307/307 graded, 0 errors, 379 s wall at concurrency 8.

**Tavily and Brave (2026-10-27).** `rag-tavily-advanced` (Tavily `search_depth=advanced`, 2 credits × $0.008 per request as reported) and `rag-brave-llm-context` (Brave LLM Context, $5 per 1,000 list) ran at 23:44–23:56 UTC at concurrency 6 with the upstream adapters unchanged. Brave's adapter strips punctuation from every query and clips at 400 characters or 50 words; no WebCode query was shortened by it.

**Exa lite and auto (2026-10-28).** `rag-exa-lite-highlights` (Exa `type=lite`, highlights; an overlay catalog entry on the upstream adapter) and `rag-exa-auto-highlights` (upstream's preset) ran at 03:52–03:58 UTC at concurrency 10; Exa-reported cost $4.00 and $7.00 per 1,000 searches.

**Perplexity web (2026-10-28).** `rag-perplexity-web` is upstream's preset: Perplexity Search with `search_type` web and otherwise default settings, priced by the upstream adapter at $5.00 per 1,000 searches; 05:20–05:25 UTC at concurrency 10.

**Failed tasks.** DeepSeek failed `rag_006` and `rag_231`. DeepSeek returned HTTP 500 `internal_error` on all 5 adapter attempts, in each of 4 run-suite passes, so the error is deterministic for those queries. They count as zero above (over the 305 graded tasks: grounded 81.3% [76.7–85.6], correct 75.7% [70.8–80.7]). Every other system graded 307/307.

The six pilot-20 systems are the same run directories as `pilot-20/pilot-report.json` and the per-system summaries in `pilot-20/`.

## Spend

`report.py --spend` sums `search_cost_usd + model_cost_usd` (`result.json`; Expand's search cost is its billed searches at list price, `../bakeoff/pricing.py`) and `judge_cost_usd` (`cost.json`) over every run directory on disk under `runs/` other than `official/`. That covers WebCode, the supplementary suites below, smokes and the pilot.
- **Recorded cost of the run directories committed here: $64.67** (of which the 14 published WebCode rows $28.74).
- By system: Exa fast $11.53, Exa instant $7.80, Firecrawl $7.78, Parallel turbo $7.19, Exa webcode $6.76, Perplexity fast $5.76, Tavily $5.62, Exa auto $2.93, Perplexity web $2.17, Brave $2.10, Exa lite $2.03, Expand $1.32, Parallel fast $0.85, DeepSeek $0.82.
- Searches that failed with Exa's 402 were not billed and incurred no model or judge cost.
- OpenRouter's 5.5% credit-purchase fee is not included.

## Commands

```sh
cd benchmarks/search   # the bakeoff root
export EXA_BENCH_VENV="$PWD/.venv"   # created by `make venv` (README)
"$EXA_BENCH_VENV/bin/python" -m pytest -q -p no:cacheprovider        # offline tests

# Preflight (no paid calls):
DRY_RUN=1 runs/run-suite.sh webcode-rag rag-deepseek rag-parallel-fast rag-expand rag-tavily-advanced rag-brave-llm-context

# Original six WebCode systems: runs/pilot-20/run-pilot.sh (LIMIT=307); see pilot-20/README.md.
# Later systems (5-task smoke first, then the full run; resumable):
LIMIT=5 CONCURRENCY=5 PASSES=1 runs/run-suite.sh webcode-rag rag-parallel-fast
runs/run-suite.sh webcode-rag rag-parallel-fast                      # concurrency 10
runs/run-suite.sh webcode-rag rag-deepseek                           # DeepSeek capped at 4
CONCURRENCY=8 runs/run-suite.sh webcode-rag rag-expand
CONCURRENCY=6 runs/run-suite.sh webcode-rag rag-tavily-advanced rag-brave-llm-context
runs/run-suite.sh webcode-rag rag-exa-lite-highlights rag-exa-auto-highlights   # concurrency 10
runs/run-suite.sh webcode-rag rag-perplexity-web                                  # concurrency 10

runs/run-suite.sh <suite> [system ...]     # the supplementary runs, for example: runs/run-suite.sh seal-0
"$EXA_BENCH_VENV/bin/python" runs/report.py          # every table here
"$EXA_BENCH_VENV/bin/python" runs/report.py --spend  # spend only
```

`run-suite.sh` sources the bakeoff-root `.env` through `runs/env.sh` without printing it and sets the OpenRouter transport. It sets `HF_HOME=.hf-cache` and `HF_HUB_DISABLE_XET=1` (plain HTTPS dataset downloads). It runs one `bench run` per system in parallel. After a pass with failed tasks it waits 60, 120 and then 240 s and runs another pass, up to 4 passes. The runner skips every task that has a `grade.json`, so only execution errors are rerun; graded wrong answers never are.

## Caveats

1. **Authorship.** Exa wrote WebCode's data, grader and harness, and Exa's index may have crawled the source pages. Every system uses the same grader. The published Exa 79.4 is historical and does not name its tier.
2. **Evidence size differs by system.**
   - Tokens per citation: Firecrawl snippets 112, Parallel 255–498, DeepSeek summaries 270, Brave 279, Perplexity 376–387, Tavily 395, Exa 413–426 (all five Exa configurations), Expand 523.
   - Groundedness rises with more text.
3. **Date window and live web.** The six original WebCode runs were at 22:22–22:38 UTC on 10-26, Parallel fast and DeepSeek at 00:19–00:43 UTC on 10-27, Expand at 17:29–17:35 UTC on 10-27 (from its run directory's timestamps; its console log was not kept), Tavily and Brave at 23:35–23:46 UTC on 10-27, Exa lite and auto at 03:52–03:58 UTC and Perplexity web at 05:20–05:25 UTC on 10-28. Each is a single sample. CIs cover task sampling only, not judge or repeat-run variance.
4. **Latency** is from a laptop and includes answer generation.
5. **OpenRouter transport.** The model ids are unchanged (`require_parameters`); costs match upstream's pricing table. Chat Completions is used rather than the Responses API, and the default reasoning effort is not guaranteed to be identical (`pilot-20/README.md`, "Transport").
6. **Costs are mixed.**
   - Exa: Exa-reported `costDollars`.
   - Perplexity, Parallel, DeepSeek, Expand and Brave: list prices.
   - Firecrawl: credits × $0.00099 (Standard plan).
   - Tavily: reported credits × $0.008 (pay-as-you-go).
7. **DeepSeek.**
   - Queries are clipped to the documented 128 characters ([docs](https://api-docs.deepseek.com/guides/search)). WebCode queries are at most 90 characters, so nothing was clipped here. FRAMES and AA questions (medians 139 and 178 characters) would be clipped.
   - The docs give a 100 QPS limit. We still ran DeepSeek at concurrency 4.
   - Two WebCode queries get a persistent HTTP 500.

## Dataset pins (new loaders, `bakeoff/suites.py`)

| Suite | Source @ revision | File SHA-256 | Rows |
|---|---|---|---:|
| simpleqa-verified | HF `google/simpleqa-verified` @ `0dc97e0d28d8233463e005cdc4475cc2a13ba2dc` (2026-03-09), `simpleqa_verified.csv` | `b5db21155444763543fe31b67e7cf28ce2bb225742a5b889421c5f182e2f92f5` | 1,000 |
| seal-hard | HF `vtllms/sealqa` @ `0c298f519c871579c75920189b3858da29fe2c81` (2026-09-21, "update 092126"; next refresh 2026-10-29), `seal-hard.parquet` | `5bc6df2bf5012782675cbfc36a991d264320e4edcb332db60da2119b61383beb` | 254 |
| seal-0 | same revision, `seal-0.parquet` (all 111 questions are also in SEAL-Hard) | `381c9f86039c16570ee8d74ecbc3e687b553b21f7ebd7828a3d6a9e8f4705e7c` | 111 |
| aa-omniscience-public | `../data/AA-Omniscience_dataset_public.csv`, byte-identical to HF `ArtificialAnalysis/AA-Omniscience-Public` @ `e4883edbb9f5ccf2b2a8fdc6fb65e01a58e99849` | `1e04603dafa3bd0d16d8151f07a5eb74c43d90c3a85d2fca120da2359174d02f` | 600 (as expected) |
| frames (upstream) | HF `google/frames-benchmark` @ `58d9fb6330f3ab1316d1eca12e5e8ef23dcc22ef`, `test.tsv` | (upstream pin) | 824 |

Grading:
- SimpleQA Verified and SealQA use FRAMES' grading: upstream `Frames.grade`, the simple-evals SimpleQA prompt pair. They add `GroundedRAGGrader`'s groundedness call on the retrieved citations.
- AA-Omniscience uses `GroundedRAGGrader` unchanged.
- The judge throughout is gpt-6-luna. SimpleQA Verified's official autorater (GPT-4.1, modified prompt) and SealQA's Colab template were not used here; they are used in `official/`.

## Supplementary: single-search mode, not the benchmark's official protocol

These runs used the WebCode-style single-search RAG on suites whose designers specify a different protocol: model and grader, no tools (SimpleQA Verified's card says it is meant to be run without tools), agentic search, or AA's private set and rubric. **Do not publish or compare these with any leaderboard.** They were stopped at 00:32 UTC on 10-27 when the scope changed and are kept on disk under `runs/<suite>/`.

Why runs are incomplete:
- **Exa ran out of credits.** From about 00:08 UTC every Exa search returned HTTP 402 `NO_MORE_CREDITS`. The Exa rows for seal-hard and aa-omniscience-public therefore exclude the failed tasks and are biased toward the tasks that ran first (failed tasks: fast 36 and 29, instant 25 and 61, webcode 153 and 414). A recheck at 00:17 UTC still got 402. The Exa reruns were cancelled with the scope change.
- **Never run on these suites:** DeepSeek, Parallel fast, Expand, Tavily and Brave; the official-grader suites (`official/`) replaced them.

| Suite | Systems complete | Partial or not run |
|---|---|---|
| seal-0 (111) | all six competitors | — |
| seal-hard (254) | Parallel turbo, Perplexity fast, Firecrawl | Exa ×3 partial (402) |
| aa-omniscience-public (600) | Parallel turbo, Perplexity fast, Firecrawl | Exa ×3 partial (402) |
| simpleqa-verified (1,000) | Parallel turbo, Perplexity fast, Firecrawl (999/1,000; one task still failed when stopped) | Exa not run |

Headline numbers, correct % [95% CI] / grounded %:

| System | seal-0 | seal-hard | aa-omniscience-public | simpleqa-verified |
|---|---|---|---|---|
| rag-perplexity-fast | 39.6 [30.6–48.6] / 46.8 | 40.9 [35.0–46.9] / 48.4 | 84.0 [81.0–87.0] / 85.5 | 97.5 [96.5–98.4] / 97.9 |
| rag-parallel-turbo | 16.2 [9.9–23.4] / 17.1 | 26.8 [21.7–32.3] / 32.3 | 76.2 [72.7–79.5] / 77.8 | 93.7 [92.1–95.2] / 94.4 |
| rag-firecrawl-search | 16.2 [9.9–23.4] / 20.7 | 23.6 [18.5–28.7] / 26.0 | 49.7 [45.7–53.7] / 51.0 | 89.6 [87.7–91.4] / 89.3 |
| rag-exa-fast-highlights | 36.0 [27.0–45.0] / 52.3 | 48.6 / 63.8 (218/254 graded) | 80.7 / 83.7 (571/600) | — |
| rag-exa-instant-highlights | 37.8 [28.8–46.8] / 50.5 | 47.2 / 61.1 (229/254) | 78.5 / 81.6 (539/600) | — |
| rag-exa-webcode | 36.0 [27.9–45.0] / 49.5 | 46.5 / 60.4 (101/254) | 75.8 / 81.2 (186/600) | — |

The full per-suite tables, with costs, latency and C/I/NA, are in the `report.py` output and in `runs/report.json`.
