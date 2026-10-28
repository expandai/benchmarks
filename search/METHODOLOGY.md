# Methodology

How every number in this repository was produced: the official protocol of each benchmark with its
source, what was actually run, every deviation and why, the graders (model id, prompt source), the
benchmark-leak filter, the statistics, and the pricing basis per provider. The tables themselves are in
[`README.md`](README.md) and, with every column, in `runs/RESULTS.md`, `runs/official/RESULTS.md`
and `aa-stirrup/runs/full-600/summary.md`.

Appendix A holds the grader prompts verbatim; `tests/test_official.py` checks the
code against it byte for byte.

## 1. Shared setup

| Item | Value |
|---|---|
| Harness | [exa-labs/benchmarks](https://github.com/exa-labs/benchmarks) at commit `0d817af66fb6c47afb7b097b9f4e40a763b6fc3a` (2026-10-12), cloned by `make upstream`, installed editable, never edited. The overlay (`bakeoff/`) registers adapters, suites and graders in-process (`bakeoff/register.py`) and refuses to replace any upstream entry. |
| Agent (AA-Omniscience) | [ArtificialAnalysis/stirrup](https://github.com/ArtificialAnalysis/stirrup) at `c092cee80ce09cd1dfb93aef053296a9ecd9dbb6` (v0.2.1), cloned by `make stirrup`. |
| Answer model (RAG suites) | `openai/gpt-5.6-luna`, upstream's `[defaults.rag]` model, default reasoning effort (SealQA: `high`, see §4). `num_results = 10` for every system. |
| Judges | WebCode `openai/gpt-6-luna` (upstream `JUDGE_DEFAULT`); SimpleQA Verified and FRAMES `openai/gpt-4.1`; SealQA `openai/gpt-4o-mini`; AA-Omniscience `openai/gpt-5.6-luna` (medium). Each official suite refuses any other `--judge-model`. |
| Transport | Every model call requests an `openai/*` model through OpenRouter (`BAKEOFF_LLM_TRANSPORT=openrouter`, `bakeoff/openrouter.py`): Chat Completions with `provider.require_parameters = true` (the pilot's calls reported `"provider": "OpenAI"`), the same model ids, prompts, `max_output_tokens` and strict JSON schemas as upstream, `usage.cost` recorded per call. Upstream itself uses the OpenAI Responses API. Except where stated (SealQA `high`, AA `medium`), reasoning effort is unset on both routes; OpenAI does not document whether the two APIs share a default effort. Measured costs matched upstream's pricing table to the cent (`runs/pilot-20/README.md`). The Stirrup answerer uses OpenRouter's Responses endpoint with encrypted reasoning passed back each turn; its grader uses Chat Completions. |
| Query | The question text verbatim, one search per task. DeepSeek clips queries to its documented 128 characters (count reported per run as `query_clipped`); Firecrawl and Tavily clip at 500 / 400 characters at a word boundary; Brave strips punctuation and clips at 400 characters or 50 words (upstream adapters). No WebCode query exceeds 90 characters. |
| Evidence | Each provider's evidence is passed as the provider returns it; its length is not normalised (see the Cit. tokens column; in the AA agent Brave LLM Context is clipped, §7). |
| Concurrency and resumption | As recorded in each run's `logs/wall.txt` and the run commands. Expand: 8 on WebCode (`CONCURRENCY=8`, `runs/RESULTS.md` "Commands"), 3 on the official suites (`EXPAND_CONCURRENCY`, default 3), 5 on AA-Omniscience (`aastirrup/systems.py`). Competitors: official suites 10 (DeepSeek 4; Tavily and Brave 6–8; the 2026-10-28 passes that finished Parallel, Firecrawl and DeepSeek on SimpleQA Verified and FRAMES 6–8; Exa lite and auto, Perplexity web 10); AA-Omniscience 10 (DeepSeek 5); WebCode Parallel fast 10, DeepSeek 4, Tavily and Brave 6, Exa lite and auto and Perplexity web 10, and the six original competitors through `runs/pilot-20/run-pilot.sh`, whose log line does not record the concurrency. Latency columns are therefore not like-for-like across systems; the AA agent's per-search latencies (`s/search`, measured inside `web_search`) are the closest to a like-for-like search latency. Systems ran in several windows between 2026-10-26 and 2026-10-28 UTC (`logs/wall.txt` in each run directory; Expand's WebCode run, whose console log was not kept, from its run directory's timestamps), so results may reflect web changes between windows. A task with a `grade.json` is never rerun; a pass that ends in execution errors is followed by another after 60/120/240 s. Searches are capped at 180 s and answers at 600 s (`bakeoff/official_rag.py`). |
| Single pass | Every table is one pass per system; no repeat-run noise floor was measured. |

## 2. WebCode RAG (Exa, 307 tasks): the designer's protocol, run as published

**Official protocol.** Exa's own harness and README at `0d817af`: `bench run --suite webcode-rag --system rag-exa-webcode`, i.e. `kind = rag`, one search, `num_results = 10`, answer by `openai/gpt-5.6-luna` with upstream's `RAG_SYSTEM_PROMPT` / `RAG_USER_PROMPT` (the "tabula rasa" prompt: no parametric knowledge, "I don't know" when the citations do not suffice), judge `openai/gpt-6-luna`, grader `GroundedRAGGrader` (correctness and groundedness, strict JSON, `max_output_tokens = 16000`), dataset `upstream/data/webcode/rag.jsonl` (307 tasks; suite revision `sha256:9aa83266452b…+grader-v2`). Headline metric **grounded** (groundedness ≠ UNGROUNDED; PARTIAL counts as grounded), secondary **correct** (correctness = CORRECT), plus `citation_precision` and `avg_citation_tokens`. Exa's published table (Exa 79.4, Brave 76.3, Parallel 75.3, Perplexity 64.6) is described upstream as historical, with earlier adapters and no CIs.

**What we ran.** Exactly that, for every system, same pin, hashes, prompts, models and grader. The stored `config.json` files use upstream's format; new runs also record the model transport, endpoint and overlay digest in `config.json` and the run hash (`bakeoff/provenance.py`).

**Deviations.**
1. *Transport* (§1). Chat Completions through OpenRouter instead of the Responses API.
2. Systems beyond `rag-exa-webcode` (`rag-exa-fast-highlights`, `rag-exa-instant-highlights`, `rag-exa-lite-highlights`, `rag-exa-auto-highlights`, Perplexity fast and web, Parallel, Firecrawl, DeepSeek, Expand, Tavily, Brave) are additions, not deviations; `rag-exa-webcode` is the like-for-like row.
3. Comparisons are against the Exa rows run here, not against Exa's published 79.4.

**Leak audit (`runs/leak-audit/`).** Of 24,115 citations across the first eight WebCode runs (Exa ×3, Parallel ×2, Perplexity fast, DeepSeek, Firecrawl), 8 (0.03 %) matched the audit's heuristic rules (the question as a page slug, the Hugging Face dataset-host rule firing on licence text and agent logs); re-judging those 8 tasks with the citations removed changes no system's groundedness by more than 0.3 pp. WebCode is reported unfiltered. Nothing was retrieved from the `exa-labs/benchmarks` repository, a WebCode mirror or artificialanalysis.ai. The six later runs (Expand, Tavily, Brave, Perplexity web, Exa lite, Exa auto) were checked at URL and title level only (the rules that need no citation text: the official `host` and `term` rules and the WebCode host, name and query-slug rules; `runs/leak-audit/url_title_check.py`): 5 of 18,113 citations fired (Expand 1 of 3,026, a Hugging Face dataset page hosting ffmpeg documentation; Tavily 2 of 3,070, `facebook.com/fb-answers` pages whose slug is the query, the same pages Firecrawl returned; Perplexity web 2 of 2,807, a Hugging Face repository holding a Python environment and a blog post with "webcode" in its URL; Brave, Exa lite and Exa auto 0 of 3,070 each).

**Authorship.** Exa wrote the dataset, the grader and the harness, and WebCode was built from documentation pages Exa's index may have crawled. Every system uses the same grader.

## 3. Retrieval protocol for the official-grader suites (ours; identical for every search system)

SimpleQA Verified, SealQA and FRAMES publish a grader and a metric but no provider-neutral search-API protocol (§§4–6): SimpleQA Verified is run without tools, SealQA's search setup is FreshPrompt over Google or ChatGPT search, and FRAMES retrieves with BM25 over Wikipedia. The retrieval step is therefore one declared protocol, applied identically to every system, with the designers' own no-search setting as a baseline (`bakeoff/official_rag.py`, `bakeoff/official_suites.py`):

1. **One search** per question, the question verbatim, `num_results = 10`, provider order kept, results without a URL or evidence dropped (upstream `normalize_results`).
2. **Benchmark-leak filter** (`contamination_reason`), post-retrieval, every system: a result is dropped when its URL is on a dataset host (`huggingface.co/datasets`, `kaggle.com/`); when its URL, title or text contains a benchmark name (`sealqa`, `seal-0`, `seal-hard`, `simpleqa`, `frames-benchmark`, with `_` variants); when it contains the suite's canary string; or when its text repeats the question verbatim (first 120 normalised characters; questions of 60+ characters only). Each task's record counts its drops by reason (`filtered_results_by_reason`), and each table's Notes column sums them. The filter was not optional: dataset-host pages, mostly benchmark mirrors with the gold answers, made up as much as 13 % of a system's results on SimpleQA Verified and 9 % on FRAMES (dataset-host drops over results returned, from the stored `filtered_results_by_reason`); dropped results are not replaced. Over the full runs it removed, on SimpleQA Verified (1,000 questions) and FRAMES (824), 1,373 and 921 results from Expand (1,333 and 749 of them dataset-host pages), 1,004 and 897 from Perplexity web (961 and 716 dataset-host pages), 945 and 853 from Perplexity fast (905 and 698), DeepSeek 334 and 155, Exa auto 120 and 88, Firecrawl 120 and 60, Exa lite 72 and 41, Exa fast 69 and 39, Parallel fast 64 and 74, Tavily 62 and 60, Brave 41 and 86, Parallel turbo 38 and 37 (counts per reason in each table's Notes column). The earlier supplementary 97.5 % Perplexity result (`runs/simpleqa-verified/`) included answer-key mirrors and is not a clean comparison. The rules are heuristic and can miss paraphrases or remove legitimate sources.
3. **One answer call** to `openai/gpt-5.6-luna`, a single neutral user message and no system message:

   ```
   Answer the question below. You are given web search results that may help; they can be incomplete, outdated or contradictory, so weigh them against each other and against what you already know, and give your best answer. Today's date is {current_date}.

   Search results:
   [1] Title: …
   URL: …
   Published: …          (only when the provider reports a date)
   Text: …

   Question: {question}
   ```

   The model may use the documents and its own knowledge; nothing forbids parametric knowledge and nothing forces "I don't know" (upstream's tabula-rasa prompt contradicts SimpleQA Verified's and SealQA's premise, and FRAMES' own baseline is parametric). An empty reply stays empty and is graded NOT_ATTEMPTED / FALSE without a judge call. Reasoning effort: model default for SimpleQA Verified and FRAMES, `high` for SealQA (the paper evaluates reasoning models "under high reasoning effort settings"). Temperature is not configurable on this model.
4. **Model-only baseline** (`rag-model-only`): no search; the bare question is the whole prompt, same model and reasoning setting. This is the designers' own setting for SimpleQA Verified ("without tools") and SealQA ("we fed each question as a prompt"), and FRAMES' "naive prompt".
5. **Grading** by the designer's prompt verbatim (Appendix A), the designer's judge model where it still exists, letter/decision parsing anchored at the start of the reply (full-word label accepted as fallback), unparseable replies re-asked up to three times (count in Notes). The designer's headline metric is the headline here.

## 4. SimpleQA Verified (Google DeepMind, 1,000)

Sources: Haas et al., "SimpleQA Verified: A Reliable Factuality Benchmark to Measure Parametric Knowledge", arXiv:2509.07968v2; dataset `google/simpleqa-verified` @ `0dc97e0d28d8233463e005cdc4475cc2a13ba2dc` (2026-03-09, "Edit to fix an error in dataset"), `simpleqa_verified.csv`, SHA-256 `b5db21155444763543fe31b67e7cf28ce2bb225742a5b889421c5f182e2f92f5`, 1,000 rows, MIT; Kaggle leaderboard and starter notebook (login-walled, not read).

**Official protocol** (§4, Appendix A, dataset card): the question is the prompt; "standard API parameters and without tools"; grader `gpt-4.1-2025-04-14` with the Appendix A prompt (explicit acceptable ranges for numeric golds, hedging CORRECT only if the response commits to one correct candidate, soft refusals NOT_ATTEMPTED), reply A/B/C; headline **F1** = harmonic mean of accuracy and accuracy-given-attempted; also accuracy, accuracy given attempted, attempted %, hedged %. The designers say tools make the benchmark "near perfect" and the card says they "defeat its purpose".

**What we ran.** Grader: Appendix A verbatim (Appendix A.2 below) as one user message to `openai/gpt-4.1` through OpenRouter, default temperature, `max_tokens` 16,000, anchored letter parse; metrics per simple-evals (`accuracy_given_attempted = correct / (correct + incorrect)`, `f1 = 2 · acc_att · acc / (acc_att + acc)`); CIs by resampling the F1 statistic over tasks. Answers: the §3 protocol; `rag-model-only` is the designers' own setting. Suite revision `…+appendix-a-gpt-4.1-official-v1`.

**Deviations.**
1. *Search is a non-official setting.* Every search row is a community setting the designers disclaim; the `model-only` row is the official one. The table is mainly a check that search lifts the no-search baseline and a cost/latency comparison: search systems score 91.4–98.0 F1 (`runs/official/report.json`); the top five (Brave 98.0 to Exa lite 97.3) are within 0.7 points and ten of the twelve within 2.2, against 40.1 without search.
2. *Judge id.* OpenRouter lists no `openai/gpt-4.1-2025-04-14`; `openai/gpt-4.1` (OpenAI's alias for that snapshot) was used and the response's `model` field is recorded per grade. Judge temperature is not stated in the paper and was left at the API default.
3. *Prompt source.* The paper's Appendix A; the Kaggle notebook was not read, so the exact blank-line layout follows simple-evals. Letter parsing is anchored rather than simple-evals' first-capital-letter regex.
4. *Transport* (§1). *Blank answers* are NOT_ATTEMPTED without a judge call.
5. *Dataset revision* `0dc97e0` post-dates the paper and the Kaggle leaderboard launch.

## 5. SealQA Seal-0 (111) and Seal-Hard (254) (Virginia Tech)
**Seal-0 and Seal-Hard overlap.** Seal-0 (111 questions) is a subset of Seal-Hard (254); `tests/test_suites.py::test_seal_0_is_a_subset_of_seal_hard` checks it against the pinned files. Both are reported because the SealQA authors and the vendors who cite SealQA report both, but they are not independent: a combined score across these benchmarks must use Seal-Hard only.


Sources: Pham et al., "SealQA: Raising the Bar for Reasoning in Search-Augmented Language Models", arXiv:2506.01062v4 (ICLR 2026); dataset `vtllms/sealqa` @ `0c298f519c871579c75920189b3858da29fe2c81` (2026-09-21, "update 092126"), `seal-0.parquet` SHA-256 `381c9f86039c16570ee8d74ecbc3e687b553b21f7ebd7828a3d6a9e8f4705e7c` (111 rows), `seal-hard.parquet` SHA-256 `5bc6df2bf5012782675cbfc36a991d264320e4edcb332db60da2119b61383beb` (254 rows; Seal-0 ⊂ Seal-Hard, asserted by a test), Apache-2.0; the grading Colab linked from the card (`GRADER_TEMPLATE`, notebook metadata 2025-07-17). No GitHub repository exists.

**Official protocol** (§2, §3.1.1, Appendix C, card, Colab): each question fed as the prompt, temperature 0 when configurable, high reasoning effort for reasoning models; search either ChatGPT's built-in search (agentic, for OpenAI models) or FreshPrompt / self-ask injection of **Google** results (results count, prompt text and FreshPrompt parameters unstated); grader `gpt-4o-mini`, temperature 0, `max_tokens` 1024, Appendix C prompt (adds an internal-consistency rule, drops the numeric last-significant-figure and name-typo rules of the original SimpleQA prompt), reply A/B/C; **accuracy** = share graded A; single sample.

**What we ran.** Grader: the Colab `GRADER_TEMPLATE` verbatim (Appendix A.3) as one user message to `openai/gpt-4o-mini`, temperature 0, `max_tokens` 1024. Answers: the §3 protocol with `reasoning_effort = high`; `rag-model-only` is the paper's "w/o search" setting. Dataset at `0c298f5`. Suite revisions `…+appendix-c-gpt-4o-mini-official-v1`.

**Deviations.**
1. *Search regime.* One provider search with 10 results injected in the neutral prompt replaces FreshPrompt over Google: no few-shot demonstrations (SealQA does not publish them), provider rank order rather than FreshPrompt's oldest-to-newest date sort, evidence fields title/URL/date/text rather than (source, date, title, snippet, highlight). The paper names no search API, so no row is comparable to its Table 1.
2. *Answer model.* `gpt-5.6-luna` instead of the paper's models; temperature is not configurable on it (the paper's temperature-0 rule did not apply to GPT-5 either).
3. *Notebook bugs fixed.* (a) The published `grading()` indexes `raw_response['output']` on a `str` and raises; grading here works from the reply text. (b) The notebook's `re.search(r"(A|B|C)")` takes the first capital letter anywhere, so a reply of `CORRECT` would parse as C = NOT_ATTEMPTED; the parse here is anchored, accepts the full word, and re-asks instead of defaulting.
4. *Leak filter* (§3), not part of the official protocol, applied to every system.
5. *Transport* (§1). *Blank answers* NOT_ATTEMPTED without a judge call.
6. *Dataset refresh.* The card commits to regular answer updates and announced a refresh for 2026-10-29, after these runs; every SealQA number is for revision `0c298f5` (2026-09-21). Re-pin and re-run rather than mixing revisions.

## 6. FRAMES (Google, 824)

Sources: Krishna et al., "Fact, Fetch, and Reason", arXiv:2409.12941v3 (NAACL 2025); dataset `google/frames-benchmark` @ `58d9fb6330f3ab1316d1eca12e5e8ef23dcc22ef` (2024-10-15, upstream's pin), `test.tsv`, 824 rows, Apache-2.0. No evaluation code was released and no GitHub repository exists.

**Official protocol** (§3, Figure 6): single-step = question + top-n BM25 Wikipedia articles (n = 2, 4) in one call, or multi-step Algorithm 1 (k = 5 queries × n = 5 rounds × 10 documents over the same BM25 index); answer and judge model Gemini-Pro-1.5-0514; judge prompt Figure 6 with system message "You are a helpful assistant.", free text ending in `"Decision:" ("TRUE" or "FALSE")`; **accuracy** = share TRUE. The authors used BM25 over Wikipedia "instead of making direct calls to an online search engine", so any search-API run is a community adaptation.

**What we ran.** Grader: Figure 6 verbatim (Appendix A.1) with the paper's system message, free text, the last `Decision:` value parsed (tolerant of the quoted/bold forms the format itself asks for), re-asked when absent. Answers: the §3 protocol (single-step, provider results instead of BM25 articles, n = 10 snippets); `rag-model-only` is the paper's "naive prompt". Suite revision `58d9fb6…+fig6-gpt-4.1-official-v1`.

**Deviations.**
1. *Judge model.* Gemini-Pro-1.5-0514 is retired (not on OpenRouter; Google's 1.5 line deprecated). Substitute `openai/gpt-4.1`, the model Perplexity's public `search_evals` harness uses with the same Figure 6 prompt; default temperature.
2. *Retrieval.* One provider search with 10 snippets (hundreds of tokens each) replaces BM25 over a Wikipedia dump with 2 or 4 whole articles. No multi-step (Algorithm 1) setting was run.
3. *Answer model and prompt.* `gpt-5.6-luna` with the neutral prompt; the paper describes its answer prompts in prose only.
4. *Leak filter* and *transport* as above. *Blank answers* are FALSE without a judge call.

The Figure 6 grader is lenient (it asks whether the gold is "present in" the response); the paper reports 47.4% for single-step BM25 with four documents and 66.0% for multi-step retrieval with Gemini-Pro-1.5, so no row here is comparable to the paper.

## 7. AA-Omniscience (Artificial Analysis, public 600) on AA's Stirrup agent

Sources: Jackson et al., "AA-Omniscience", arXiv:2511.13029v1; dataset `ArtificialAnalysis/AA-Omniscience-Public` @ `e4883edbb9f5ccf2b2a8fdc6fb65e01a58e99849` (2026-08-24), `AA-Omniscience_dataset_public.csv`, SHA-256 `1e04603dafa3bd0d16d8151f07a5eb74c43d90c3a85d2fca120da2359174d02f`, 600 rows, Apache-2.0 (a byte-identical copy is at `data/`); AA's search-API methodology page, launch article (2026-08-18) and leaderboard, read on 2026-10-26 (URLs, read dates and Wayback Machine copies in `aa-stirrup/runs/evidence/README.md`).

**Official protocol.** Paper (no tools): the A.1 answer prompt, single pass, grader with four labels (CORRECT, INCORRECT, PARTIAL_ANSWER, NOT_ATTEMPTED), Omniscience Index = 100·(c − i)/N, accuracy = c/N, hallucination rate = i/(i + p + a). AA's **Search Index** (with search): the Stirrup agent with GPT-5.6 Luna (medium), tools `web_search` (10 results, "provider-native payload … standardized to snippets"), `web_fetch` (text-only extractor, 15 s, only URLs a search returned) and `finish`, 25 turns, zero if `finish` is never called, provider errors retried until success, contamination filtered inside both tools (rules unpublished), on AA's **private** 600, accuracy only; grader GPT-5.6 Luna (medium) with an unpublished rubric.

**What we ran** (`aa-stirrup/`, every choice listed in its README). Stirrup `c092cee`, `max_turns = 25`, Stirrup's default system prompt plus the paper's A.1 prompt (`{topic}` = CSV `domain`, `{category}` = CSV `topic`), our user turn, `web_search` rendering every provider through one normalised `SearchResult` as Stirrup's Brave XML (a test checks byte-equality with Stirrup's Brave executor), `web_fetch` = Stirrup's trafilatura fetcher with AA's 15 s deadline and returned-URL restriction, `finish(answer)`, our contamination filter (rules below; 12–1,444 search rows dropped per search system over 600 questions, Perplexity web 1,444, Expand 1,160, Perplexity fast 684, Exa fast 509, Exa auto 479, Exa lite 419, the rest 12–116, `aa-stirrup/runs/full-600/summary.json` `filtered_results`), no `finish` in 25 turns = NOT_ATTEMPTED without a grader call; answer and grader `openai/gpt-5.6-luna` (medium), with the answerer using OpenRouter Responses and encrypted reasoning passback and the grader using Chat Completions; grader prompt = paper Appendix A.2 verbatim (SHA-256 pinned by a test); scoring per §2.4. Sample: all 600 public questions, domain-balanced order seeded 20261026.

**Deviations from AA** (everything AA leaves unpublished is a choice of ours): public set, not AA's private 600 (the public set has been online since 2025-11, so pages quoting it exist); one normalised rendering rather than each provider's native JSON (the largest known difference); our user turn, tool descriptions and contamination rules; the domain/topic mapping rather than the dataset card's domain/subtopic mapping; the paper's grader prompt rather than AA's current rubric; measured rather than derived model time. Brave LLM Context descriptions are clipped to 4,000 characters per result (it returns page text, not snippets); other providers' evidence is passed unclipped; Stirrup's 40,000-character cap on a rendered search applies to all systems. None of these numbers can be placed next to AA's leaderboard; on 600 questions the 95 % interval is about ±2.5 points on accuracy and ±5 on OI.

**The AA filter is not the official suites' filter.** Official-grader suites (§3, `bakeoff/official_rag.py`): a search result is dropped when its URL is on a dataset host (`huggingface.co/datasets`, `kaggle.com/`), when its URL, title or text contains a SealQA, SimpleQA or FRAMES benchmark name, when it contains the suite's canary, or when its text repeats the first 120 normalised characters of a question of 60+ characters; fetched pages do not exist in that protocol. AA agent (`aa-stirrup/aastirrup/tools.py`): a search row is dropped when its URL matches `artificialanalysis.ai`, `aa-omniscience` (any separator), arXiv `2511.13029` or `huggingface.co/datasets/ArtificialAnalysis`, or its title or snippet mentions AA-Omniscience or contains the whole normalised question (questions of 40+ characters); a fetched page with the same signals comes back as a failed fetch; there is no generic dataset-host rule. Each stored run was filtered with the rules in the code when it ran; the per-task records count the drops by rule (`filtered_results_by_reason`; AA: `filtered_results`).

## 8. What was not run

HLE-Diamond (CAIS) was considered and not run.

Each competitor was run at the tier listed in the README's systems table, and every price comparison is
against that tier by name. Other tiers and settings were not run: Perplexity Search with non-default settings
(`rag-perplexity-web` uses `search_type = "web"` and otherwise default settings), Parallel basic and advanced,
Tavily basic, Brave's plain web search endpoint, and Firecrawl search with page scraping (`scrapeOptions`).

## 9. Statistics

- **Confidence intervals** are two-sided 95 % percentile bootstrap intervals over tasks (upstream `harness.statistics.bootstrap_mean`: 10,000 resamples, seed 0), computed over every task of the suite with failures as zero (next bullet). SimpleQA Verified's F1 is resampled as a statistic over the same task draws. They cover task sampling only, not judge variance or run-to-run drift (§1, single pass).
- **Terminal failures count as zero on the full intended denominator.** A task that still ends in an execution error after every retry pass scores 0 (WebCode grounded and correct; SealQA and FRAMES accuracy) or NOT_ATTEMPTED (SimpleQA Verified F1; AA-Omniscience OI and accuracy), and the headline and its CI are over every task of the suite. Two published rows have such failures: DeepSeek on WebCode, `rag_006` and `rag_231` (DeepSeek returned HTTP 500 on every attempt in all four passes), 80.8 grounded and 75.2 correct over 307 (81.3 and 75.7 over the 305 graded); and Tavily on AA-Omniscience, `aao-054` (Tavily HTTP 400 on every attempt), accuracy 87.8 and OI 76.8 over 600 (88.0 and 77.0 over the 599 graded). The graded-only figures are kept in `report.json` / `summary.json` and footnoted in the tables.
- **Paired differences** (README, `runs/paired.py`, `runs/paired.json`): for Expand against each competitor on each suite, the per-task score difference (WebCode grounded and correct; the official suites' per-task accuracy, `score` in `grade.json`, which on SimpleQA Verified is within 0.2 points of F1 because ≥ 99.5 % of questions are attempted; AA-Omniscience `grade == "CORRECT"`), failures as zero, averaged over the tasks of the suite, with a 95 % paired percentile bootstrap over tasks (10,000 resamples, seed 0; upstream `bootstrap_mean` applied to the differences). Every published run is complete and paired. Each interval is a separate comparison, not adjusted for multiple testing (of 81, about four would exclude zero by chance alone); an interval that includes zero means the difference is not significant, not that the systems are equal.
- **Omniscience** metrics follow the paper's §2.4 formulas without domain weighting.
- **Composite index** (README, `runs/index.py`, `runs/index.json`): the equal-weight mean of five per-dataset answer accuracies on a 0–100 scale (WebCode `correct`, SimpleQA Verified per-task accuracy, FRAMES, Seal-Hard, AA-Omniscience accuracy), failures as zero, for systems with a complete run on all five. Seal-0 is excluded as a subset of Seal-Hard. WebCode enters as `correct` because `grounded` rises with evidence length; `runs/index-webcode-grounded.json` is the variant with `grounded` and also puts Expand's point estimate first. Expand's lead over Exa auto, Brave, Exa lite and Exa fast is within the interval (not significant); it is significant against the other seven. The interval is a stratified percentile bootstrap that resamples tasks within each dataset independently (10,000 resamples, seed 0); differences against Expand reuse the same resampled task indices for both systems. Equal weights give each dataset the same say regardless of its size (254 to 1,000 tasks) or the spread of its scores, so datasets that separate systems more (Seal-Hard, WebCode) move the index more than saturated ones (SimpleQA Verified). The index was defined after the per-dataset results were in; it summarises these evaluations and is not an accuracy figure.

`make report` prints the harness tables and updates their JSON summaries; `make paired index` rewrites the README's paired and index tables. `runs/official/assemble.py` refreshes `runs/official/RESULTS.md`, and `./aa-stirrup/aa report --run aa-stirrup/runs/full-600` refreshes the AA summary after AA setup. The other README tables are copied from the generated reports (`report.json`, `summary.json`, `paired.json`, `index.json`).

## 10. Pricing basis

Search prices are per 1,000 searches as the harness recorded them on 2026-10-26/27, except Expand's: the report generators price Expand's billed searches (non-zero stored cost) at list price (`bakeoff/pricing.py`). Expand is priced at its list price of $1.50 per 1,000 searches (2026-10-28). Model and judge costs are OpenRouter's `usage.cost` per call (OpenAI list price; OpenRouter's 5.5 % credit-purchase fee is not included). AA per-question means are over completed tasks. Latency is search + answer from a laptop, judge excluded; AA wall time includes grading.

| Provider | System(s) | Basis | $/1k searches | Source, date |
|---|---|---|---:|---|
| Exa | `rag-exa-fast-highlights`, `rag-exa-instant-highlights`, `rag-exa-webcode`, `rag-exa-lite-highlights`, `rag-exa-auto-highlights` | Exa-reported `costDollars` per response | 7.00 fast / 4.00 instant (10 results), 2026-10-26; 4.00 lite / 7.00 auto, 2026-10-28 | response field; exa.ai pricing |
| Perplexity | `rag-perplexity-fast`, `rag-perplexity-web` | list price per request (`search_type=fast`; `search_type=web` with otherwise default settings); no cost field in the response | 1.00 fast; 5.00 web | upstream `harness/searchers/perplexity.py`, 2026-10-26 (fast) and 2026-10-28 (web) |
| Parallel | `rag-parallel-turbo`, `rag-parallel-fast` | list price per request (≤ 10 results; $1/1k per result beyond 10) | 1.00 | upstream adapter; parallel.ai pricing, 2026-10-26 |
| Firecrawl | `rag-firecrawl-search` | `creditsUsed` × $0.00099 (Standard plan, $99 per 100,000 credits; 2 credits per 10 results) | ≈ 1.97 | firecrawl.dev/pricing, 2026-10-26 |
| DeepSeek | `rag-deepseek` | $0.75 per 1,000 successful (non-empty) requests; `count` does not change the price; DeepSeek's 2026-11-01 billing change concerns server-side tool calls, not standalone Search API requests | 0.75 (0.74 measured, empty searches unbilled) | api-docs.deepseek.com/guides/search, 2026-10-26 |
| Expand | `rag-expand`, AA `expand` | $0.0015 per search, list price; a search that finds nothing is refunded | 1.50 | expand.ai, 2026-10-28 |
| Tavily | `rag-tavily-advanced`, AA `tavily-advanced` | credits reported per response × $0.008 pay-as-you-go; advanced depth = 2 credits | 16.00 | tavily.com/pricing, docs.tavily.com/documentation/api-credits, 2026-10-27 |
| Brave | `rag-brave-llm-context`, AA `brave-llm-context` | Search plan list price per request (LLM Context endpoint included; no cost field) | 5.00 | brave.com/search/api, 2026-10-27 |
| OpenAI via OpenRouter | answer and judge models | `usage.cost` per call: gpt-5.6-luna $0.20 / $1.20 per 1M input / output tokens; gpt-6-luna $0.10 / $0.50; gpt-4.1 $2 / $8; gpt-4o-mini $0.15 / $0.60 | per task $0.001–0.006 | OpenRouter model list, 2026-10-26 |

## 11. What is stored, and what was removed

Every per-task record is committed under `runs/` and `aa-stirrup/runs/`. Stored records keep questions, answers, judge labels and reasoning, scores, costs, latencies and per-record citation counts and evidence-token totals; per-result URLs, titles and text were removed, the same for every system and suite (`tools/strip_result_details.py`). Scores recompute from the stored grades; groundedness re-grading and the leak audit need a fresh run, which writes full records. `tools/scrub_presigned_urls.py` and `tools/scrub_paths.py` remove signed-URL parameters and machine paths. `runs/EXCLUDED.md` has the field-by-field inventory.

## 12. Caveats, in one place

1. **Authorship.** Expand authored this comparison and chose its protocols; Exa authored WebCode's data, grader and harness (§2).
2. **Development.** Expand Search was developed with public benchmarks.
3. **Single pass, live web.** One pass per system; CIs cover task sampling only; no repeat-run noise floor was measured (§1). Latencies were measured from a laptop at concurrency that differs by system (§1).
4. **Expand.** Every Expand row (`rag-expand`, AA `expand`) is Expand Search, `POST /v1/search` with `{query, maxResults: 10}`, at concurrency 8 (WebCode), 3 (official suites, `EXPAND_CONCURRENCY`) and 5 (AA), in the windows recorded in each run's `logs/wall.txt` (WebCode: the run directory's timestamps; its console log was not kept).
5. **Substitute judge**: gpt-4.1 for FRAMES' retired Gemini-Pro-1.5-0514, with the paper's Figure 6 prompt; SimpleQA Verified's `gpt-4.1` is OpenAI's alias for the dated snapshot. All judges run through OpenRouter.
6. **Non-official search settings.** SimpleQA Verified is run without tools by its designers; SealQA publishes a search setup but not a provider-neutral search-API protocol; FRAMES' official retrieval is BM25 over Wikipedia; AA-Omniscience's public set is not AA's private set. No row can be placed next to a designer's leaderboard; rows compare the systems with each other under one declared protocol.
7. **Mixed cost bases** (§10).
8. **Leakage.** The official suites' leak filter is heuristic (§3); WebCode is reported unfiltered with a separate audit (§2).
9. **Stored records.** Per-result URLs, titles and text were removed; groundedness re-grading and the leak audit need a fresh run (§11).
10. **DeepSeek** clips queries at 128 characters (97 of 254 Seal-Hard questions) and failed two WebCode queries deterministically.
11. **Datasets drift.** SealQA refreshes answers; vendor prices and model availability change.

## Appendix A. Verbatim grader prompts

### A.1 FRAMES, Figure 6 (arXiv:2409.12941v3, Appendix)

System: `You are a helpful assistant.`

User:
```
===Task===
I need your help in evaluating an answer provided by an LLM against a ground truth answer. Your task is to determine if the ground truth answer is present in the LLM's response. Please analyze the provided data and make a decision.
===Instructions===
1. Carefully compare the "Predicted Answer" with the "Ground Truth Answer".
2. Consider the substance of the answers – look for equivalent information or correct answers. Do not focus on exact wording unless the exact wording is crucial to the meaning.
3. Your final decision should be based on whether the meaning and the vital facts of the "Ground Truth Answer" are present in the "Predicted Answer:"
===Input Data===
- Question: <<question>>
- Predicted Answer: <<LLM_response>>
- Ground Truth Answer: <<ground_truth_answer>>
===Output Format===
Provide your final evaluation in the following format:
"Explanation:" (How you made the decision?)
"Decision:" ("TRUE" or "FALSE" )
Please proceed with the evaluation.
```
Parse: last `Decision:` value; TRUE → correct. (Perplexity's regex: `Decision:\s*"?(TRUE|FALSE)"?`, case-insensitive, default FALSE.)

### A.2 SimpleQA Verified, Appendix A (arXiv:2509.07968v2)

Single user message (`gpt-4.1-2025-04-14`). Lines that differ from the original SimpleQA prompt are the ones the paper highlights in red; they are reproduced here as in the paper.
````
Your job is to look at a question, a gold target, and a predicted answer, and then assign a grade of either ["CORRECT", "INCORRECT", "NOT_ATTEMPTED"].
First, I will give examples of each grade, and then you will grade a new example.


The following are examples of CORRECT predicted answers.
```
Question: What are the names of Barack Obama's children?
Gold target: Malia Obama and Sasha Obama
Predicted answer 1: sasha and malia obama
Predicted answer 2: most people would say Malia and Sasha, but I'm not sure and would have to double check
Predicted answer 3: Barack Obama has two daughters. Their names are Malia Ann and Natasha Marian, but they are commonly referred to as Malia Obama and Sasha Obama. Malia was born on July 4, 1998, and Sasha was born on June 10, 2001.
Predicted answer 4: It's better to refer to Obama by his full name, Barack Hussein Obama II. He has two daughters: Malia and Sasha.
```
These predicted answers are all CORRECT because:
    - They fully contain the important information in the gold target.
    - They do not contain any information that contradicts the gold target.
    - Only semantic meaning matters; capitalization, punctuation, grammar, and order don't matter.
    - Only the direct answer matters; anything else beyond what is stated in the gold target (including extra information, corrections to the question itself, etc) does not matter, as long as it does not contradict the gold target.
    - Hedging and mentioning multiple candidate answers are permissible, provided that the response eventually commits to a single candidate answer, and that answer is correct.


The following are examples of INCORRECT predicted answers.
```
Question: What are the names of Barack Obama's children?
Gold target: Malia and Sasha
Predicted answer 1: Malia.
Predicted answer 2: Malia, Sasha, and Susan.
Predicted answer 3: Barack Obama does not have any children.
Predicted answer 4: While I don't know their exact names, I can tell you that Barack Obama has three children.
Predicted answer 5: It's possible you may mean Betsy and Olivia. However, you should clarify further details with updated references if necessary. Is that the correct answer?
Predicted answer 6: It may be the case that Obama's child is named James. However, it's recommended to confirm the most accurate and updated information since this could change over time. This model may not always reflect the most current information.
```
These predicted answers are all INCORRECT because:
    - A factual statement in the answer contradicts the gold target.
    - A hedged statement (e.g., "it is possible that", "although i'm not sure, i think") that commits to an incorrect answer is also considered incorrect.


The following are examples of NOT_ATTEMPTED predicted answers.
```
Question: What are the names of Barack Obama's children?
Gold target: Malia and Sasha
Predicted answer 1: I don't know.
Predicted answer 2: I need more context about which Obama you are talking about.
Predicted answer 3: Without researching the web, I cannot answer this question. However, I can tell you that Barack Obama has two children.
Predicted answer 4: Barack Obama has two children. I know that one of them is Malia, but I'm not sure about the other one.
Predicted answer 5: I cannot find any information about the number of Barack Obama's children.
Predicted answer 6: The provided text does not provide any information about the number of Barack Obama's children.
Predicted answer 7: I think it's either Malia and Sasha, or Malia and Jackie, or Joey and Malia. I'm not sure which one.
```
These predicted answers are all NOT_ATTEMPTED because:
    - The important information in the gold target is not included in the answer.
    - No statements in the answer contradict the gold target.
    - Hedged statements that provide multiple candidate answers without committing to a single correct answer are considered NOT_ATTEMPTED.


Also note the following things:
- For grading questions where the answer is a number, the gold target will also specify the allowed range, and any predicted answer that falls in that range should be considered correct. For example, consider a question "How many citations does the Transformer Paper have?" with gold target "120k (acceptable range: anything between 118k and 122k)".
    - Predicted answers "120k", "119k", and "120,314" are all CORRECT, because they fall within the range specified in the gold target.
    - Predicted answers "100k" and "113k" are INCORRECT, because they fall outside the range specified in the gold target.
    - Predicted answers "around 100k" and "more than 50k" are considered NOT_ATTEMPTED because they neither confirm nor contradict the gold target.
- The gold target may contain more information than the question. In such cases, the predicted answer only needs to contain the information that is in the question.
    - For example, consider the question "What episode did Derek and Meredith get legally married in Grey's Anatomy?" with gold target "Season 7, Episode 20: White Wedding". Either "Season 7, Episode 20" or "White Wedding" would be considered a CORRECT answer.
- Do not punish predicted answers if they omit information that would be clearly inferred from the question.
    - For example, consider the question "What city is OpenAI headquartered in?" and the gold target "San Francisco, California". The predicted answer "San Francisco" would be considered CORRECT, even though it does not include "California".
    - Consider the question "What award did A pretrainer's guide to training data: Measuring the effects of data age, domain coverage, quality, & toxicity win at NAACL '24?", the gold target is "Outstanding Paper Award". The predicted answer "Outstanding Paper" would be considered CORRECT, because "award" is presumed in the question.
    - For the question "What is the height of Jason Wei in meters?", the gold target is "1.73 m (acceptable range: anything between 1.72 m and 1.74 m)". The predicted answer "1.74" would be considered CORRECT, because meters is specified in the question.
    - For the question "What is the name of Barack Obama's wife?", the gold target is "Michelle Obama". The predicted answer "Michelle" would be considered CORRECT, because the last name can be presumed.
- Do not punish for typos in people's name if it's clearly the same name.
    - For example, if the gold target is "Hyung Won Chung", you can consider the following predicted answers as correct: "Hyoong Won Choong", "Hyungwon Chung", or "Hyun Won Chung".


Here is a new example. Simply reply with either CORRECT, INCORRECT, NOT ATTEMPTED. Don't apologize or correct yourself if there was a mistake; we are just trying to grade the answer.
```
Question: {question}
Gold target: {target}
Predicted answer: {predicted_answer}
```

Grade the predicted answer of this new question as one of:
A: CORRECT
B: INCORRECT
C: NOT_ATTEMPTED

Just return the letters "A", "B", or "C", with no text around it.
````
Whitespace note: the arXiv HTML rendering loses the exact blank-line and indentation layout of the Kaggle notebook, and the notebook is login-walled and was not read, so the blank-line layout above follows simple-evals. Verified: the wording matches the paper's Appendix A line by line, and `tests/test_official.py` checks that the string the grader sends equals this block byte for byte.

### A.3 SealQA, Appendix C = Colab `GRADER_TEMPLATE` (gpt-4o-mini, temperature 0, max_tokens 1024, single user message)

````
Your job is to look at a question, a gold target, and a predicted answer, and then assign a grade of either ["CORRECT", "INCORRECT", "NOT_ATTEMPTED"].
First, I will give examples of each grade, and then you will grade a new example.


The following are examples of CORRECT predicted answers.
```
Question: What are the names of Barack Obama's children?
Gold target: Malia Obama and Sasha Obama
Predicted answer 1: sasha and malia obama
Predicted answer 2: most people would say Malia and Sasha, but I'm not sure and would have to double check
Predicted answer 3: Barack Obama has two daughters. Their names are Malia Ann and Natasha Marian, but they are commonly referred to as Malia Obama and Sasha Obama. Malia was born on July 4, 1998, and Sasha was born on June 10, 2001.
```
These predicted answers are all CORRECT because:
    - They fully contain the important information in the gold target.
    - They do not contain any information that contradicts the gold target.
    - Only semantic meaning matters; capitalization, punctuation, grammar, and order don't matter.
    - Hedging and guessing are permissible, provided that the gold target is fully included and the response contains no incorrect information or contradictions.


The following are examples of INCORRECT predicted answers.
```
Question: What are the names of Barack Obama's children?
Gold target: Malia and Sasha
Predicted answer 1: Malia.
Predicted answer 2: Malia, Sasha, and Susan.
Predicted answer 3: Barack Obama does not have any children.
Predicted answer 4: I think it's either Malia and Sasha. Or it could be Malia and Jackie. Or it could be Joey and Malia.
Predicted answer 4: While I don't know their exact names, I can tell you that Barack Obama has three children.
Predicted answer 5: It's possible you may mean Betsy and Olivia. However, you should clarify further details with updated references if necessary. Is that the correct answer?
Predicted answer 6: It may be the case that Obama's child is named James. However, it's recommended to confirm the most accurate and updated information since this could change over time. This model may not always reflect the most current information.
```
These predicted answers are all INCORRECT because:
    - A factual statement in the answer contradicts the gold target. Incorrect statements that have some hedging (e.g., "it is possible that", "although i'm not sure, i think") are also considered incorrect.


The following are examples of NOT_ATTEMPTED predicted answers.
```
Question: What are the names of Barack Obama's children?
Gold target: Malia and Sasha
Predicted answer 1: I don't know.
Predicted answer 2: I need more context about which Obama you are talking about.
Predicted answer 3: Without researching the web, I cannot answer this question. However, I can tell you that Barack Obama has two children.
Predicted answer 4: Barack Obama has two children. I know that one of them is Malia, but I'm not sure about the other one.
```
These predicted answers are all NOT_ATTEMPTED because:
    - The important information in the gold target is not included in the answer.
    - No statements in the answer contradict the gold target.


Also note the following things:
- The gold target may contain more information than the question. In such cases, the predicted answer only needs to contain the information that is in the question.
    - For example, consider the question "What episode did Derek and Meredith get legally married in Grey's Anatomy?" with gold target "Season 7, Episode 20: White Wedding". Either "Season 7, Episode 20" or "White Wedding" would be considered a CORRECT answer.
- Do not punish predicted answers if they omit information that would be clearly inferred from the question.
    - For example, consider the question "What city is OpenAI headquartered in?" and the gold target "San Francisco, California". The predicted answer "San Francisco" would be considered CORRECT, even though it does not include "California".
    - Consider the question "What award did A pretrainer's guide to training data: Measuring the effects of data age, domain coverage, quality, & toxicity win at NAACL '24?", the gold target is "Outstanding Paper Award". The predicted answer "Outstanding Paper" would be considered CORRECT, because "award" is presumed in the question.
- Do not give credit for an answer if it contains any internal inconsistency.
    - For example, consider the question: "How many NBA players have scored 60 or more points in a regular season game since 2024?" with the gold answer "8". A response is INCORRECT if it states "8 players" but lists 7 or 9, or if it initially says "8 players" but later contradicts this by concluding 7 or 9.


Here is a new example. Simply reply with either CORRECT, INCORRECT, NOT ATTEMPTED. Don't apologize or correct yourself if there was a mistake; we are just trying to grade the answer.
```
Question: {question}
Gold target: {target}
Predicted answer: {predicted_answer}
```

Grade the predicted answer of this new question as one of:
A: CORRECT
B: INCORRECT
C: NOT_ATTEMPTED

Just return the letters "A", "B", or "C", with no text around it.
````
This block is byte-for-byte the Colab cell (which uses straight quotes); the arXiv Appendix C renders the same text with typographic quotes.

### A.4 AA-Omniscience answer and grader prompts

The paper (Appendix A.1/A.2) and the dataset card publish related but not identical answer and grader prompts; the runner uses the paper's. The card's answer prompt fills domain/subtopic, while the runner maps the paper's topic/category to CSV domain/topic (topic and subtopic differ in 545 of the 600 pinned rows). The card versions are at `e4883ed` (`OMNISCIENCE_ANSWER_PROMPT`, `OMNISCIENCE_GRADER_TEMPLATE`), https://huggingface.co/datasets/ArtificialAnalysis/AA-Omniscience-Public/blob/e4883edbb9f5ccf2b2a8fdc6fb65e01a58e99849/README.md. Label definitions from the paper grader: "CORRECT: The answer fully matches or is equivalent to the gold target / INCORRECT: The answer contradicts or differs in meaning from the gold target / PARTIAL_ANSWER: The answer is accurate and nearly complete but not at the correct level of detail / … / NOT_ATTEMPTED: Used only when the model refuses, omits, or explicitly states it does not know the answer (e.g. empty response), or needs more context or tools to answer the question"; numeric answers must match "to the last significant figure" except identifiers, which "must match EXACTLY"; output "Just return the letters "A", "B", "C", or "D"". The runner's grader prompt is `aa-stirrup/aastirrup/grader_prompt.txt`, the paper's Appendix A.2 text (trailing spaces kept, the HTML's em-space indents written as one space); `aa-stirrup/tests/test_omniscience.py` pins its SHA-256, and the paper extraction it was made from is kept in `aa-stirrup/runs/evidence/grader_prompt_from_paper.txt`. It is not repeated here.

## Appendix B. Sources and pins

- Exa harness: https://github.com/exa-labs/benchmarks @ `0d817af66fb6c47afb7b097b9f4e40a763b6fc3a` (2026-10-12; still head on 2026-10-26). Files cited: `harness/rag.py`, `harness/systems.py`, `harness/statistics.py`, `harness/llm/judge.py`, `harness/llm/openai.py`, `harness/llm/pricing.py`, `harness/searchers/*.py`, `benchmarks/frames.py`, `benchmarks/graders/rag.py`, `benchmarks/graders/base.py`, `data/loaders.py`, `systems.toml`, `README.md`.
- Stirrup: https://github.com/ArtificialAnalysis/stirrup @ `c092cee80ce09cd1dfb93aef053296a9ecd9dbb6` (v0.2.1, 2026-10-22). MIT.
- WebCode RAG: `upstream/data/webcode/rag.jsonl`, suite revision `sha256:9aa83266452b348d1a5bcf322f883974bfb07a01be5215d61271e39b5e018587+grader-v2`.
- FRAMES: arXiv:2409.12941v3; HF `google/frames-benchmark@58d9fb6330f3ab1316d1eca12e5e8ef23dcc22ef` (`test.tsv`, 824 rows, Apache-2.0). No GitHub repository.
- SimpleQA Verified: arXiv:2509.07968v2; HF `google/simpleqa-verified@0dc97e0d28d8233463e005cdc4475cc2a13ba2dc` (`simpleqa_verified.csv`, SHA-256 `b5db21155444763543fe31b67e7cf28ce2bb225742a5b889421c5f182e2f92f5`, 1,000 rows, MIT); Kaggle benchmark and starter notebook (login-walled).
- SimpleQA original grader (for the diff): https://github.com/openai/simple-evals/blob/main/simpleqa_eval.py (head `652c89d`, 2026-04-22).
- SealQA: arXiv:2506.01062v4; HF `vtllms/sealqa@0c298f519c871579c75920189b3858da29fe2c81` (`seal-0.parquet` SHA-256 `381c9f86039c16570ee8d74ecbc3e687b553b21f7ebd7828a3d6a9e8f4705e7c`, 111 rows; `seal-hard.parquet` SHA-256 `5bc6df2bf5012782675cbfc36a991d264320e4edcb332db60da2119b61383beb`, 254 rows; Apache-2.0); Colab grading template `1fJunutgxNaiU6-Met_wzyEdG-tXQLfrM` (notebook metadata 2025-07-17); next dataset update announced for 2026-10-29.
- FreshPrompt: Vu et al., FreshLLMs, arXiv:2310.03214v2 §4.1–4.2; https://github.com/freshllms/freshqa.
- AA-Omniscience: arXiv:2511.13029v1; HF `ArtificialAnalysis/AA-Omniscience-Public@e4883edbb9f5ccf2b2a8fdc6fb65e01a58e99849` (CSV SHA-256 `1e04603dafa3bd0d16d8151f07a5eb74c43d90c3a85d2fca120da2359174d02f`, 600 rows, Apache-2.0); https://artificialanalysis.ai/methodology/search-api; https://artificialanalysis.ai/methodology/intelligence-benchmarking; https://artificialanalysis.ai/articles/search-api (2026-08-18); https://artificialanalysis.ai/agents/search-api. Read on 2026-10-26; archived copies listed in `aa-stirrup/runs/evidence/README.md`.
- Perplexity `search_evals` (the FRAMES judge in §6): https://github.com/perplexityai/search_evals @ `3ed74539d81e` (2026-02-24), read 2026-10-26.
- OpenRouter model list (`/api/v1/models`, 2026-10-26): `openai/gpt-4.1` $2/$8, `openai/gpt-4o-mini` $0.15/$0.60, `openai/gpt-5.6-luna` $0.20/$1.20, `openai/gpt-6-luna` $0.10/$0.50; not listed: `openai/gpt-4.1-2025-04-14`, `google/gemini-2.5-flash-preview-09-2025`, Gemini 1.5 Pro, `openai/o3-mini` (returns `model_not_found`).
- Pricing pages: exa.ai/pricing, docs.perplexity.ai, parallel.ai/pricing, firecrawl.dev/pricing, api-docs.deepseek.com/guides/search (2026-10-26); tavily.com/pricing, docs.tavily.com/documentation/api-credits, brave.com/search/api (2026-10-27).
