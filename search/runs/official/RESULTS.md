# SimpleQA Verified, SealQA and FRAMES under their official graders, 2026-10-27/28

**Official grading, retrieval protocol ours.** Each benchmark is run on its pinned dataset, graded with the designer's own grader prompt (verbatim, `bakeoff/official_prompts.py`, checked byte-for-byte against `../../METHODOLOGY.md` Appendix A by `tests/test_official.py`), the designer's judge model where it still exists, and reported with the designer's headline metric. What is ours is the retrieval step, which is one declared protocol applied identically to every search system, plus the designers' own no-search setting as a baseline. Every departure from an official protocol is listed per suite under **Deviations**.

Harness: [exa-labs/benchmarks](https://github.com/exa-labs/benchmarks) @ `0d817af` (unedited, `../../upstream/`) plus the `../../bakeoff/` overlay (`official_prompts.py`, `official_graders.py`, `official_rag.py`, `official_suites.py`, `systems.toml`). Tables come from `report.py` (`report.json` holds every number).

## Retrieval protocol (ours; identical for every search system)

1. **One search per question**, the question text verbatim as the query, `num_results = 10` (upstream `[defaults.rag]`). The provider's result order is kept. Results without a URL or evidence text are dropped (upstream `normalize_results`). DeepSeek clips queries to its documented 128-character API limit; the number of clipped questions is reported per system and suite (`query_clipped` in `result.json`).
2. **Benchmark-leak filter**, applied post-retrieval to every system (`bakeoff/official_rag.py`, `contamination_reason`): a result is dropped when its URL is on a dataset host (`huggingface.co/datasets`, `kaggle.com/`), when its URL, title or text contains a benchmark name (`sealqa`, `seal-0`, `seal-hard`, `simpleqa`, `frames-benchmark`, with `_` variants), when it contains the SealQA canary string, or when its text repeats the question verbatim (first 120 normalized characters; questions of 60+ characters only). Dropped results are counted per task by reason and per system. This filter was not optional: dataset-host pages, mostly benchmark mirrors with the gold answers, made up as much as 13 % of a system's results on SimpleQA Verified and 9 % on FRAMES, and `artificialanalysis.ai/microevals` pages reproduce FRAMES questions. Dropped results are not replaced.
3. **One answer call** to `openai/gpt-5.6-luna` (Exa's default RAG answer model) through OpenRouter Chat Completions (`BAKEOFF_LLM_TRANSPORT=openrouter`, `provider.require_parameters`), with a single **neutral user message** and no system message:

   ```
   Answer the question below. You are given web search results that may help; they can be incomplete, outdated or contradictory, so weigh them against each other and against what you already know, and give your best answer. Today's date is {current_date}.

   Search results:
   [1] Title: …
   URL: …
   Published: …          (only when the provider reports a date)
   Text: …

   Question: {question}
   ```

   The model may use the documents and its own knowledge; nothing forbids parametric knowledge and nothing forces "I don't know" (the audit found upstream's tabula-rasa prompt contradicts SimpleQA Verified's and SealQA's premise). An empty reply stays empty (graded NOT_ATTEMPTED / FALSE without a judge call). Reasoning effort: the model default for SimpleQA Verified and FRAMES; `high` for SealQA, as the paper evaluates reasoning models "under high reasoning effort settings". `max_output_tokens` unset. Temperature is not configurable on this model (the SealQA paper's "temperature 0 when configurable" therefore does not apply, as for GPT-5 in the paper).
4. **Model-only baseline** (`rag-model-only`): no search; the bare question is the entire prompt (one user message), same model and reasoning setting. This is exactly the designers' own setting for SimpleQA Verified ("without tools") and SealQA ("we fed each question as a prompt"), and FRAMES' "naive prompt".
5. Concurrency 10 per system (Expand 3, DeepSeek 4, Tavily and Brave 6–8; the 2026-10-28 passes that finished Parallel, Firecrawl and DeepSeek on SimpleQA Verified and FRAMES 6–8). Model-only, Perplexity fast, Exa fast, Parallel, Firecrawl and DeepSeek ran as separate processes per suite on 2026-10-27 01:29–02:18 UTC; Expand, Tavily and Brave on 2026-10-27 22:17 – 2026-10-28 00:22 UTC; Exa lite and auto, Perplexity web, and the remainder of Parallel, Firecrawl and DeepSeek on SimpleQA Verified and FRAMES, on 2026-10-28 (run windows below). A search is capped at 180 s and an answer call at 600 s (`asyncio.wait_for`). Resumable; only execution errors were rerun, never graded answers. Every row covers the whole suite.

Systems: `rag-model-only`, `rag-expand` (Expand Search, `POST /v1/search`), `rag-perplexity-fast`, `rag-perplexity-web` (Perplexity Search with `search_type = "web"`, otherwise default settings), `rag-exa-fast-highlights`, `rag-exa-lite-highlights`, `rag-exa-auto-highlights`, `rag-parallel-turbo`, `rag-parallel-fast`, `rag-firecrawl-search`, `rag-deepseek`, `rag-tavily-advanced`, `rag-brave-llm-context`. Request shapes and search prices are as in `../../README.md` and `../RESULTS.md`.

Columns: the headline metric with a 95 % task-bootstrap CI (percentile, 10,000 resamples, seed 0; upstream `bootstrap_mean` for per-task means, the same resampling of the F1 statistic for SimpleQA Verified); label counts; **Cit. tokens** = o200k tokens per citation after the leak filter; **Cit./task** = citations the answer model saw; **Search $/1k** = provider search cost per 1,000 questions (Exa and Tavily as reported, others list price); **Model / Judge / Total $/task**; **Latency** = search + answer, judge excluded, from a laptop; **Notes** = failures, retries, judge re-asks, clipped queries and leak-filtered results.

## Findings

1. **SimpleQA Verified mostly separates search from no search.** Under the official grader and F1, search systems score 91.4–98.0 against 40.1 for the same model without search; the top five (Brave 98.0, Expand 97.6, Exa auto 97.5, Perplexity fast 97.3, Exa lite 97.3) are within 0.7 points and ten of the twelve within 2.2, mostly inside each other's 95 % CIs. The designers expect tools to make the benchmark near trivial; the table is a check on the lift over no search and a cost/latency comparison more than a ranking. Hedging is essentially absent (attempted ≥ 99 %), so F1 ≈ accuracy.
2. **The benchmark-leak filter matters most for Perplexity and Expand.** On SimpleQA Verified, Expand returned 1,373 leak results over 1,000 questions (1,333 of them Hugging Face dataset pages, i.e. the benchmark itself with gold answers), Perplexity web 1,004 (961) and Perplexity fast 945 (905); DeepSeek 334, Exa auto 120, Firecrawl 120, Exa lite 72, Exa fast 69, Parallel fast 64, Tavily 62, Brave 41, Parallel turbo 38. On FRAMES, Expand returned 921 (749 dataset-host pages, 153 pages quoting the question verbatim, mostly `artificialanalysis.ai/microevals`), Perplexity web 897 (716 and 161) and Perplexity fast 853 (698 and 142); DeepSeek 155, Exa auto 88, Brave 86, Parallel fast 74, Tavily 60, Firecrawl 60, Exa lite 41, Exa fast 39, Parallel turbo 37. All were removed before the answer model saw them; the kept citations are ordinary sources (Wikipedia, Britannica, DOI, news). Numbers published without such a filter can include answer-key pages, as this bakeoff's earlier supplementary 97.5 % for Perplexity on SimpleQA Verified did.
3. **SealQA separates the systems.** Seal-0: Exa fast 44.1 [35.1–53.2], Exa auto 42.3, Expand 38.7, Perplexity fast 38.7, Exa lite 37.8, Perplexity web 36.0, Tavily 36.0, Brave 30.6, Firecrawl 29.7, DeepSeek 27.0, Parallel turbo and fast 25.2, model-only 9.0. Seal-Hard: Exa auto 56.7 [50.8–63.0], Exa lite 55.5, Exa fast 53.9, Expand 52.8, Brave 49.6, Tavily 48.4, Perplexity web 46.5, Perplexity fast 45.3, Parallel turbo 41.3, Firecrawl 41.3, Parallel fast 39.8, DeepSeek 38.2, model-only 26.8. Every system beats the no-search baseline; the 95 % intervals of the top six on Seal-Hard overlap. NOT_ATTEMPTED is ≈ 0 everywhere: with the neutral prompt and high reasoning the model always commits, so B (incorrect) is the complement of A.
4. **The answer prompt changes SealQA more than the grader does.** The earlier supplementary run (tabula-rasa prompt, SimpleQA-prompt grading by gpt-6-luna) gave Seal-0 Perplexity fast 39.6, Parallel turbo 16.2, Firecrawl 16.2; under the official grader with the neutral prompt they are 38.7, 25.2 and 29.7. Systems whose snippets often lacked the answer were previously forced to say "I don't know" and now answer from the model's knowledge plus whatever evidence they have.
5. **FRAMES.** Exa auto 77.7 [74.8–80.5], Exa fast 77.1, Exa lite 76.8, Brave 76.1, Expand 75.8, Perplexity web 75.5, Parallel turbo 75.5, Parallel fast 75.1, Tavily 74.3, Perplexity fast 72.8, DeepSeek 71.7, Firecrawl 70.0, model-only 66.3. The Figure 6 grader is lenient (it asks whether the gold is "present in" the response) and the gap between search systems is a few points. The paper reports 47.4% for single-step BM25 with four documents and 66.0% for multi-step retrieval with Gemini-Pro-1.5, so no row here is comparable to the paper.
6. **Query limits and evidence size.** Brave's upstream adapter strips punctuation from every query and clips at 400 characters or 50 words, so every Brave question counts as clipped (Notes column); Tavily's adapter clips at 400 characters (11 FRAMES questions); DeepSeek clips at 128 characters (97 of 254 Seal-Hard questions, 467 of 824 FRAMES questions). Tavily's citations are the longest (860–970 tokens on SimpleQA Verified and SealQA), Expand's 150–355, Brave's 190–280, Perplexity fast and web 150–275.
7. **Cost.** Including the judge, most search systems cost $0.003–0.006 per task on SealQA and FRAMES and $0.004–0.006 on SimpleQA Verified; Exa lite ≈ $0.006–0.008, Brave and Perplexity web ≈ $0.007–0.008, Exa fast and auto ≈ $0.009–0.011 and Tavily ≈ $0.019–0.021, following their search prices ($4, $5, $5, $7 and $16 per 1,000). The gpt-4.1 judge is ≈ $0.0027 (SimpleQA Verified) and ≈ $0.0015 (FRAMES) of each task; gpt-4o-mini ≈ $0.0001.

<!-- TABLES -->
<!-- generated by assemble.py; newest run directory created 2026-10-28T05:06:20.547245+00:00 -->

## SimpleQA Verified (1,000 questions) — headline F1

Suite revision `google/simpleqa-verified@0dc97e0d28d8233463e005cdc4475cc2a13ba2dc/simpleqa_verified.csv#sha256=b5db211554447635+appendix-a-gpt-4.1-official-v1`; judge `openai/gpt-4.1` (provider reported ['openai/gpt-4.1']).

| System | **F1** [95% CI] | Accuracy [95% CI] | Acc. given attempted | Attempted % | C / I / NA | Cit. tokens | Cit./task | Search $/1k | Model $/task | Judge $/task | Total $/task | Latency s mean / p90 | Notes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| model-only | **40.1 [37.0–43.1]** | 39.9 [36.8–42.9] | 40.2 | 99.2 | 399 / 593 / 8 | 0 | 0.0 | $0.00 | $0.0010 | $0.0026 | $0.0036 | 10.3 / 21.3 | 2 LLM retries |
| expand | **97.6 [96.6–98.5]** | 97.6 [96.6–98.5] | 97.6 | 100.0 | 976 / 24 / 0 | 152 | 8.6 | $1.50 | $0.0005 | $0.0030 | $0.0050 | 2.4 / 3.5 | 1373 results leak-filtered (host 1333, term 26, verbatim_question 14) |
| perplexity-fast | **97.3 [96.3–98.3]** | 97.3 [96.3–98.3] | 97.4 | 99.9 | 973 / 26 / 1 | 150 | 8.9 | $1.00 | $0.0005 | $0.0028 | $0.0044 | 2.3 / 3.5 | 4 LLM retries; 945 results leak-filtered (host 905, term 25, verbatim_question 15) |
| perplexity-web | **96.8 [95.7–97.9]** | 96.8 [95.7–97.8] | 96.9 | 99.9 | 968 / 31 / 1 | 153 | 8.9 | $5.00 | $0.0005 | $0.0029 | $0.0084 | 2.6 / 3.9 | 1004 results leak-filtered (host 961, term 28, verbatim_question 15) |
| exa-fast-highlights | **96.9 [95.8–97.9]** | 96.9 [95.8–97.9] | 96.9 | 100.0 | 969 / 31 / 0 | 271 | 9.9 | $7.00 | $0.0009 | $0.0027 | $0.0106 | 2.4 / 3.3 | 1 LLM retries; 69 results leak-filtered (host 58, term 5, verbatim_question 6) |
| exa-lite-highlights | **97.3 [96.2–98.2]** | 97.3 [96.2–98.2] | 97.3 | 100.0 | 973 / 27 / 0 | 270 | 9.9 | $4.00 | $0.0009 | $0.0028 | $0.0077 | 2.4 / 3.4 | 72 results leak-filtered (host 61, term 5, verbatim_question 6) |
| exa-auto-highlights | **97.5 [96.5–98.4]** | 97.5 [96.5–98.4] | 97.5 | 100.0 | 975 / 25 / 0 | 265 | 9.9 | $7.00 | $0.0009 | $0.0026 | $0.0105 | 3.4 / 4.6 | 120 results leak-filtered (host 109, term 4, verbatim_question 7) |
| parallel-turbo | **96.0 [94.7–97.2]** | 95.9 [94.6–97.1] | 96.2 | 99.7 | 959 / 38 / 3 | 305 | 9.8 | $1.00 | $0.0010 | $0.0027 | $0.0047 | 2.5 / 3.7 | 38 results leak-filtered (host 27, term 6, verbatim_question 5) |
| parallel-fast | **96.1 [94.9–97.3]** | 96.1 [94.8–97.3] | 96.2 | 99.9 | 961 / 38 / 1 | 244 | 9.9 | $1.00 | $0.0008 | $0.0026 | $0.0044 | 2.8 / 4.0 | 64 results leak-filtered (host 46, term 6, verbatim_question 12) |
| firecrawl-search | **91.4 [89.6–93.1]** | 91.3 [89.5–93.0] | 91.5 | 99.8 | 913 / 85 / 2 | 125 | 9.6 | $1.98 | $0.0006 | $0.0026 | $0.0052 | 3.7 / 5.9 | 120 results leak-filtered (host 115, term 2, verbatim_question 3) |
| deepseek | **91.7 [89.9–93.3]** | 91.6 [89.8–93.2] | 91.8 | 99.8 | 916 / 82 / 2 | 163 | 9.6 | $0.75 | $0.0007 | $0.0026 | $0.0041 | 3.2 / 4.8 | 169 queries clipped; 334 results leak-filtered (host 303, term 23, verbatim_question 8) |
| tavily-advanced | **95.8 [94.5–97.0]** | 95.7 [94.4–96.9] | 95.9 | 99.8 | 957 / 41 / 2 | 858 | 9.9 | $16.00 | $0.0024 | $0.0028 | $0.0212 | 5.4 / 7.1 | 62 results leak-filtered (host 57, term 1, verbatim_question 4) |
| brave-llm-context | **98.0 [97.1–98.8]** | 98.0 [97.1–98.8] | 98.0 | 100.0 | 980 / 20 / 0 | 194 | 9.9 | $5.00 | $0.0007 | $0.0024 | $0.0081 | 3.4 / 4.5 | 1000 queries clipped; 41 results leak-filtered (host 23, term 8, verbatim_question 10) |

## SealQA Seal-0 (111 questions) — accuracy

Suite revision `vtllms/sealqa@0c298f519c871579c75920189b3858da29fe2c81/seal-0.parquet#sha256=381c9f86039c1657+appendix-c-gpt-4o-mini-official-v1`; judge `openai/gpt-4o-mini` (provider reported ['openai/gpt-4o-mini']).

| System | **Accuracy** (A) [95% CI] | B % | C % | A / B / C | Cit. tokens | Cit./task | Search $/1k | Model $/task | Judge $/task | Total $/task | Latency s mean / p90 | Notes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| model-only | **9.0 [4.5–14.4]** | 91.0 | 0.0 | 10 / 101 / 0 | 0 | 0.0 | $0.00 | $0.0043 | $0.0001 | $0.0044 | 33.1 / 76.7 | — |
| expand | **38.7 [29.7–47.7]** | 61.3 | 0.0 | 43 / 68 / 0 | 355 | 9.9 | $1.50 | $0.0030 | $0.0001 | $0.0046 | 16.4 / 46.1 | 11 results leak-filtered (host 11) |
| perplexity-fast | **38.7 [29.7–47.7]** | 61.3 | 0.0 | 43 / 68 / 0 | 264 | 9.8 | $1.00 | $0.0031 | $0.0001 | $0.0043 | 20.9 / 46.2 | 23 results leak-filtered (host 23) |
| perplexity-web | **36.0 [27.0–45.0]** | 64.0 | 0.0 | 40 / 71 / 0 | 274 | 9.9 | $5.00 | $0.0029 | $0.0001 | $0.0080 | 18.4 / 53.0 | 9 results leak-filtered (host 9) |
| exa-fast-highlights | **44.1 [35.1–53.2]** | 55.9 | 0.0 | 49 / 62 / 0 | 524 | 10.0 | $7.00 | $0.0029 | $0.0001 | $0.0100 | 13.7 / 24.2 | 2 results leak-filtered (verbatim_question 2) |
| exa-lite-highlights | **37.8 [28.8–46.8]** | 62.2 | 0.0 | 42 / 69 / 0 | 533 | 10.0 | $4.00 | $0.0028 | $0.0001 | $0.0069 | 12.6 / 21.6 | 4 results leak-filtered (host 2, verbatim_question 2) |
| exa-auto-highlights | **42.3 [33.3–51.4]** | 57.7 | 0.0 | 47 / 64 / 0 | 525 | 10.0 | $7.00 | $0.0028 | $0.0001 | $0.0099 | 14.4 / 27.1 | 3 results leak-filtered (host 1, verbatim_question 2) |
| parallel-turbo | **25.2 [17.1–33.3]** | 74.8 | 0.0 | 28 / 83 / 0 | 452 | 9.7 | $1.00 | $0.0038 | $0.0001 | $0.0049 | 21.8 / 54.8 | 1 results leak-filtered (host 1) |
| parallel-fast | **25.2 [17.1–33.3]** | 74.8 | 0.0 | 28 / 83 / 0 | 241 | 10.0 | $1.00 | $0.0036 | $0.0001 | $0.0047 | 23.6 / 62.6 | 4 results leak-filtered (host 2, verbatim_question 2) |
| firecrawl-search | **29.7 [21.6–38.7]** | 70.3 | 0.0 | 33 / 78 / 0 | 669 | 10.0 | $1.98 | $0.0049 | $0.0001 | $0.0070 | 25.9 / 71.5 | 1 results leak-filtered (host 1) |
| deepseek | **27.0 [18.9–36.0]** | 72.1 | 0.9 | 30 / 80 / 1 | 366 | 9.6 | $0.75 | $0.0042 | $0.0001 | $0.0051 | 26.3 / 72.8 | 37 queries clipped; 40 results leak-filtered (host 39, term 1) |
| tavily-advanced | **36.0 [27.0–45.0]** | 64.0 | 0.0 | 40 / 71 / 0 | 967 | 10.0 | $16.00 | $0.0044 | $0.0001 | $0.0206 | 17.6 / 31.9 | 1 recovered on retry; 4 results leak-filtered (host 1, verbatim_question 3) |
| brave-llm-context | **30.6 [21.6–39.6]** | 69.4 | 0.0 | 34 / 77 / 0 | 282 | 9.9 | $5.00 | $0.0029 | $0.0001 | $0.0080 | 16.4 / 37.3 | 111 queries clipped; 8 results leak-filtered (host 6, term 1, verbatim_question 1) |

## SealQA Seal-Hard (254 questions) — accuracy

Suite revision `vtllms/sealqa@0c298f519c871579c75920189b3858da29fe2c81/seal-hard.parquet#sha256=5bc6df2bf5012782+appendix-c-gpt-4o-mini-official-v1`; judge `openai/gpt-4o-mini` (provider reported ['openai/gpt-4o-mini']).

| System | **Accuracy** (A) [95% CI] | B % | C % | A / B / C | Cit. tokens | Cit./task | Search $/1k | Model $/task | Judge $/task | Total $/task | Latency s mean / p90 | Notes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| model-only | **26.8 [21.7–32.3]** | 72.8 | 0.4 | 68 / 185 / 1 | 0 | 0.0 | $0.00 | $0.0034 | $0.0001 | $0.0036 | 27.8 / 66.4 | — |
| expand | **52.8 [46.5–58.7]** | 47.2 | 0.0 | 134 / 120 / 0 | 335 | 9.9 | $1.50 | $0.0021 | $0.0001 | $0.0038 | 13.0 / 21.8 | 16 results leak-filtered (host 14, term 1, verbatim_question 1) |
| perplexity-fast | **45.3 [39.4–51.6]** | 54.7 | 0.0 | 115 / 139 / 0 | 267 | 9.9 | $1.00 | $0.0023 | $0.0001 | $0.0034 | 15.4 / 36.7 | 1 LLM retries; 29 results leak-filtered (host 27, term 1, verbatim_question 1) |
| perplexity-web | **46.5 [40.2–52.8]** | 53.5 | 0.0 | 118 / 136 / 0 | 274 | 9.9 | $5.00 | $0.0022 | $0.0001 | $0.0073 | 14.6 / 35.1 | 14 results leak-filtered (host 12, term 1, verbatim_question 1) |
| exa-fast-highlights | **53.9 [48.0–59.8]** | 46.1 | 0.0 | 137 / 117 / 0 | 510 | 10.0 | $7.00 | $0.0018 | $0.0001 | $0.0089 | 10.0 / 19.4 | 7 results leak-filtered (host 2, verbatim_question 5) |
| exa-lite-highlights | **55.5 [49.6–61.4]** | 44.5 | 0.0 | 141 / 113 / 0 | 519 | 10.0 | $4.00 | $0.0019 | $0.0001 | $0.0060 | 10.3 / 17.4 | 8 results leak-filtered (host 3, verbatim_question 5) |
| exa-auto-highlights | **56.7 [50.8–63.0]** | 43.3 | 0.0 | 144 / 110 / 0 | 510 | 10.0 | $7.00 | $0.0018 | $0.0001 | $0.0089 | 10.7 / 18.0 | 8 results leak-filtered (host 1, term 1, verbatim_question 6) |
| parallel-turbo | **41.3 [35.4–47.6]** | 58.7 | 0.0 | 105 / 149 / 0 | 440 | 9.7 | $1.00 | $0.0033 | $0.0001 | $0.0044 | 18.3 / 48.7 | 2 LLM retries; 5 results leak-filtered (host 3, verbatim_question 2) |
| parallel-fast | **39.8 [33.9–46.1]** | 60.2 | 0.0 | 101 / 153 / 0 | 237 | 10.0 | $1.00 | $0.0028 | $0.0001 | $0.0039 | 18.0 / 45.5 | 1 LLM retries; 10 results leak-filtered (host 6, verbatim_question 4) |
| firecrawl-search | **41.3 [35.4–47.6]** | 58.7 | 0.0 | 105 / 149 / 0 | 654 | 9.9 | $1.97 | $0.0035 | $0.0001 | $0.0055 | 20.4 / 53.6 | 2 LLM retries; 5 results leak-filtered (host 3, term 1, verbatim_question 1) |
| deepseek | **38.2 [32.3–44.1]** | 61.8 | 0.0 | 97 / 157 / 0 | 358 | 9.8 | $0.75 | $0.0029 | $0.0001 | $0.0038 | 18.2 / 45.9 | 6 recovered on retry; 1 LLM retries; 97 queries clipped; 50 results leak-filtered (host 49, term 1) |
| tavily-advanced | **48.4 [42.1–54.7]** | 51.6 | 0.0 | 123 / 131 / 0 | 929 | 10.0 | $16.00 | $0.0028 | $0.0001 | $0.0189 | 13.0 / 25.4 | 9 results leak-filtered (host 3, term 1, verbatim_question 5) |
| brave-llm-context | **49.6 [43.7–55.9]** | 50.4 | 0.0 | 126 / 128 / 0 | 264 | 10.0 | $5.00 | $0.0023 | $0.0001 | $0.0074 | 13.7 / 28.1 | 254 queries clipped; 6 results leak-filtered (host 4, term 1, verbatim_question 1) |

## FRAMES (824 questions) — accuracy

Suite revision `58d9fb6330f3ab1316d1eca12e5e8ef23dcc22ef+fig6-gpt-4.1-official-v1`; judge `openai/gpt-4.1` (provider reported ['openai/gpt-4.1']).

| System | **Accuracy** [95% CI] | TRUE / FALSE | Cit. tokens | Cit./task | Search $/1k | Model $/task | Judge $/task | Total $/task | Latency s mean / p90 | Notes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| model-only | **66.3 [63.0–69.5]** | 546 / 278 | 0 | 0.0 | $0.00 | $0.0012 | $0.0015 | $0.0027 | 12.1 / 28.8 | 3 LLM retries |
| expand | **75.8 [72.9–78.8]** | 625 / 199 | 214 | 8.9 | $1.50 | $0.0012 | $0.0015 | $0.0041 | 7.3 / 14.2 | 5 LLM retries; 921 results leak-filtered (host 749, term 19, verbatim_question 153) |
| perplexity-fast | **72.8 [69.7–75.8]** | 600 / 224 | 180 | 8.9 | $1.00 | $0.0011 | $0.0015 | $0.0036 | 7.1 / 13.7 | 5 LLM retries; 853 results leak-filtered (host 698, term 13, verbatim_question 142) |
| perplexity-web | **75.5 [72.5–78.4]** | 622 / 202 | 184 | 8.9 | $5.00 | $0.0012 | $0.0015 | $0.0076 | 8.0 / 15.3 | 897 results leak-filtered (host 716, term 20, verbatim_question 161) |
| exa-fast-highlights | **77.1 [74.2–79.9]** | 635 / 189 | 440 | 9.9 | $7.00 | $0.0017 | $0.0015 | $0.0102 | 6.3 / 11.8 | 5 LLM retries; 39 results leak-filtered (host 20, term 2, verbatim_question 17) |
| exa-lite-highlights | **76.8 [73.9–79.6]** | 633 / 191 | 444 | 9.9 | $4.00 | $0.0017 | $0.0015 | $0.0072 | 6.3 / 10.4 | 41 results leak-filtered (host 21, term 2, verbatim_question 18) |
| exa-auto-highlights | **77.7 [74.8–80.5]** | 640 / 184 | 439 | 9.9 | $7.00 | $0.0017 | $0.0015 | $0.0102 | 7.3 / 11.6 | 88 results leak-filtered (host 59, term 2, verbatim_question 27) |
| parallel-turbo | **75.5 [72.6–78.4]** | 622 / 202 | 362 | 9.9 | $1.00 | $0.0016 | $0.0015 | $0.0041 | 7.1 / 12.4 | 37 results leak-filtered (host 12, verbatim_question 25) |
| parallel-fast | **75.1 [72.1–78.0]** | 619 / 205 | 237 | 9.9 | $1.00 | $0.0014 | $0.0015 | $0.0038 | 7.7 / 14.4 | 74 results leak-filtered (host 29, term 1, verbatim_question 44) |
| firecrawl-search | **70.0 [66.7–73.2]** | 577 / 247 | 191 | 9.5 | $1.95 | $0.0015 | $0.0015 | $0.0049 | 10.8 / 22.7 | 4 queries clipped; 60 results leak-filtered (host 46, verbatim_question 14) |
| deepseek | **71.7 [68.6–74.8]** | 591 / 233 | 279 | 9.8 | $0.75 | $0.0016 | $0.0015 | $0.0038 | 8.6 / 19.3 | 467 queries clipped; 155 results leak-filtered (host 112, term 3, verbatim_question 40) |
| tavily-advanced | **74.3 [71.2–77.2]** | 612 / 212 | 436 | 9.9 | $16.00 | $0.0018 | $0.0015 | $0.0193 | 9.7 / 15.9 | 11 queries clipped; 60 results leak-filtered (host 40, term 1, verbatim_question 19) |
| brave-llm-context | **76.1 [73.2–79.0]** | 627 / 197 | 197 | 9.9 | $5.00 | $0.0012 | $0.0015 | $0.0077 | 7.8 / 13.6 | 9 LLM retries; 823 queries clipped; 86 results leak-filtered (host 45, term 7, verbatim_question 34) |

## Coverage, spend and run windows

Recorded costs of the committed official-suite run directories, pilots included (search + answer model + judge): **$204.02**. By suite: simpleqa-verified $97.76, seal-0 $10.91, seal-hard $21.80, frames $73.55. By system: tavily-advanced $44.19, exa-fast-highlights $22.41, exa-auto-highlights $22.20, perplexity-web $17.45, brave-llm-context $17.20, exa-lite-highlights $15.86, firecrawl-search $11.38, expand $9.86, parallel-turbo $9.70, parallel-fast $9.07, deepseek $8.77, perplexity-fast $8.66, model-only $7.27.

Run windows (UTC, from `logs/wall.txt`; one line per pass, stamped when the pass ended):

The `exit=143` passes are processes stopped at 02:03 UTC on 2026-10-27 when the run was paused; the same run directories were resumed on 2026-10-28 with their graded tasks kept, so every task has one stored answer and one grade.

- `simpleqa-verified-official`:
  - 2026-10-27T02:03:11Z rag-deepseek limit=all pass=1 exit=143 wall_s=275 concurrency=4 judge=openai/gpt-4.1
  - 2026-10-27T02:03:11Z rag-firecrawl-search limit=all pass=1 exit=143 wall_s=275 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-27T02:03:11Z rag-parallel-turbo limit=all pass=1 exit=143 wall_s=275 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-27T02:03:11Z rag-parallel-fast limit=all pass=1 exit=143 wall_s=275 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-27T02:04:54Z rag-perplexity-fast limit=all pass=1 exit=0 wall_s=378 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-27T02:04:55Z rag-exa-fast-highlights limit=all pass=1 exit=0 wall_s=379 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-27T02:18:19Z rag-model-only limit=all pass=1 exit=0 wall_s=1183 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-27T22:52:10Z rag-brave-llm-context limit=all pass=1 exit=1 wall_s=159 concurrency=6 judge=openai/gpt-4.1
  - 2026-10-27T22:53:57Z rag-brave-llm-context limit=all pass=2 exit=1 wall_s=47 concurrency=6 judge=openai/gpt-4.1
  - 2026-10-27T22:56:44Z rag-brave-llm-context limit=all pass=3 exit=1 wall_s=47 concurrency=6 judge=openai/gpt-4.1
  - 2026-10-27T23:08:37Z rag-tavily-advanced limit=all pass=1 exit=0 wall_s=1146 concurrency=6 judge=openai/gpt-4.1
  - 2026-10-27T23:37:58Z rag-expand limit=all pass=1 exit=0 wall_s=1316 concurrency=3 judge=openai/gpt-4.1
  - 2026-10-27T23:39:33Z rag-brave-llm-context limit=all pass=1 exit=0 wall_s=691 concurrency=6 judge=openai/gpt-4.1
  - 2026-10-28T01:01:30Z rag-parallel-turbo limit=all pass=1 exit=0 wall_s=208 concurrency=6 judge=openai/gpt-4.1
  - 2026-10-28T01:02:10Z rag-parallel-fast limit=all pass=1 exit=0 wall_s=248 concurrency=6 judge=openai/gpt-4.1
  - 2026-10-28T01:04:56Z rag-firecrawl-search limit=all pass=1 exit=0 wall_s=414 concurrency=6 judge=openai/gpt-4.1
  - 2026-10-28T01:12:47Z rag-deepseek limit=all pass=1 exit=0 wall_s=885 concurrency=4 judge=openai/gpt-4.1
  - 2026-10-28T03:23:37Z rag-exa-auto-highlights limit=all pass=1 exit=1 wall_s=14 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-28T03:23:37Z rag-exa-lite-highlights limit=all pass=1 exit=1 wall_s=14 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-28T03:24:51Z rag-exa-auto-highlights limit=all pass=2 exit=1 wall_s=14 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-28T03:24:51Z rag-exa-lite-highlights limit=all pass=2 exit=1 wall_s=14 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-28T03:37:26Z rag-exa-lite-highlights limit=all pass=1 exit=0 wall_s=386 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-28T03:39:02Z rag-exa-auto-highlights limit=all pass=1 exit=0 wall_s=482 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-28T05:06:19Z rag-perplexity-web limit=all pass=1 exit=0 wall_s=409 concurrency=10 judge=openai/gpt-4.1
- `seal-0-official`:
  - 2026-10-27T01:34:00Z rag-exa-fast-highlights limit=all pass=1 exit=0 wall_s=243 concurrency=10 judge=openai/gpt-4o-mini
  - 2026-10-27T01:34:29Z rag-parallel-turbo limit=all pass=1 exit=0 wall_s=272 concurrency=10 judge=openai/gpt-4o-mini
  - 2026-10-27T01:35:13Z rag-perplexity-fast limit=all pass=1 exit=0 wall_s=316 concurrency=10 judge=openai/gpt-4o-mini
  - 2026-10-27T01:35:38Z rag-parallel-fast limit=all pass=1 exit=0 wall_s=341 concurrency=10 judge=openai/gpt-4o-mini
  - 2026-10-27T01:35:39Z rag-firecrawl-search limit=all pass=1 exit=0 wall_s=342 concurrency=10 judge=openai/gpt-4o-mini
  - 2026-10-27T01:37:14Z rag-model-only limit=all pass=1 exit=0 wall_s=437 concurrency=10 judge=openai/gpt-4o-mini
  - 2026-10-27T01:43:03Z rag-deepseek limit=all pass=1 exit=0 wall_s=786 concurrency=4 judge=openai/gpt-4o-mini
  - 2026-10-27T22:21:42Z rag-tavily-advanced limit=all pass=1 exit=1 wall_s=257 concurrency=8 judge=openai/gpt-4o-mini
  - 2026-10-27T22:22:28Z rag-brave-llm-context limit=all pass=1 exit=0 wall_s=303 concurrency=8 judge=openai/gpt-4o-mini
  - 2026-10-27T22:24:12Z rag-tavily-advanced limit=all pass=2 exit=1 wall_s=89 concurrency=8 judge=openai/gpt-4o-mini
  - 2026-10-27T22:27:41Z rag-tavily-advanced limit=all pass=3 exit=1 wall_s=89 concurrency=8 judge=openai/gpt-4o-mini
  - 2026-10-27T22:38:55Z rag-brave-llm-context limit=all pass=1 exit=0 wall_s=1 concurrency=6 judge=openai/gpt-4o-mini
  - 2026-10-27T22:41:09Z rag-tavily-advanced limit=all pass=1 exit=0 wall_s=135 concurrency=6 judge=openai/gpt-4o-mini
  - 2026-10-27T22:55:51Z rag-expand limit=all pass=1 exit=0 wall_s=701 concurrency=3 judge=openai/gpt-4o-mini
  - 2026-10-28T03:17:09Z rag-exa-auto-highlights limit=all pass=1 exit=0 wall_s=214 concurrency=10 judge=openai/gpt-4o-mini
  - 2026-10-28T03:17:53Z rag-exa-lite-highlights limit=all pass=1 exit=0 wall_s=258 concurrency=10 judge=openai/gpt-4o-mini
  - 2026-10-28T04:40:43Z rag-perplexity-web limit=all pass=1 exit=0 wall_s=256 concurrency=10 judge=openai/gpt-4o-mini
- `seal-hard-official`:
  - 2026-10-27T01:35:05Z rag-exa-fast-highlights limit=all pass=1 exit=0 wall_s=308 concurrency=10 judge=openai/gpt-4o-mini
  - 2026-10-27T01:38:17Z rag-perplexity-fast limit=all pass=1 exit=0 wall_s=500 concurrency=10 judge=openai/gpt-4o-mini
  - 2026-10-27T01:38:44Z rag-parallel-turbo limit=all pass=1 exit=0 wall_s=527 concurrency=10 judge=openai/gpt-4o-mini
  - 2026-10-27T01:38:52Z rag-parallel-fast limit=all pass=1 exit=0 wall_s=535 concurrency=10 judge=openai/gpt-4o-mini
  - 2026-10-27T01:40:19Z rag-firecrawl-search limit=all pass=1 exit=0 wall_s=622 concurrency=10 judge=openai/gpt-4o-mini
  - 2026-10-27T01:43:16Z rag-model-only limit=all pass=1 exit=0 wall_s=799 concurrency=10 judge=openai/gpt-4o-mini
  - 2026-10-27T01:50:53Z rag-deepseek limit=all pass=1 exit=1 wall_s=1256 concurrency=4 judge=openai/gpt-4o-mini
  - 2026-10-27T01:57:07Z rag-deepseek limit=all pass=1 exit=0 wall_s=18 concurrency=4 judge=openai/gpt-4o-mini
  - 2026-10-27T22:35:30Z rag-tavily-advanced limit=all pass=1 exit=1 wall_s=469 concurrency=8 judge=openai/gpt-4o-mini
  - 2026-10-27T22:36:15Z rag-brave-llm-context limit=all pass=1 exit=0 wall_s=514 concurrency=8 judge=openai/gpt-4o-mini
  - 2026-10-27T22:41:11Z rag-brave-llm-context limit=all pass=1 exit=0 wall_s=2 concurrency=6 judge=openai/gpt-4o-mini
  - 2026-10-27T22:49:31Z rag-tavily-advanced limit=all pass=1 exit=0 wall_s=502 concurrency=6 judge=openai/gpt-4o-mini
  - 2026-10-27T23:16:02Z rag-expand limit=all pass=1 exit=0 wall_s=1211 concurrency=3 judge=openai/gpt-4o-mini
  - 2026-10-28T03:23:07Z rag-exa-lite-highlights limit=all pass=1 exit=0 wall_s=314 concurrency=10 judge=openai/gpt-4o-mini
  - 2026-10-28T03:23:23Z rag-exa-auto-highlights limit=all pass=1 exit=0 wall_s=330 concurrency=10 judge=openai/gpt-4o-mini
  - 2026-10-28T04:40:50Z rag-perplexity-web limit=all pass=1 exit=1 wall_s=7 concurrency=10 judge=openai/gpt-4o-mini
  - 2026-10-28T04:41:56Z rag-perplexity-web limit=all pass=2 exit=1 wall_s=6 concurrency=10 judge=openai/gpt-4o-mini
  - 2026-10-28T04:44:04Z rag-perplexity-web limit=all pass=3 exit=1 wall_s=8 concurrency=10 judge=openai/gpt-4o-mini
  - 2026-10-28T04:59:30Z rag-perplexity-web limit=all pass=1 exit=0 wall_s=503 concurrency=10 judge=openai/gpt-4o-mini
- `frames-official`:
  - 2026-10-27T02:03:11Z rag-deepseek limit=all pass=1 exit=143 wall_s=275 concurrency=4 judge=openai/gpt-4.1
  - 2026-10-27T02:03:11Z rag-firecrawl-search limit=all pass=1 exit=143 wall_s=275 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-27T02:03:11Z rag-parallel-turbo limit=all pass=1 exit=143 wall_s=275 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-27T02:03:11Z rag-parallel-fast limit=all pass=1 exit=143 wall_s=275 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-27T02:10:28Z rag-exa-fast-highlights limit=all pass=1 exit=0 wall_s=712 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-27T02:11:15Z rag-perplexity-fast limit=all pass=1 exit=0 wall_s=759 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-27T02:18:01Z rag-model-only limit=all pass=1 exit=0 wall_s=1165 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-27T23:09:22Z rag-brave-llm-context limit=all pass=1 exit=1 wall_s=45 concurrency=6 judge=openai/gpt-4.1
  - 2026-10-27T23:11:07Z rag-brave-llm-context limit=all pass=2 exit=1 wall_s=45 concurrency=6 judge=openai/gpt-4.1
  - 2026-10-27T23:13:51Z rag-brave-llm-context limit=all pass=3 exit=1 wall_s=44 concurrency=6 judge=openai/gpt-4.1
  - 2026-10-27T23:35:47Z rag-tavily-advanced limit=all pass=1 exit=0 wall_s=1630 concurrency=6 judge=openai/gpt-4.1
  - 2026-10-28T00:03:16Z rag-brave-llm-context limit=all pass=1 exit=0 wall_s=1398 concurrency=6 judge=openai/gpt-4.1
  - 2026-10-28T00:21:58Z rag-expand limit=all pass=1 exit=0 wall_s=2640 concurrency=3 judge=openai/gpt-4.1
  - 2026-10-28T01:26:18Z rag-parallel-turbo limit=all pass=1 exit=0 wall_s=811 concurrency=6 judge=openai/gpt-4.1
  - 2026-10-28T01:27:27Z rag-parallel-fast limit=all pass=1 exit=0 wall_s=880 concurrency=6 judge=openai/gpt-4.1
  - 2026-10-28T03:13:07Z rag-firecrawl-search limit=all pass=1 exit=0 wall_s=233 concurrency=8 judge=openai/gpt-4.1
  - 2026-10-28T03:19:07Z rag-deepseek limit=all pass=1 exit=0 wall_s=593 concurrency=6 judge=openai/gpt-4.1
  - 2026-10-28T03:50:41Z rag-exa-lite-highlights limit=all pass=1 exit=0 wall_s=698 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-28T03:52:12Z rag-exa-auto-highlights limit=all pass=1 exit=0 wall_s=790 concurrency=10 judge=openai/gpt-4.1
  - 2026-10-28T05:20:24Z rag-perplexity-web limit=all pass=1 exit=0 wall_s=845 concurrency=10 judge=openai/gpt-4.1

# Official protocols and deviations, per suite

## SimpleQA Verified (1,000 questions)

**Official protocol** (arXiv:2509.07968v2 §4, Appendix A; dataset card): the question is the prompt; "standard API parameters and without tools"; grader `gpt-4.1-2025-04-14` with the Appendix A prompt (ranges for numeric golds, hedging CORRECT only if the response commits to one correct candidate, soft refusals NOT_ATTEMPTED), reply A/B/C; headline **F1** = harmonic mean of accuracy and accuracy-given-attempted; also accuracy, accuracy given attempted, attempted %, hedged %.

**What we ran.** Grader: Appendix A verbatim as one user message to `openai/gpt-4.1` on OpenRouter (default temperature, `max_tokens` 16,000), anchored letter parse, full-word label as fallback, unparseable replies re-asked up to 3 times. Metrics per simple-evals. Answers: the retrieval protocol above; `rag-model-only` is the designers' own setting.

**Deviations.**
1. *Search is a non-official setting.* The paper says tools make the benchmark "near perfect" and the card says they "defeat its purpose". Every search row is a community setting; the `model-only` row is the official one.
2. *Judge id.* OpenRouter lists no `openai/gpt-4.1-2025-04-14`; `openai/gpt-4.1` was used (OpenAI's alias for the 2025-04-14 snapshot) and the response's `model` field, `openai/gpt-4.1`, is recorded per grade. The judge temperature is not stated in the paper and was left at the API default.
3. *Prompt source.* The prompt is the paper's Appendix A; the Kaggle starter notebook is behind a login wall and was not read, so the exact blank-line layout follows simple-evals (`../../METHODOLOGY.md` A.2 note). Letter parsing is anchored at the start of the reply rather than simple-evals' first-capital-letter regex.
4. *Transport.* Judge and answer model through OpenRouter Chat Completions rather than OpenAI direct.
5. *Blank answers* are NOT_ATTEMPTED without a judge call.
6. *Dataset revision* `0dc97e0` (2026-03-09) post-dates the paper and the Kaggle leaderboard launch ("Edit to fix an error in dataset").

## SealQA Seal-0 (111) and Seal-Hard (254)

**Official protocol** (arXiv:2506.01062v4 §2, §3.1.1, Appendix C; dataset card; Colab grading notebook): each question fed as the prompt, temperature 0 when configurable, high reasoning effort for reasoning models; search either ChatGPT built-in search (agentic) or FreshPrompt/self-ask injection of Google results; grader `gpt-4o-mini`, temperature 0, `max_tokens` 1024, Appendix C prompt, reply A/B/C; accuracy = share graded A; single sample.

**What we ran.** Grader: the Colab `GRADER_TEMPLATE` verbatim as one user message to `openai/gpt-4o-mini`, temperature 0, `max_tokens` 1024. Answers: the retrieval protocol above with `reasoning_effort = high`; `rag-model-only` is the paper's "w/o search" column setting. Dataset at the pre-10-29 revision `0c298f5` (2026-09-21).

**Deviations.**
1. *Search regime.* A single provider search with 10 results injected into the prompt replaces FreshPrompt over Google. FreshPrompt's unpublished few-shot demonstrations are not used, evidence is kept in provider rank order rather than FreshPrompt's oldest-to-newest date sort, and the evidence fields are title/URL/date/text rather than FreshPrompt's (source, date, title, snippet, highlight). The paper names no search API, so no row here is comparable to its Table 1 (which used ChatGPT built-in search and a different answer model).
2. *Answer model.* `gpt-5.6-luna` (default for the bakeoff) instead of the paper's models; temperature is not configurable on it, so the paper's temperature-0 rule does not apply, as for GPT-5 in the paper.
3. *Notebook bugs fixed.* (a) The published `grading()` indexes `raw_response['output']` on a `str` and raises; our pipeline grades directly from the reply text. (b) The notebook's `re.search(r"(A|B|C)")` takes the first capital letter anywhere, so a reply of `CORRECT` would be parsed as C = NOT_ATTEMPTED; our parse anchors the letter at the start of the reply, accepts the full-word label, and re-asks (up to 3 times) instead of defaulting to C. The number of re-asks per system is in the Notes column.
4. *Leak filter.* Not part of the official protocol; applied identically to every system (counts in Notes).
5. *Transport.* Judge and answer model through OpenRouter Chat Completions.
6. *Blank answers* are NOT_ATTEMPTED without a judge call.
7. *Dataset refresh.* The card announces a revision on 2026-10-29; numbers here are for revision `0c298f5` only.

## FRAMES (824 questions)

**Official protocol** (arXiv:2409.12941v3 §3, Figure 6): single-step = question + top-n BM25 Wikipedia articles (n = 2, 4) in one call, or multi-step Algorithm 1 over the same BM25 index; answer and judge model Gemini-Pro-1.5-0514; judge prompt Figure 6 with system "You are a helpful assistant.", free text ending in `"Decision:" ("TRUE" or "FALSE")`; accuracy = share TRUE.

**What we ran.** Grader: Figure 6 verbatim with the paper's system message, free text, last `Decision:` value parsed (regex tolerant of the quoted/bold forms the output format itself asks for), re-asked up to 3 times when absent. Answers: the retrieval protocol above (single-step, provider results instead of BM25 Wikipedia articles, n = 10 snippets); `rag-model-only` is the paper's "naive prompt".

**Deviations.**
1. *Judge model.* Gemini-Pro-1.5-0514 is retired (not on OpenRouter; Google's 1.5 line deprecated). Substitute: `openai/gpt-4.1`, the model Perplexity's public `search_evals` harness uses with the same Figure 6 prompt. Default temperature.
2. *Retrieval.* One provider search with 10 snippets replaces BM25 over a Wikipedia dump with 2 or 4 whole articles; evidence per citation is hundreds of tokens, not whole articles (Cit. tokens column). No multi-step (Algorithm 1) setting was run.
3. *Answer model and prompt.* `gpt-5.6-luna` with the neutral prompt above; the paper's answer prompts are described in prose only.
4. *Leak filter and transport* as above. *Blank answers* are FALSE without a judge call.
5. *Dataset* at the paper's revision `58d9fb6`; no refresh since.

## Pins and exact commands

| Suite | Dataset @ revision | File SHA-256 | Rows | Judge | Suite revision string |
|---|---|---|---:|---|---|
| simpleqa-verified-official | HF `google/simpleqa-verified` @ `0dc97e0d28d8233463e005cdc4475cc2a13ba2dc` (2026-03-09), `simpleqa_verified.csv` | `b5db2115…92f5` | 1,000 | `openai/gpt-4.1` | `…+appendix-a-gpt-4.1-official-v1` |
| seal-0-official | HF `vtllms/sealqa` @ `0c298f519c871579c75920189b3858da29fe2c81` (2026-09-21, "update 092126"; next refresh 2026-10-29), `seal-0.parquet` | `381c9f86…` | 111 | `openai/gpt-4o-mini` | `…+appendix-c-gpt-4o-mini-official-v1` |
| seal-hard-official | same revision, `seal-hard.parquet` | `5bc6df2b…3beb` | 254 | `openai/gpt-4o-mini` | `…+appendix-c-gpt-4o-mini-official-v1` |
| frames-official | HF `google/frames-benchmark` @ `58d9fb6330f3ab1316d1eca12e5e8ef23dcc22ef` (2024-10-15), `test.tsv` | upstream pin | 824 | `openai/gpt-4.1` | `58d9fb6…+fig6-gpt-4.1-official-v1` |

```sh
cd benchmarks/search   # the bakeoff root
export EXA_BENCH_VENV="$PWD/.venv"   # created by `make venv` (README)
"$EXA_BENCH_VENV/bin/python" -m pytest -q -p no:cacheprovider          # offline tests (official: tests/test_official.py)

# Preflight (no paid calls) for every suite × system:
DRY_RUN=1 runs/run-suite.sh seal-0-official rag-model-only rag-perplexity-fast … rag-expand rag-tavily-advanced rag-brave-llm-context

# Pilots (10 questions, perplexity-fast + model-only), then the full runs; resumable:
LIMIT=10 PASSES=2 runs/run-suite.sh <suite> rag-model-only rag-perplexity-fast
runs/run-suite.sh seal-0-official & runs/run-suite.sh seal-hard-official & wait
runs/run-suite.sh simpleqa-verified-official & runs/run-suite.sh frames-official & wait
# Later windows: Expand (concurrency 3), Tavily and Brave (6–8), then Exa lite and auto, on every suite:
for s in seal-0-official seal-hard-official simpleqa-verified-official frames-official; do
  CONCURRENCY=6 runs/run-suite.sh $s rag-tavily-advanced rag-brave-llm-context; runs/run-suite.sh $s rag-expand
done

"$EXA_BENCH_VENV/bin/python" runs/official/report.py          # tables above, runs/official/report.json
"$EXA_BENCH_VENV/bin/python" runs/official/report.py --spend  # spend only
```

The stored runs were made with `runs/official/run-official.sh`, now a wrapper around `runs/run-suite.sh`, which for an official suite sources the bakeoff-root `.env` through `runs/env.sh` (never printed), sets `BAKEOFF_LLM_TRANSPORT=openrouter`, `HF_HOME=.hf-cache`, `HF_HUB_DISABLE_XET=1`, passes `--judge-model` per suite (the suite refuses any other value, so a run directory's label can never disagree with the grader that produced it), writes under `runs/official/<suite>/`, and reruns a pass after 60/120/240 s while tasks ended in execution errors.
