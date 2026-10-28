# WebCode RAG leak audit

Question: of the citations the WebCode RAG runs returned, how many came from the benchmark
itself (the `exa-labs/benchmarks` repo or forks, Hugging Face mirrors, pages that reproduce the
question or the gold answer, AA microevals, blogs copying the dataset), and what would each
system's groundedness be with those citations removed?

Answer: 8 of 24,115 citations (0.03%) match the leak rules, 8 of 2,454 tasks had one, the
judge's own source attribution never named a flagged citation, and removing those citations
and re-judging changes no audited system's groundedness by more than 0.3 pp (repeat judgments
on that one change differed, see below). Nothing at all was retrieved from `exa-labs`, a WebCode
dataset mirror, or artificialanalysis.ai. The rules are heuristic, so a match is a flag, not
verified contamination, and the re-grade covers groundedness only: answers were not regenerated
without the flagged citations.

Read-only over the eight WebCode runs that existed when the audit ran (`runs/pilot-20/*-webcode-rag-*`
for Exa fast, instant and webcode, Parallel turbo, Perplexity fast and Firecrawl; `runs/webcode-rag/*`
for Parallel fast and DeepSeek); gold from `upstream/data/webcode/rag.jsonl`. The six later WebCode runs
(Expand, Tavily, Brave, Perplexity web, Exa lite, Exa auto) get the URL and title check in Table 4. The only live calls were 8 judge calls plus
2 repeat calls (`openai/gpt-6-luna` via OpenRouter), under one cent in total.

## Rules

A citation is leaked if either set of rules fires. The first match is the recorded reason.

1. The official suites' filter, unchanged: `bakeoff.official_rag.contamination_reason`
   (`host`: URL on `huggingface.co/datasets` or `kaggle.com`; `term`: a benchmark name such as
   `sealqa`/`simpleqa`/`frames-benchmark` in URL, title or text; `canary` (WebCode has none);
   `verbatim_question`: the first 120 normalized characters of a 60+ character question appear in
   the text).
2. WebCode extensions (`audit.py`):
   - `webcode_host`: `github.com/exa-labs`, `exa-labs/benchmarks`, `artificialanalysis.ai`, or a
     `huggingface.co/datasets/...webcode...` URL;
   - `webcode_term`: the word `webcode` or `exa-labs`/`exa labs` in URL, title or text;
   - `verbatim_query`: the whole normalized query appears in the text, the title, or the URL slug.
     WebCode queries are 37-90 character keyword strings (213 of 307 are under the official rule's
     60-character floor), so the floor is dropped and title and URL slug are checked too;
   - `answer_with_query`: the text contains both the query and the expected answer (15+ chars).
     The answer alone is not a leak signal: thousands of citations contain it, and many contain the
     gold `citation_excerpt` verbatim, because they are the source pages the benchmark was built from.

Leaked citation = removed; "judge used it" = its URL is in the grade's `answer_source_urls`
(the judge's `source_indices` resolved to URLs; a fresh run writes them, the stored grades keep
only their count).

Re-grade: for every (system, task) with at least one leaked citation, `GroundedRAGGrader._call_groundedness`
(same prompt, numbering and schema as the runs) is re-run on the remaining citations with
`Judge("openai/gpt-6-luna")` through the bakeoff's OpenRouter transport (default effort, 16k max
output tokens). Correctness is not re-run; it does not depend on the citations. A task with no
citations left would be UNGROUNDED without a call (none occurred: every leaked task kept 9 of 10).

## Table 1: leaked citations per system

| System | Citations | Leaked | Leaked % | Tasks with >=1 leak | Tasks where judge used a leaked citation |
|---|---:|---:|---:|---:|---:|
| rag-perplexity-fast | 2803 | 0 | 0.00 | 0 | 0 |
| rag-exa-fast-highlights | 3070 | 0 | 0.00 | 0 | 0 |
| rag-parallel-fast | 3070 | 2 | 0.07 | 2 | 0 |
| rag-parallel-turbo | 3046 | 0 | 0.00 | 0 | 0 |
| rag-exa-webcode | 3070 | 0 | 0.00 | 0 | 0 |
| rag-exa-instant-highlights | 2987 | 0 | 0.00 | 0 | 0 |
| rag-deepseek | 3011 | 4 | 0.13 | 4 | 0 |
| rag-firecrawl-search | 3058 | 2 | 0.07 | 2 | 0 |
| **all 8 runs** | 24115 | 8 | 0.03 | 8 | 0 |

## Table 2: groundedness, recorded vs. recomputed with leaked citations removed

Denominator is the run's graded tasks, as in `RESULTS.md` (DeepSeek's two failed tasks excluded).

| System | Graded tasks | Grounded (recorded) | Re-graded tasks | Flips (grounded -> ungrounded / ungrounded -> grounded) | Grounded (filtered) | Delta (pp) |
|---|---:|---:|---:|---:|---:|---:|
| rag-perplexity-fast | 307 | 94.5 | 0 | 0 / 0 | 94.5 | +0.0 |
| rag-exa-fast-highlights | 307 | 88.6 | 0 | 0 / 0 | 88.6 | +0.0 |
| rag-parallel-fast | 307 | 87.3 | 2 | 0 / 0 | 87.3 | +0.0 |
| rag-parallel-turbo | 307 | 87.0 | 0 | 0 / 0 | 87.0 | +0.0 |
| rag-exa-webcode | 307 | 86.6 | 0 | 0 / 0 | 86.6 | +0.0 |
| rag-exa-instant-highlights | 307 | 85.7 | 0 | 0 / 0 | 85.7 | +0.0 |
| rag-deepseek | 305 | 81.3 | 4 | 0 / 0 | 81.3 | +0.0 |
| rag-firecrawl-search | 307 | 54.4 | 2 | 1 / 0 | 54.1 | -0.3 |

