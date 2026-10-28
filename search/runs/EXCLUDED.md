# What the stored run records keep

Stored records keep questions, answers, judge labels and reasoning, scores, costs, latencies and
per-record citation counts and evidence-token totals; per-result URLs, titles and text were removed.
Scores recompute from the stored grades; groundedness re-grading and the leak audit need a fresh run,
which writes full records. The same reduction applies to every system and suite.
`tools/strip_result_details.py` performs it (idempotent; `--check` verifies the stored records, and
CI runs it); run it on a new run's records before committing (`CONTRIBUTING.md`). After it, `runs/`
holds 92 MB and `aa-stirrup/runs/` 27 MB.

## Harness runs (`runs/**/tasks/<task>/`)

The repository holds 40,826 `result.json` and 40,824 `grade.json`.

| Record | Removed | Kept in its place |
|---|---|---|
| `result.json` | `messages`: the prompt sent to the answer model | — |
| `result.json` | `citations`: URL, title, published date and text of each citation (375,298 citations) | `num_citations`, `citation_text_tokens` (o200k_base tokens, the unit the tables report), `citation_text_chars` |
| `result.json` | `filtered_results`: URL, title and reason of each leak-filter drop (7,830 drops) | `filtered_results_by_reason` (counts by rule) |
| `result.json` | `skipped_results`: URL and reason of each result skipped as empty (32) | `skipped_results_by_reason` |
| `grade.json` | `details.evidence`: the judge's quotes from the citations (12,367 WebCode grades) | — |
| `grade.json` | `details.answer_source_urls`: the citations the judge attributed the answer to (24,036 URLs) | `details.num_answer_sources` |

Each changed record lists what it lost in `_redacted: {"removed": [...], "see": "runs/EXCLUDED.md"}`;
the file's indent and escaping are unchanged. Kept as written: `task_id`, `prompt`, `answer`,
`search_queries`, `query_clipped`, `answer_protocol`, costs, `usage`, `latency_ms`, `attempt`; every
grade score (including `avg_citation_tokens`, `total_citation_tokens`, `num_citations`,
`filtered_results`), label, judge reasoning and raw judge reply; `cost.json`, `error.json`,
`config.json`, `summary.json`, the per-system `<system>.json` summaries and `logs/`.

Consequences:

- `runs/report.py`, `runs/official/report.py` and `runs/pilot-20/pilot_report.py` read the per-record
  counts (`citation_count()` and `filtered_by_reason()` in `_records.py`, `mean_citation_tokens()` in
  `report.py`) and fall back to the full lists in a fresh run's records. Every table regenerates
  byte-identically from the stored records.
- `runs/leak-audit/audit.py` (citation text) and `url_title_check.py` (citation URLs and titles) need
  a fresh WebCode run. Their stored outputs keep counts, reasons, citation indices and verdicts; the
  citation URLs, titles and judge quotes in them were removed in the same pass.
- Model answers and agent search queries are kept verbatim, including any URL they contain (267 harness
  answers; 61 AA search queries in 57 records).

## AA-Omniscience via Stirrup (`aa-stirrup/runs/{pilot-20,full-600}/<system>/aao-*.json`)

The repository holds 7,920 records and one superseded attempt (`attempts/aao-*/`). Removed: `trace`,
the agent conversation turn by turn (including the rendered `web_search` results and `web_fetch` page
text the model saw), and the URL of each fetch (6,106 fetches in 3,353 records). Kept: question,
gold, answer, grade, raw grader reply, status, turns, wall/model/agent seconds, `usage` (per-call
tokens and cost), `tools.searches` (query, latency, cost, result count, filtered count, attempts,
error), `tools.fetches` (latency, success, allowed, filtered) and the `search` totals.

## Signed URLs and machine paths

`tools/scrub_presigned_urls.py` replaces the query string of presigned S3/CDN URLs
(`X-Amz-Credential`, `AWSAccessKeyId`, `Signature`, `AKIA…`) and Azure SAS URLs (`sig`, `jwt`, `sv`,
`se`) with `?<presigned-params-redacted>`. Every such URL in the stored records was a citation or
fetch URL, so none remains. `tools/scrub_paths.py` replaces absolute paths in tracebacks and logs
with `<repo>`, `<home>` and `<venv>`, rejoining paths the log renderer wrapped across lines (CI runs
it with `--check`).

## Not included at all

- The vendored copy of `exa-labs/benchmarks @ 0d817af` (4.6 MB). It is cloned at the pin instead
  (`make upstream`) and installed editable; nothing in it was edited.
- `.env` and any other credential file, editor and tool scratch directories, `__pycache__/`, `.pytest_cache/`.
- Raw provider payloads kept elsewhere in the working tree: a 20-task search-only probe
  (`runs/pilot-20/search-probe/`, every provider's full response body), two full AA-Stirrup smoke
  traces, and verbatim copies of Artificial Analysis' pages (replaced by URLs, read dates and
  Wayback Machine links in `aa-stirrup/runs/evidence/README.md`).

## Supplementary single-search runs (`runs/{seal-0,seal-hard,simpleqa-verified,aa-omniscience-public}/`)

Kept (reduced as above) although `runs/RESULTS.md` excludes them from comparisons: they are the
evidence behind the RESULTS.md "Supplementary" section and the leak-filter finding in
`runs/official/RESULTS.md` (an earlier 97.5 % for Perplexity was inflated by benchmark pages in its
results, which the leak filter now removes).

## Run-directory names and fingerprints

Expand's system id was shortened to `rag-expand` after its official-suite runs; the run directories
were renamed with it, so the hash in their names differs from what the current code computes. Code
comments and docs were edited after the runs; the fingerprints stored with each run are those at run
time.
