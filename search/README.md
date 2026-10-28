# Search-API benchmarks

A reproducible comparison of web-search APIs for retrieval-augmented answering: Expand, Exa,
Perplexity, Parallel, Firecrawl, DeepSeek, Tavily and Brave, measured on Exa's open
WebCode harness, on three public QA benchmarks with their designers' grader prompts (SimpleQA Verified,
SealQA, FRAMES), and on AA-Omniscience through Artificial Analysis' Stirrup search agent. The harness is an
unmodified, pinned clone of [exa-labs/benchmarks](https://github.com/exa-labs/benchmarks); this directory adds
adapters, suites and graders as an in-process overlay. Every number below was produced by the code here between
2026-10-26 and 2026-10-28 (UTC), every per-task record behind it is committed (without per-result URLs, titles and text; see
[`runs/EXCLUDED.md`](runs/EXCLUDED.md)), and the scores recompute offline from the stored grades. The protocols and
every deviation from the designers' are in [`METHODOLOGY.md`](METHODOLOGY.md); limitations are under [Caveats](#caveats).

Each provider was called through its API with the request shape listed under [Systems](#systems). Expand is
Expand Search, `POST /v1/search`, one request per search, 10 results, $1.50 per 1,000 (list).

## Results

Costs are the recorded search, answer and judge costs per task ([Cost](#cost-and-wall-time-as-measured)). Latency
is search + answer from a laptop, judge excluded (the AA wall-time column includes grading). CIs are 95 %
task-bootstrap intervals. A task that failed on every retry counts as zero over the full suite (three tasks
across two rows, named below). Every table is a single pass per system on the live web; rows are ordered by
the headline score.

### WebCode RAG (Exa's protocol, 307 tasks)

Exa's headline is **grounded** (the citations contain the gold facts); **correct** (the answer is right)
deserves equal weight. Groundedness rises with evidence length, since a longer excerpt is more likely to
contain the gold fact, so read it next to the citation-token column: per-citation evidence ranges from 112 to
523 tokens across systems, and Expand's is the longest. On correctness Perplexity fast, Expand and Brave
are within 1.3 points of each other. Judge `gpt-6-luna`. Full table: [`runs/RESULTS.md`](runs/RESULTS.md);
per-row records: `runs/report.json` → `run_dir`.

| System | Grounded % [95% CI] | Correct % [95% CI] | Cit. tokens | Search $/1k | Total $/1k | Latency s mean / p90 | Run |
|---|---:|---:|---:|---:|---:|---:|---|
| rag-expand | 95.8 [93.5–97.7] | 87.6 [84.0–91.2] | 523 | 1.50 | 4.30 | 3.9 / 6.2 | `webcode-rag/…-09e2964740` |
| rag-perplexity-fast | 94.5 [91.9–96.7] | 87.9 [84.4–91.5] | 376 | 1.00 | 3.08 | 2.8 / 4.3 | `pilot-20/…-26d497ae83` |
| rag-perplexity-web | 93.5 [90.6–96.1] | 86.0 [82.1–89.9] | 387 | 5.00 | 7.06 | 3.2 / 4.9 | `webcode-rag/…-53bf7ec5b1` |
| rag-brave-llm-context | 92.2 [88.9–95.1] | 86.6 [82.7–90.2] | 279 | 5.00 | 6.84 | 4.4 / 6.4 | `webcode-rag/…-288ce01625` |
| rag-exa-auto-highlights | 88.9 [85.3–92.2] | 81.8 [77.5–86.0] | 415 | 7.00 | 9.56 | 4.7 / 7.2 | `webcode-rag/…-53aa0bedea` |
| rag-exa-fast-highlights | 88.6 [85.0–91.9] | 80.1 [75.6–84.4] | 422 | 7.00 | 9.58 | 3.6 / 5.3 | `pilot-20/…-7dcbaf2322` |
| rag-exa-lite-highlights | 87.6 [83.7–91.2] | 77.9 [73.0–82.4] | 418 | 4.00 | 6.60 | 3.8 / 6.2 | `webcode-rag/…-0ce89d8de3` |
| rag-parallel-fast | 87.3 [83.4–90.9] | 84.0 [79.8–87.9] | 255 | 1.00 | 2.77 | 3.5 / 5.4 | `webcode-rag/…-ccfac1c1fc` |
| rag-parallel-turbo | 87.0 [83.1–90.6] | 80.1 [75.6–84.4] | 498 | 1.00 | 3.72 | 3.3 / 5.1 | `pilot-20/…-f177439c59` |
| rag-exa-webcode (Exa's WebCode preset) | 86.6 [82.7–90.2] | 79.5 [74.9–83.7] | 413 | 7.00 | 9.45 | 11.8 / 19.0 | `pilot-20/…-ca6bb5113c` |
| rag-exa-instant-highlights | 85.7 [81.8–89.6] | 76.5 [71.7–81.1] | 426 | 4.00 | 6.57 | 3.6 / 5.5 | `pilot-20/…-ff3306f6b1` |
| rag-deepseek | 80.8 [76.2–85.0] | 75.2 [70.4–80.1] | 270 | 0.74 | 2.68 | 3.4 / 5.3 | `webcode-rag/…-0bc34557c4` |
| rag-tavily-advanced | 78.5 [73.9–83.1] | 71.7 [66.4–76.5] | 395 | 16.00 | 18.30 | 6.6 / 8.9 | `webcode-rag/…-1b39563614` |
| rag-firecrawl-search | 54.4 [48.9–59.9] | 51.8 [46.3–57.3] | 112 | 1.97 | 3.11 | 3.7 / 5.4 | `pilot-20/…-d15af8a79a` |

Run directories are `runs/<dir>/<system>-webcode-rag-<hash>/`; the `pilot-20/` directories hold full 307-task
runs (the 20 pilot tasks resumed into them). DeepSeek failed
`rag_006` and `rag_231` on every attempt (HTTP 500); they count as zero (graded only, on 305 tasks: 81.3
grounded, 75.7 correct).

### SimpleQA Verified, SealQA and FRAMES with the designers' grader prompts

Headline metric per the designer: **F1** (SimpleQA Verified, judge `gpt-4.1`), **accuracy** (SealQA,
judge `gpt-4o-mini`, temperature 0; FRAMES, Figure 6 prompt, judge `gpt-4.1`). One search with 10 results
and a benchmark-leak filter, identical for every system; `model-only` is the designers' own no-search
setting. Rows are ordered by Seal-Hard accuracy, the no-search baseline last; every row covers the whole
suite. Seal-0 is the 111-question subset of Seal-Hard that the SealQA authors publish as a
separate headline number (the test suite checks that every Seal-0 question is in Seal-Hard); it is not
independent evidence, and no combined score should count both. Full tables and the run directory of every row: [`runs/official/RESULTS.md`](runs/official/RESULTS.md),
`runs/official/report.json`.

| System | SimpleQA Verified F1 | Seal-0 acc. (111, subset of Seal-Hard) | Seal-Hard acc. (254) | FRAMES acc. (824) |
|---|---:|---:|---:|---:|
| exa-auto-highlights | 97.5 [96.5–98.4] | 42.3 [33.3–51.4] | 56.7 [50.8–63.0] | 77.7 [74.8–80.5] |
| exa-lite-highlights | 97.3 [96.2–98.2] | 37.8 [28.8–46.8] | 55.5 [49.6–61.4] | 76.8 [73.9–79.6] |
| exa-fast-highlights | 96.9 [95.8–97.9] | 44.1 [35.1–53.2] | 53.9 [48.0–59.8] | 77.1 [74.2–79.9] |
| expand (Expand Search) | 97.6 [96.6–98.5] | 38.7 [29.7–47.7] | 52.8 [46.5–58.7] | 75.8 [72.9–78.8] |
| brave-llm-context | 98.0 [97.1–98.8] | 30.6 [21.6–39.6] | 49.6 [43.7–55.9] | 76.1 [73.2–79.0] |
| tavily-advanced | 95.8 [94.5–97.0] | 36.0 [27.0–45.0] | 48.4 [42.1–54.7] | 74.3 [71.2–77.2] |
| perplexity-web | 96.8 [95.7–97.9] | 36.0 [27.0–45.0] | 46.5 [40.2–52.8] | 75.5 [72.5–78.4] |
| perplexity-fast | 97.3 [96.3–98.3] | 38.7 [29.7–47.7] | 45.3 [39.4–51.6] | 72.8 [69.7–75.8] |
| parallel-turbo | 96.0 [94.7–97.2] | 25.2 [17.1–33.3] | 41.3 [35.4–47.6] | 75.5 [72.6–78.4] |
| firecrawl-search | 91.4 [89.6–93.1] | 29.7 [21.6–38.7] | 41.3 [35.4–47.6] | 70.0 [66.7–73.2] |
| parallel-fast | 96.1 [94.9–97.3] | 25.2 [17.1–33.3] | 39.8 [33.9–46.1] | 75.1 [72.1–78.0] |
| deepseek | 91.7 [89.9–93.3] | 27.0 [18.9–36.0] | 38.2 [32.3–44.1] | 71.7 [68.6–74.8] |
| model-only (no search) | 40.1 [37.0–43.1] | 9.0 [4.5–14.4] | 26.8 [21.7–32.3] | 66.3 [63.0–69.5] |

On SimpleQA Verified the search systems score 91.4–98.0 F1 against 40.1 without search; the top five (Brave
98.0, Expand 97.6, Exa auto 97.5, Perplexity fast 97.3, Exa lite 97.3) are within 0.7 points and ten of the
twelve within 2.2, so the suite separates search from no search far more than it separates search systems. The leak filter removed 1,373 results per 1,000 questions from Expand (1,333 of them
Hugging Face dataset pages), 1,004 from Perplexity web (961) and 945 from Perplexity fast (905). SealQA separates
the systems more: on Seal-Hard the three Exa tiers lead (auto 56.7, lite 55.5, fast 53.9), then Expand 52.8,
Brave 49.6 and Tavily 48.4; Expand's paired differences from those five are not significant, and it is ahead of
Perplexity web and fast, Parallel, Firecrawl and DeepSeek (paired table below). Per task
including the judge: $0.003–0.006 on SealQA and FRAMES and $0.004–0.006 on SimpleQA Verified for most systems;
Exa lite ≈ $0.006–0.008, Brave and Perplexity web ≈ $0.007–0.008, Exa fast and auto ≈ $0.009–0.011, Tavily ≈ $0.019–0.021,
following their search prices.

### AA-Omniscience on AA's Stirrup agent (public 600)

Omniscience Index OI = 100·(c − i)/N; accuracy is the number AA's Search Index uses. Answer and grader
`gpt-5.6-luna` (medium), paper grader prompt, 25 turns, `web_search` + `web_fetch` + `finish`. Public
questions, not AA's private 600: not comparable to AA's leaderboard. On 600 questions the 95 % interval
is about ±2.5 points on accuracy and ±5 on OI, so the search systems are a cluster. Records:
`aa-stirrup/runs/full-600/<system>/`; table: [`aa-stirrup/runs/full-600/summary.md`](aa-stirrup/runs/full-600/summary.md).

| System | OI [95% CI] | Accuracy % [95% CI] | C / I / P / NA | Searches/q | Search $/q | Total $/q | Wall s/q mean (p50) | s/search |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Expand Search | 82.2 [77.5–86.5] | 90.7 [88.3–93.0] | 544 / 51 / 5 / 0 | 3.1 | 0.0046 | 0.0106 | 16 (10) | 0.86 |
| Perplexity fast | 81.5 [76.8–86.0] | 90.3 [87.8–92.7] | 542 / 53 / 5 / 0 | 3.2 | 0.0032 | 0.0081 | 12 (9) | 0.27 |
| Perplexity web | 81.2 [76.5–85.7] | 90.2 [87.8–92.5] | 541 / 54 / 3 / 2 | 3.2 | 0.0158 | 0.0207 | 13 (9) | 0.47 |
| Brave (LLM context) | 80.5 [75.7–85.2] | 89.8 [87.3–92.2] | 539 / 56 / 4 / 1 | 3.9 | 0.0197 | 0.0257 | 20 (12) | 1.60 |
| Exa auto highlights | 80.3 [75.7–85.0] | 89.7 [87.2–92.0] | 538 / 56 / 4 / 2 | 3.2 | 0.0227 | 0.0286 | 16 (11) | 1.44 |
| Exa lite highlights | 79.8 [75.0–84.5] | 89.5 [87.0–91.8] | 537 / 58 / 4 / 1 | 3.4 | 0.0136 | 0.0200 | 14 (9) | 0.42 |
| Parallel turbo | 78.5 [73.5–83.3] | 88.8 [86.3–91.3] | 533 / 62 / 5 / 0 | 3.7 | 0.0037 | 0.0104 | 15 (9) | 0.40 |
| Firecrawl search | 78.2 [73.2–83.0] | 88.7 [86.2–91.2] | 532 / 63 / 2 / 3 | 5.4 | 0.0105 | 0.0150 | 24 (15) | 1.30 |
| Exa fast highlights | 77.5 [72.5–82.3] | 88.3 [85.7–90.8] | 530 / 65 / 4 / 1 | 3.4 | 0.0238 | 0.0300 | 14 (10) | 0.41 |
| Tavily (advanced) | 76.8 [71.7–81.8] | 87.8 [85.2–90.3] | 527 / 66 / 4 / 2 + 1 failed | 4.4 | 0.0709 | 0.0785 | 32 (19) | 3.85 |
| Parallel fast | 76.2 [71.0–81.2] | 87.7 [85.0–90.3] | 526 / 69 / 4 / 1 | 4.0 | 0.0040 | 0.0097 | 17 (11) | 0.68 |
| DeepSeek | 75.8 [70.7–80.8] | 87.3 [84.7–90.0] | 524 / 69 / 3 / 4 | 4.4 | 0.0032 | 0.0123 | 18 (11) | 0.55 |
| Model only (no search) | −2.8 [−10.7–5.0] | 46.8 [42.8–50.8] | 281 / 298 / 4 / 17 | 0.0 | 0.0000 | 0.0012 | 10 (8) | — |

Tavily's row counts one failed question (`aao-054`, the "+ 1 failed") as not attempted, i.e. zero in OI and
accuracy ([`METHODOLOGY.md` §9](METHODOLOGY.md#9-statistics)). Its stored error is
`HTTPStatusError: Client error '400 Bad Request' for url 'https://api.tavily.com/search'` on every attempt
(graded only, on 599 questions: OI 77.0, accuracy 88.0); the record does not keep Tavily's response body.
Expand's token, model-cost and wall means (`summary.md`) include `aao-447`, where the answer model produced two
very long replies (127,999 output tokens each, 701 s and 731 s); the task took 1,450 s, of which its two searches
took 1.7 s.

### Paired differences: Expand minus each competitor

For every suite, Expand's per-task score minus the competitor's on the same task (WebCode grounded and correct;
the official suites' per-task accuracy, which for SimpleQA Verified is within 0.2 points of F1; AA-Omniscience
`grade == "CORRECT"`), averaged, with a 95 % paired percentile bootstrap over tasks (10,000 resamples, seed 0;
failed tasks count as zero). Points; `*` marks an interval that excludes zero. `runs/paired.py` (`make paired`)
computes it offline from the stored grades into `runs/paired.json`. Every published run is complete and paired.
Each interval is a separate comparison, not adjusted for multiple testing (of 81, about four would exclude zero
by chance alone); an interval that includes zero means the difference is not significant, not that the two
systems are equal.

<!-- paired:begin (generated by runs/paired.py) -->
| Expand minus | WebCode grounded | WebCode correct | SimpleQA Verified acc. | Seal-0 | Seal-Hard | FRAMES | AA-Omniscience acc. |
|---|---:|---:|---:|---:|---:|---:|---:|
| perplexity-fast | +1.3 [−0.7, +3.6] | −0.3 [−3.6, +2.9] | +0.3 [−0.6, +1.2] | +0.0 [−9.0, +9.0] | +7.5 [+2.0, +13.0] * | +3.0 [+0.8, +5.3] * | +0.3 [−1.5, +2.2] |
| perplexity-web | +2.3 [+0.3, +4.6] * | +1.6 [−1.6, +5.2] | +0.8 [−0.2, +1.8] | +2.7 [−3.6, +9.0] | +6.3 [+1.2, +11.4] * | +0.4 [−1.8, +2.5] | +0.5 [−1.0, +2.2] |
| exa-fast-highlights | +7.2 [+3.6, +11.1] * | +7.5 [+2.9, +12.4] * | +0.7 [−0.3, +1.8] | −5.4 [−14.4, +2.7] | −1.2 [−7.5, +5.1] | −1.2 [−4.0, +1.6] | +2.3 [+0.2, +4.5] * |
| exa-instant-highlights | +10.1 [+6.2, +14.0] * | +11.1 [+6.2, +16.3] * | — | — | — | — | — |
| exa-webcode | +9.1 [+4.9, +13.4] * | +8.1 [+3.3, +13.0] * | — | — | — | — | — |
| exa-lite-highlights | +8.1 [+4.2, +12.1] * | +9.8 [+4.9, +15.0] * | +0.3 [−0.7, +1.3] | +0.9 [−8.1, +9.9] | −2.8 [−9.1, +3.1] | −1.0 [−3.8, +1.8] | +1.2 [−1.2, +3.5] |
| exa-auto-highlights | +6.8 [+3.3, +10.7] * | +5.9 [+1.3, +10.4] * | +0.1 [−0.9, +1.1] | −3.6 [−12.6, +5.4] | −3.9 [−10.2, +2.4] | −1.8 [−4.6, +1.0] | +1.0 [−1.2, +3.2] |
| parallel-turbo | +8.8 [+4.6, +13.0] * | +7.5 [+2.6, +12.4] * | +1.7 [+0.5, +3.0] * | +13.5 [+3.6, +23.4] * | +11.4 [+4.7, +18.1] * | +0.4 [−2.3, +2.9] | +1.8 [−0.3, +4.0] |
| parallel-fast | +8.5 [+4.9, +12.4] * | +3.6 [−1.0, +8.1] | +1.5 [+0.3, +2.8] * | +13.5 [+3.6, +23.4] * | +13.0 [+5.9, +20.1] * | +0.7 [−2.1, +3.5] | +3.0 [+0.8, +5.2] * |
| firecrawl-search | +41.4 [+35.8, +46.9] * | +35.8 [+29.6, +41.7] * | +6.3 [+4.5, +8.2] * | +9.0 [−1.8, +18.9] | +11.4 [+4.3, +18.5] * | +5.8 [+2.9, +8.7] * | +2.0 [−0.3, +4.3] |
| deepseek | +15.0 [+10.4, +19.9] * | +12.4 [+6.8, +17.9] * | +6.0 [+4.3, +7.8] * | +11.7 [+0.9, +22.5] * | +14.6 [+7.9, +21.3] * | +4.1 [+1.5, +6.9] * | +3.3 [+0.8, +5.8] * |
| tavily-advanced | +17.3 [+13.0, +21.8] * | +16.0 [+10.7, +21.2] * | +1.9 [+0.7, +3.2] * | +2.7 [−7.2, +12.6] | +4.3 [−2.8, +11.4] | +1.6 [−1.2, +4.5] | +2.8 [+0.5, +5.3] * |
| brave-llm-context | +3.6 [+0.3, +6.8] * | +1.0 [−3.3, +5.2] | −0.4 [−1.3, +0.5] | +8.1 [−0.9, +17.1] | +3.1 [−3.5, +9.4] | −0.2 [−2.7, +2.2] | +0.8 [−1.3, +3.0] |
<!-- paired:end -->

In short: against Perplexity fast, Expand is ahead on Seal-Hard (+7.5) and FRAMES (+3.0), with no significant
difference on WebCode, SimpleQA Verified, Seal-0 or AA-Omniscience; against Perplexity web it is ahead on WebCode
groundedness (+2.3) and Seal-Hard (+6.3), with no significant difference on the other five columns. Against
every Exa configuration it is ahead on WebCode (grounded +6.8 to +10.1, correct +5.9 to +11.1), with no
significant difference on SimpleQA Verified, Seal-0, Seal-Hard and FRAMES, where Exa fast, lite and auto have
the higher point estimates on Seal-Hard and FRAMES; on AA-Omniscience it is ahead of Exa fast (+2.3), with no
significant difference from Exa lite and auto. Against Brave it is ahead only on WebCode groundedness (+3.6),
and it is ahead of Parallel, Firecrawl, DeepSeek and Tavily on most suites.

### Composite index: answer accuracy across the five datasets

One number per system: the equal-weight mean of five answer accuracies (0–100): WebCode *correct*,
SimpleQA Verified, FRAMES, Seal-Hard and AA-Omniscience. Seal-0 is left out because its questions are a subset
of Seal-Hard. WebCode enters as *correct*, not *grounded*, because groundedness rises with how much text a
provider returns; the variant with *grounded* (`runs/index-webcode-grounded.json`) also puts Expand's point
estimate first. Expand's lead over Exa auto, Brave, Exa lite and Exa fast is within the interval (not
significant); it is significant against the other seven. Only systems with a complete run on all five datasets appear.
The interval is a stratified bootstrap over tasks (10,000 resamples, seed 0), and the last column is the paired
difference against Expand on the same resampled tasks; `*` marks an interval that excludes zero. It is a
summary of these five evaluations, not a measure of overall accuracy, and it weights each dataset equally
whatever its size or spread. Regenerate with `make index`
(`runs/index.py`, `runs/index.json`).

<!-- index:begin (generated by runs/index.py) -->
| System | Index [95% CI] | WebCode | SimpleQA Verified | FRAMES | Seal-Hard | AA-Omniscience | Expand minus system [95% CI] |
|---|---:|---:|---:|---:|---:|---:|---|
| expand | 80.9 [79.3–82.5] | 87.6 | 97.6 | 75.8 | 52.8 | 90.7 | — |
| exa-auto-highlights | 80.7 [79.0–82.3] | 81.8 | 97.5 | 77.7 | 56.7 | 89.7 | +0.2 [−1.4, +1.9] |
| brave-llm-context | 80.0 [78.4–81.7] | 86.6 | 98.0 | 76.1 | 49.6 | 89.8 | +0.9 [−0.8, +2.5] |
| exa-lite-highlights | 79.4 [77.7–81.1] | 77.9 | 97.3 | 76.8 | 55.5 | 89.5 | +1.5 [−0.2, +3.2] |
| exa-fast-highlights | 79.3 [77.5–80.9] | 80.1 | 96.9 | 77.1 | 53.9 | 88.3 | +1.6 [−0.0, +3.3] |
| perplexity-web | 79.0 [77.3–80.6] | 86.0 | 96.8 | 75.5 | 46.5 | 90.2 | +1.9 [+0.6, +3.3] * |
| perplexity-fast | 78.7 [77.1–80.4] | 87.9 | 97.3 | 72.8 | 45.3 | 90.3 | +2.2 [+0.7, +3.6] * |
| parallel-fast | 76.5 [74.8–78.2] | 84.0 | 96.1 | 75.1 | 39.8 | 87.7 | +4.4 [+2.6, +6.2] * |
| parallel-turbo | 76.3 [74.7–78.0] | 80.1 | 95.9 | 75.5 | 41.3 | 88.8 | +4.6 [+2.8, +6.3] * |
| tavily-advanced | 75.6 [73.8–77.4] | 71.7 | 95.7 | 74.3 | 48.4 | 87.8 | +5.3 [+3.4, +7.2] * |
| deepseek | 72.8 [71.0–74.6] | 75.2 | 91.6 | 71.7 | 38.2 | 87.3 | +8.1 [+6.1, +10.0] * |
| firecrawl-search | 68.6 [66.8–70.5] | 51.8 | 91.3 | 70.0 | 41.3 | 88.7 | +12.3 [+10.2, +14.2] * |
<!-- index:end -->

### What was not run

Each competitor was measured at the tier named in [Systems](#systems), and every price comparison here is
against that tier. Other tiers and settings were not run: Perplexity Search with non-default settings (the web
row uses `search_type = "web"` and otherwise default settings), Parallel basic and advanced, Tavily basic,
Brave's plain web search endpoint, and Firecrawl search with page scraping (`scrapeOptions`). Benchmarks considered and not run are
in [`METHODOLOGY.md` §8](METHODOLOGY.md#8-what-was-not-run).

## Reproduce

Prerequisites: Python 3.12, [uv](https://docs.astral.sh/uv/), `git`, `make`; macOS or Linux. Run everything
from this directory (`search/`).

```sh
git clone https://github.com/expandai/benchmarks && cd benchmarks/search
make upstream          # clone exa-labs/benchmarks at 0d817af66fb6c47afb7b097b9f4e40a763b6fc3a into ./upstream
make venv              # uv sync --locked -> ./.venv (upstream installed editable)
make test              # offline regression tests; no keys, no provider calls (tiktoken fetches o200k_base once)
cp .env.example .env   # fill in the keys you have
make download          # pinned public datasets into ./.hf-cache, SHA-256 verified
make dry-run           # preflight: credentials, pins, catalog; no paid call
```

Then one target per benchmark (live, spends money). A new run's directory name hashes its resolved
configuration (endpoint, transport, overlay source), so it starts fresh rather than resuming a stored run; the
report readers reject two runs of the same system and suite, so give a separate evaluation its own
`--runs-dir <new-output-root>`. The AA runner resumes only a run with a matching manifest and settings
fingerprint; use a new directory for changed settings.

```sh
make webcode-rag               # WebCode RAG, 307 tasks, every published system      recorded $28.74
make official                  # SealQA, SimpleQA Verified, FRAMES, grader prompts   recorded $204.02
make seal-hard-official        # or one suite at a time: seal-0-official, simpleqa-verified-official, frames-official
make stirrup aa-venv           # pinned Stirrup clone + venv, then
make aa-omniscience            # AA-Omniscience public 600 on the Stirrup agent        recorded $162.45
make report paired index       # recompute harness reports and comparison tables (offline)
```

One system on one suite: `runs/run-suite.sh webcode-rag rag-perplexity-fast`,
`runs/run-suite.sh seal-hard-official rag-exa-fast-highlights` (official suites get their fixed judge and
write under `runs/official/`), or the raw CLI
`./bench run --suite <suite> --system <system> --judge-model <judge> --runs-dir <dir> -o <summary.json>`
(`./bench list` shows every suite and system; the run scripts set `BAKEOFF_LLM_TRANSPORT=openrouter`
and source `.env` through `runs/env.sh` without printing it). `make help` lists every target with its cost. Running
everything again costs about $400 at the recorded cost ($28.74 + $204.02 + $162.45, the official figure
including pilots). `make report` prints the harness tables and updates their `report.json` files;
`make paired index` rewrites the paired and index tables in this README. The other offline commands, after setup:

```sh
.venv/bin/python runs/official/assemble.py       # update runs/official/RESULTS.md
./aa-stirrup/aa report --run aa-stirrup/runs/full-600  # update AA summary (requires aa-venv)
```

The other README tables are copied from the generated reports (`report.json`, `summary.json`, `paired.json`,
`index.json`).

## Benchmarks

Details, sources and every deviation: [`METHODOLOGY.md`](METHODOLOGY.md).

| Benchmark | Designer | Dataset pin | Official protocol | Our deviation |
|---|---|---|---|---|
| WebCode RAG (307) | Exa | `upstream/data/webcode/rag.jsonl`, suite `sha256:9aa83266…+grader-v2` | one search, 10 results, gpt-5.6-luna with Exa's RAG prompt, GroundedRAGGrader on gpt-6-luna, headline grounded | none but the transport: answer and judge models through OpenRouter Chat Completions instead of the Responses API |
| SimpleQA Verified (1,000) | Google DeepMind | `google/simpleqa-verified` @ `0dc97e0d…a2dc`, `simpleqa_verified.csv` SHA-256 `b5db2115…92f5` | no tools; Appendix A grader on gpt-4.1-2025-04-14; F1 | search is a non-official setting the designers disclaim (`model-only` is the official row); judge `openai/gpt-4.1` alias via OpenRouter; neutral answer prompt; leak filter |
| SealQA Seal-0 (111), Seal-Hard (254) | Virginia Tech | `vtllms/sealqa` @ `0c298f51…2c81` (2026-09-21; the card announced a refresh for 2026-10-29, after these runs), parquet SHA-256 `381c9f86…`, `5bc6df2b…3beb` | question as prompt, high reasoning; FreshPrompt over Google or ChatGPT search; Appendix C grader on gpt-4o-mini, temperature 0; accuracy | one provider search with 10 results in a neutral prompt replaces FreshPrompt (no demos, provider order); gpt-5.6-luna answers; two notebook bugs fixed; leak filter |
| FRAMES (824) | Google | `google/frames-benchmark` @ `58d9fb63…22ef`, `test.tsv` | question + BM25 Wikipedia articles, Gemini-Pro-1.5-0514 answers and judges with the Figure 6 prompt; accuracy | gpt-4.1 judges (Gemini 1.5 retired), gpt-5.6-luna answers; provider snippets replace BM25 articles; no multi-step setting; leak filter |
| AA-Omniscience (public 600) | Artificial Analysis | `ArtificialAnalysis/AA-Omniscience-Public` @ `e4883edb…9849`, CSV SHA-256 `1e04603d…d02f` | Stirrup agent, gpt-5.6-luna medium, 25 turns, web_search (10) + web_fetch + finish, on AA's private 600; grader gpt-5.6-luna | public set; one normalised result rendering rather than provider-native JSON; our user turn, tool text and contamination rules; the paper's grader prompt |

## Systems

Every RAG row shares upstream's settings: one search with the question verbatim, `num_results = 10`, one
answer from `openai/gpt-5.6-luna`, the judge fixed per suite. Prices per 1,000 searches as recorded;
the report generators price Expand's billed searches at list price (`bakeoff/pricing.py`). Expand is priced at
its list price of $1.50 per 1,000 searches (2026-10-28). Basis and dates in [`METHODOLOGY.md` §10](METHODOLOGY.md#10-pricing-basis).

| System | Provider, tier | Request | $/1k | Price basis | Adapter |
|---|---|---|---|---|---|
| `rag-expand` | Expand Search: one result per page with an excerpt | `POST /v1/search {query, maxResults: 10}` | 1.50 | list, per request; empty searches refunded | `bakeoff/expand.py` |
| `rag-exa-fast-highlights` / `-instant-highlights` | Exa `type=fast` / `instant`, highlights | `/search`, `contents.highlights` | 7.00 / 4.00 | Exa-reported `costDollars` | upstream |
| `rag-exa-lite-highlights` / `-auto-highlights` | Exa `type=lite` / `auto`, highlights | `/search`, `contents.highlights` | 4.00 / 7.00 | Exa-reported `costDollars` (2026-10-28) | upstream adapter; the lite entry is in `bakeoff/systems.toml` |
| `rag-exa-webcode` | Exa's WebCode preset: `fast`, query highlights, `maxAgeHours: 0` live crawl | `/search` | 7.00 | reported | upstream |
| `rag-perplexity-fast` / `-web` | Perplexity Search `search_type=fast` / `web`, otherwise default settings | `POST /search` | 1.00 / 5.00 | list, per request (web: the upstream adapter's rate, read 2026-10-28) | upstream |
| `rag-parallel-turbo` / `-fast` | Parallel Search `mode=turbo` / `fast` | `/v1/search` | 1.00 | list, per request | upstream |
| `rag-firecrawl-search` | Firecrawl search, snippets, no scraping | `POST /v2/search`, `sources: ["web"]` | ≈ 1.97 | credits × $0.00099 (Standard plan) | `bakeoff/firecrawl.py` |
| `rag-deepseek` | DeepSeek Search; `summary` as evidence; query clipped to 128 chars | `POST /v1/tools/search` | 0.75 | list, per successful request | `bakeoff/deepseek.py` |
| `rag-tavily-advanced` | Tavily `search_depth=advanced` | `POST /search` | 16.00 | 2 credits × $0.008 pay-as-you-go; credits as reported | upstream |
| `rag-brave-llm-context` | Brave LLM Context (page text; clipped to 4,000 chars per result in the AA agent) | `GET /res/v1/llm/context` | 5.00 | Search plan list price | upstream |
| `rag-model-only` | no search; the bare question | — | 0 | — | `bakeoff/official_rag.py` |

The AA-Omniscience runner uses the same catalog searchers under the names without the `rag-` prefix
(`aa-stirrup/aastirrup/systems.py`). `make dry-run` names whatever key is missing.

**Transport.** All OpenAI models were called through OpenRouter. `BAKEOFF_LLM_TRANSPORT=openrouter` calls the `openai/*` answer
and judge models through OpenRouter Chat Completions with `provider.require_parameters = true`, the same model
ids, prompts, `max_output_tokens` and strict JSON schemas as upstream, and `usage.cost` recorded per call
(pilot cost check: `runs/pilot-20/README.md`). The AA agent's answerer uses OpenRouter's Responses API and its
grader Chat Completions, with the same model ids.

## Cost and wall time, as measured

The amounts below are the recorded costs summed from `runs/report.json`, `runs/official/report.json`
and `aa-stirrup/runs/*/summary.json`; Expand's search cost is its billed searches at list price
(`bakeoff/pricing.py`). AA per-question costs are over completed tasks. Wall times and concurrency are from each
run's `logs/wall.txt`, summed over passes for resumed runs. Expand's WebCode console log was not kept: its 379 s is the
span from the run directory's `config.json` `created_at` (17:28:56 UTC, 2026-10-27) to its `summary.json`
`updated_at` (17:35:15 UTC), and its concurrency is the run command in `runs/RESULTS.md`.

| Run | Spend (search + answer + judge) | Wall time |
|---|---:|---|
| WebCode RAG, 20-task pilot, 6 systems | $0.70 | 38–92 s per system, in parallel, concurrency 5 |
| WebCode RAG, 307 tasks, the 14 published rows | $28.74: Tavily $5.62, Exa fast $2.94, Exa auto $2.93, Exa webcode $2.90, Perplexity web $2.17, Brave $2.10, Exa lite $2.03, Exa instant $2.02, Expand $1.32, Parallel turbo $1.14, Firecrawl $0.95, Perplexity fast $0.95, Parallel fast $0.85, DeepSeek $0.82 | six original competitors 254–673 s each, in parallel (their concurrency is not in the logs); Parallel fast 288 s at 10; DeepSeek 956 s at 4 over four passes; Expand 379 s at 8; Tavily 615 s and Brave 495 s at 6; Exa auto 351 s, Exa lite 369 s and Perplexity web 305 s at 10 |
| Everything else under `runs/` except `official/` (supplementary single-search suites, smokes) | $35.92 (`runs/report.json` "spend" is $64.67 including the WebCode rows) | — |
| Official-grader suites (4 suites × 13 systems, pilots included) | $204.02: SimpleQA Verified $97.76, FRAMES $73.55, Seal-Hard $21.80, Seal-0 $10.91; by system Tavily $44.19, Exa fast $22.41, Exa auto $22.20, Perplexity web $17.45, Brave $17.20, Exa lite $15.86, Firecrawl $11.38, Expand $9.86, Parallel turbo $9.70, Parallel fast $9.07, DeepSeek $8.77, Perplexity fast $8.66, model-only $7.27 | Seal-0 4–13 min, Seal-Hard 5–21 min, SimpleQA Verified 6–22 min, FRAMES 8–44 min per system |
| Leak audit (8 + 2 judge calls) | < $0.01 | minutes |
| AA-Omniscience Stirrup, 20-question pilot, 6 systems | $2.01 | 13–26 s per question |
| AA-Omniscience Stirrup, 600 questions, 13 systems | $162.45: Tavily $47.08, Exa fast $18.01, Exa auto $17.17, Brave $15.41, Perplexity web $12.40, Exa lite $12.01, Firecrawl $8.99, DeepSeek $7.38, Expand $6.36, Parallel turbo $6.25, Parallel fast $5.83, Perplexity fast $4.85, model-only $0.71 | 0.17–1.03 h elapsed per system, resumes included, at concurrency 10 (5 for Expand and DeepSeek) |

## Caveats

1. **Authorship.** Expand authored this comparison and chose its protocols; Exa authored WebCode's data, grader
   and harness.
2. **Development.** Expand Search was developed with public benchmarks.
3. **Single pass, live web, laptop.** One pass per system on the live web; CIs cover task sampling only, not
   judge variance or run-to-run drift, and no repeat-run noise floor was measured. Latencies were measured from
   a laptop and include answer generation.
4. **Run windows.** Exa fast, Perplexity fast, Parallel, Firecrawl, DeepSeek and model-only ran together per suite
   on 2026-10-26/27; Expand, Tavily and Brave on 2026-10-27; Exa lite and auto, Perplexity web, Parallel fast on
   AA-Omniscience, and the remainder of the Parallel, Firecrawl and DeepSeek runs on SimpleQA Verified and FRAMES,
   on 2026-10-28 (UTC; `logs/wall.txt` in each run directory). Results may reflect web changes between windows.
5. **Concurrency differs by system**, so latency columns are not like-for-like across rows (the AA agent's
   per-search latencies, `s/search`, are the closest to a like-for-like search latency). Expand ran at 8 on
   WebCode, 3 on the official suites (`EXPAND_CONCURRENCY`) and 5 on AA; competitors at 10 on the official
   suites (DeepSeek 4; Tavily and Brave 6–8; the passes that finished Parallel, Firecrawl and DeepSeek on
   SimpleQA Verified and FRAMES at 6–8) and on AA (DeepSeek 5); Exa lite and auto and Perplexity web at 10 everywhere; on WebCode Parallel fast at 10, DeepSeek 4,
   Tavily and Brave 6, and the six original competitors at a concurrency their logs do not record.
6. **Substitute judge.** FRAMES uses its paper's Figure 6 prompt with gpt-4.1 as judge, since the original
   Gemini-Pro-1.5-0514 is retired. SimpleQA Verified's `gpt-4.1` is OpenAI's alias for the dated snapshot. All
   judges run through OpenRouter.
7. **Non-official search settings.** SimpleQA Verified is designed to run without tools; SealQA publishes a search
   setup (FreshPrompt over Google, ChatGPT search) but not a provider-neutral search-API protocol; FRAMES'
   official retrieval is BM25 over Wikipedia; AA-Omniscience's public set is not AA's private set. No row can be
   placed next to a designer's leaderboard.
8. **Leak filter.** Search engines return benchmark mirrors; the official-grader suites drop them with heuristic
   rules, which can miss paraphrases or remove legitimate sources, and count the drops; the AA agent applies its
   own rules ([`METHODOLOGY.md` §3, §7](METHODOLOGY.md)). WebCode is unfiltered; heuristic leak checks matched
   8 of 24,115 citations in the first eight WebCode runs (text level) and 5 of 18,113 in the six later runs (URL
   and title) ([`runs/leak-audit/`](runs/leak-audit/README.md)).
9. **Mixed cost bases.** Exa reports its own cost; Tavily reports credits; Perplexity, Parallel, DeepSeek,
   Expand and Brave are list prices; Firecrawl assumes the Standard plan; OpenRouter's 5.5 % fee is excluded.
10. **Query limits.** DeepSeek clips queries to 128 characters and failed two WebCode queries on every attempt;
    Tavily's adapter clips at 400 characters (11 FRAMES questions clipped) and one AA question failed with a
    Tavily HTTP 400; Brave's adapter strips punctuation and clips at 400 characters or 50 words.
11. **Datasets and prices drift.** SealQA's card announced a refresh for 2026-10-29, after these runs; every
    SealQA number is for revision `0c298f5`. Re-pin and re-run rather than mixing revisions.
12. **Stored records.** Stored records keep questions, answers, judge labels and reasoning, scores, costs,
    latencies and per-record citation counts and evidence-token totals; per-result URLs, titles and text were
    removed. Scores recompute from the stored grades; groundedness re-grading and the leak audit need a fresh
    run, which writes full records ([`runs/EXCLUDED.md`](runs/EXCLUDED.md)).
13. **Dependencies.** The main harness is locked (`uv.lock`); the AA environment pins Stirrup but not all its
    transitive dependencies (the versions used are in `aa-stirrup/runs/evidence/venv-versions.txt`).

## Adding a provider

A provider is a `Searcher` subclass, a catalog entry and a test file; the AA runner picks it up by catalog
name. [`CONTRIBUTING.md`](CONTRIBUTING.md) walks through it (adapter contract, registration, catalog,
tests, Makefile lists, pricing note), and through adding a suite and how results are stored and redacted.

## Directory layout

| Path | What |
|---|---|
| `bakeoff/` | The overlay: adapters (`expand.py`, `firecrawl.py`, `deepseek.py`), the OpenRouter transport (`openrouter.py`), suites and official graders (`suites.py`, `official_*.py`), the catalog (`systems.toml`) and `register.py`, which installs all of it into the pinned harness without editing it. `bakeoff` is the package name used in the committed run records (error tracebacks, logs, run scripts). |
| `bench` | `python -m bakeoff`: upstream's `bench` CLI with the overlay registered |
| `tests/` | Offline regression tests |
| `runs/` | Every harness run with per-task records, the report scripts (`report.py`, `official/report.py`, shared readers in `_records.py`), `paired.py`, `RESULTS.md` files and `EXCLUDED.md` |
| `aa-stirrup/` | AA-Omniscience on the pinned Stirrup agent: adapter, tests, pilot and full-600 runs |
| `METHODOLOGY.md` | Protocols, deviations, graders (verbatim prompts in Appendix A), statistics, pricing |
| `CONTRIBUTING.md` | Adding providers and suites; tests; results storage and redaction |
| `data/` | A byte-identical copy of `ArtificialAnalysis/AA-Omniscience-Public` so offline tests need no network, with its Apache-2.0 license and NOTICE |
| `tools/` | `strip_result_details.py`, `scrub_presigned_urls.py` and `scrub_paths.py`, run on new records before committing (`CONTRIBUTING.md`) |

## License and citation

MIT for everything written here ([`LICENSE`](../LICENSE)), which also lists the third-party material: the
pinned clones (exa-labs/benchmarks MIT, Stirrup MIT) and the datasets (FRAMES Apache-2.0, SimpleQA
Verified MIT, SealQA Apache-2.0, AA-Omniscience-Public Apache-2.0, whose redistributed copy carries its
license and NOTICE in [`data/LICENSE-Apache-2.0.txt`](data/LICENSE-Apache-2.0.txt)). The grader prompts quoted in `METHODOLOGY.md` remain their authors'.

```bibtex
@misc{expand-search-benchmarks-2026,
  title        = {Search-API benchmarks: Expand, Exa, Perplexity, Parallel, Firecrawl, DeepSeek, Tavily and Brave on WebCode, SimpleQA Verified, SealQA, FRAMES and AA-Omniscience},
  author       = {{Expand AI}},
  year         = {2026},
  month        = oct,
  howpublished = {\url{https://github.com/expandai/benchmarks}},
  note         = {Harness: exa-labs/benchmarks @ 0d817af; runs of 2026-10-26 through 2026-10-28 UTC}
}
```