Re-grade cost: 8 tasks, 8 judge calls, $0.0043 reported by OpenRouter (plus $0.0004 for the two
repeat calls below). 0 retries, 0 failures.

The one flip, `rag-firecrawl-search rag_105` (gold: `os.spawnve` returns 127 on invalid env
keys/values): the removed citation was a `facebook.com/fb-answers` page the original judge had
not used; both the original grade and the re-grade cite the same `docs.python.org` passage, the
gold source. The re-grade called it UNGROUNDED; two repeat calls on the same filtered citations
both returned GROUNDED (`regrade_repeats.json`). The re-grade gives 54.1; with either repeat it is 54.4.

## Table 3: leaking domains

| Domain | Leaked citations | Reason | What it is |
|---|---:|---|---|
| huggingface.co | 4 | `host` (official rule) | Hugging Face dataset repositories holding licence text (GFDL, rag_005 and rag_031: 2), an agent log (rag_283: 1) and a SWE-bench predictions diff (rag_285: 1), all returned by DeepSeek. None is a WebCode mirror; they fire the generic dataset-host rule. |
| www.facebook.com | 4 | `verbatim_query` | `facebook.com/fb-answers/<slug>` AI answer pages whose slug is exactly the WebCode query (rag_003, rag_164 via Parallel fast; rag_090, rag_105 via Firecrawl). Other fb-answers citations were returned whose slugs are not WebCode queries; they are not flagged. |

Zero hits for `webcode_host`, `webcode_term`, `answer_with_query`, `term`, and the official
`verbatim_question` rule on its own (every verbatim hit here is a query under 60 characters or a
slug/title match the official rule does not check).

## Table 4: the later runs, URL and title only

The Expand, Tavily, Brave, Perplexity web, Exa lite and Exa auto WebCode runs were made after this audit, and the records it ran on
carried no citation text, so `url_title_check.py` applied only the rules that read a citation's URL and title:
the official `host` rule (`huggingface.co/datasets`, `kaggle.com/`), the official `term` rule
(benchmark names in URL or title), and the WebCode `webcode_host`, `webcode_term` and `verbatim_query`
(title and URL slug) rules. The text rules (`verbatim_question`, `answer_with_query`, `verbatim_query` on
text) cannot run, and no re-grade was done. Output: `url_title_check.json`.

| System | Citations | host | term | webcode_host | webcode_term | verbatim_query | Flagged |
|---|---:|---:|---:|---:|---:|---:|---:|
| rag-expand | 3026 | 1 | 0 | 0 | 0 | 0 | 1 |
| rag-tavily-advanced | 3070 | 0 | 0 | 0 | 0 | 2 | 2 |
| rag-brave-llm-context | 3070 | 0 | 0 | 0 | 0 | 0 | 0 |
| rag-perplexity-web | 2807 | 1 | 0 | 0 | 1 | 0 | 2 |
| rag-exa-lite-highlights | 3070 | 0 | 0 | 0 | 0 | 0 | 0 |
| rag-exa-auto-highlights | 3070 | 0 | 0 | 0 | 0 | 0 | 0 |

The Expand hit (rag_046) is a Hugging Face dataset repository hosting ffmpeg's HTML documentation, the
generic dataset-host rule firing on a legitimate source; the two Tavily hits (rag_090, rag_105) are the
same `facebook.com/fb-answers/<query slug>` pages Firecrawl returned (Table 3). Perplexity web's are a Hugging Face dataset repository holding a Python environment (rag_137, the generic host rule again) and an Upstash blog post with "webcode" in its URL (rag_189). In total 5 of 18,113 citations.

## Recommendation

Report WebCode unfiltered, as it is in `RESULTS.md`, with a pointer here:

- In the eight audited runs, 8 of 24,115 citations matched the rules, in eight tasks (four DeepSeek,
  two Parallel fast, two Firecrawl). Half are the generic dataset-host rule firing on license text and
  agent logs; the other four are `fb-answers` pages whose slug is the query.
- Removing them and re-grading groundedness changed one Firecrawl label, which two repeat judgments
  reversed.
- The six later runs had the URL and title check only (Table 4): 5 of 18,113 citations flagged.

If the bakeoff is re-run, apply `verbatim_query` (text, title, URL slug, no length floor) at
retrieval time alongside the official filter so the question does not need to be asked again.

## Files

- `audit.py`: the rules and the scan; writes `leaked_citations.jsonl`, `regrade_plan.json`, `audit.json`.
  It reads citation text, URLs and titles, which the committed records do not carry (`../EXCLUDED.md`),
  so it can only be re-run on a fresh WebCode run.
- `regrade.py`: the groundedness re-grade (resumable); writes `regrades.json`.
- `regrade_repeats.json`: the two repeat calls on the flipped task.
- `report.py`: Tables 1-3 from the JSON; writes `tables.md` and `summary.json`.
- `url_title_check.py`: Table 4 (offline; needs a fresh WebCode run, since the committed records keep
  only citation counts); writes `url_title_check.json`.
- The stored JSON outputs keep counts, reasons, citation indices and verdicts; citation URLs, titles
  and judge quotes were removed from them (`../EXCLUDED.md`).
- Re-run from the bakeoff root: `.venv/bin/python -I runs/leak-audit/audit.py`,
  then `regrade.py` with the OpenRouter key sourced, then `report.py`.
