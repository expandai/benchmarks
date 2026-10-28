# AA-Omniscience the way Artificial Analysis runs search APIs (Stirrup agent), 2026-10-26

This directory reproduces Artificial Analysis' (AA) search-API setup for AA-Omniscience as closely as their published material allows. It uses their Stirrup agent with `web_search` / `web_fetch` / `finish`, GPT-5.6 Luna (medium) as both answerer and grader, the paper's grader prompt, and Omniscience scoring. Each bakeoff searcher is plugged in as the agent's `web_search`. It runs on the **public** AA-Omniscience questions only.

Status: the full public-600 run completed for every published system, with one failed question (Tavily, `aao-054`, HTTP 400 on every attempt, scored as not attempted). Exa fast, Parallel turbo, Firecrawl, DeepSeek, Perplexity fast and model-only ran on 2026-10-27 from 01:11 UTC; Expand Search, Tavily and Brave from 22:18 UTC the same day; Exa lite, Exa auto, Perplexity web and Parallel fast on 2026-10-28. Results: `runs/full-600/summary.md`, `summary.json`, per-task records per system. The table is reproduced in the repository README. The sections below are the design record and the 20-question pilot that preceded it.

## AA's methodology as published (checked 2026-10-26)

Sources:
- [AA search-API methodology](https://artificialanalysis.ai/methodology/search-api) (read 2026-10-26; URL, read date and archived copy of every AA page in `runs/evidence/README.md`)
- [AA launch article, 2026-08-18](https://artificialanalysis.ai/articles/search-api)
- [Leaderboard](https://artificialanalysis.ai/agents/search-api)
- AA-Omniscience paper, [arXiv 2511.13029v1](https://arxiv.org/html/2511.13029v1) (§2.4 and appendix A)
- [Stirrup](https://github.com/ArtificialAnalysis/stirrup) (MIT)
- [AA intelligence-benchmarking methodology](https://artificialanalysis.ai/methodology/intelligence-benchmarking) (grader history)

| Setting | AA's published value | Source |
|---|---|---|
| Harness | Stirrup search-agent loop. `web_search` and `web_fetch` tools, plus a `finish` tool that submits the final answer | methodology, article |
| Turn budget | 25 agent turns, unlimited tool calls within them. No `finish` after 25 turns means no answer, which scores zero | methodology |
| Results per search | `max_results=10` or the provider's equivalent; provider defaults otherwise | methodology |
| `web_search` payload | "returns its native response payload", "Provider-native; the model sees the provider's original response body"; the article adds "(with content modes standardized to snippets)" | methodology, article |
| `web_fetch` | Fetches one URL from a search result and returns text only, using a text-only extractor with a 15 s timeout per page. Fetching a URL that `web_search` did not return is a recoverable (failed) tool call | methodology |
| Candidate model | GPT-5.6 Luna (medium), max output 127,999 tokens | methodology |
| Grader | GPT-5.6 Luna (medium), "benchmark-specific rubrics" (Omniscience grader since Intelligence Index v4.1.1; the paper used Gemini 2.5 Flash) | methodology, intelligence methodology |
| Grader prompt | Not on AA's pages. The paper's appendix A.2 is the published Omniscience grader: CORRECT / INCORRECT / PARTIAL_ANSWER / NOT_ATTEMPTED, reply A–D | paper |
| Answer prompt | Paper A.1: "You are answering questions about {topic}, and in particular {category}. … answer with JUST the answer … If you do not know … be clear about this". AA does not publish the agent's prompt | paper |
| Omniscience Index | OI = 100·(c − i)/(c + p + i + a); partial = 0, abstain = 0, incorrect = −1; accuracy = c/N; hallucination rate = i/(p + i + a). No domain weighting | paper §2.4 |
| What the Search Index uses | Omniscience **accuracy**, not OI or hallucination rate ("given a search tool supplying context, a model tends to always answer") | methodology |
| Sample | 600 **private** held-out questions, 100 per domain × 6 | methodology |
| Errors | Provider 429, 5xx and timeouts are retried until success, and no published result contains one. Fetch failures go back to the model as failed tool calls | methodology |
| Contamination | Filtered inside both tools: search rows screened on URL, title and snippet; fetched text screened after extraction. Flagged rows are dropped without changing the response shape. Rules not published | methodology |
| Cost | Model cost (input, cached, reasoning and output tokens; earlier-turn input priced at the cache-hit rate) plus search-provider cost | methodology |
| Time | Search time is measured time in `web_search`. Model time is *derived* (tokens ÷ canonical output speed) | methodology, article |
| Baseline | `model_only`: one call, benchmark prompt, no tools. Omniscience accuracy 38 | article, leaderboard |

AA's published Omniscience accuracy (private 600; leaderboard data as of 2026-10-26):

| Provider | Score |
|---|---|
| Exa auto + dynamic highlights | 73 |
| Firecrawl | 73 |
| Perplexity medium | 72 |
| Exa lite + dynamic highlights | 72 |
| OpenAI Web Search | 72 |
| Perplexity high | 71 |
| Nimble standard | 71 |
| Brave LLM context | 69 |
| You.com highlights | 69 |
| Parallel basic | 68 |
| Parallel advanced | 67 |
| Octen | 66 |
| Model only | 38 |

From the launch article: Exa fast 69, Parallel turbo 56.

AA has no row for Perplexity *fast*, Exa *fast + highlights* as configured here, DeepSeek, or Expand.

Things AA does not publish, so neither this directory nor anyone else can match them exactly:
- the agent system prompt and user prompt
- the `web_search` / `finish` tool descriptions
- the per-provider "standardized to snippets" rendering
- the contamination rules
- the Omniscience rubric text AA uses with GPT-5.6 Luna
- which Stirrup client (Chat Completions or Responses) and which commit they ran

## Our implementation, and every choice made where AA is silent

| Item | Choice | Why |
|---|---|---|
| Stirrup | [`c092cee`](https://github.com/ArtificialAnalysis/stirrup/commit/c092cee80ce09cd1dfb93aef053296a9ecd9dbb6) (v0.2.1, 2026-10-22, latest on 2026-10-26). Installed non-editable into `aa-stirrup/.venv` (Python 3.12) from the pinned clone at `aa-stirrup/.stirrup-src` (`make stirrup aa-venv`). Versions in `runs/evidence/venv-versions.txt` | AA does not name a version |
| Agent | Stirrup `Agent`, `max_turns=25`, everything else at Stirrup defaults: its base system prompt ("…complete that task using the tools provided in 25 steps…"), turn-remaining warnings from turn 5, a "Please continue" message after a text-only turn, and summarisation at 70% of context (never reached) | AA says Stirrup with 25 turns |
| System prompt | Stirrup appends ours as "Follow these instructions from the User:" + paper A.1. `{topic}` = CSV `domain`, `{category}` = CSV `topic` | The paper publishes A.1; the pinned dataset card's related prompt fills domain/subtopic instead (topic and subtopic differ in 545 of the 600 rows). We follow the paper |
| User turn | `Question: …` plus a line asking the model to use `web_search` / `web_fetch` and call `finish` with JUST the answer, or to say it does not know (`aastirrup/omniscience.py: TASK_TEMPLATE`) | Not published |
| `finish` | Custom finish tool `finish(answer: str)` | AA: "calls finish and submits its final answer". Stirrup's default finish takes `reason`, `paths` |
| `web_search` | Stirrup's tool name and schema (one `query` string). Results rendered exactly as Stirrup renders Brave results: `<results><result><title/><url/><description/></result>…</results>`, HTML-escaped, 40,000-character cap with Stirrup's middle truncation. A test checks that the rendering is byte-identical to Stirrup's Brave executor. `description` = the searcher's evidence (`SearchResult.evidence`: highlights, excerpts or passages, else text, snippet or summary), the same text the bakeoff's RAG answerer sees. 10 results per search. Tool description: "Search the web. Returns top 10 results with title, URL, and description as XML." | One rendering for every provider, so the providers are compared on the same footing. **AA instead passes the provider-native JSON body** ("standardized to snippets"). This is the largest known deviation; see caveats |
| `web_fetch` | Stirrup's own fetch executor (trafilatura → markdown, 40,000 characters, public-IP checks), renamed from Stirrup's `fetch_web_page` to AA's `web_fetch`. 15 s deadline. Only URLs returned by `web_search` in the same task are accepted; any other URL gets a failed tool call | AA's settings |
| Contamination filter | Drop rows whose URL matches `artificialanalysis.ai`, `aa-omniscience`, the paper's arXiv id or the AA Hugging Face datasets; also check title and description for the AA-Omniscience name or the verbatim question (≥ 40 characters). A fetched page with the same signals returns a failed fetch. Every drop is counted (`filtered_results`) | AA's rules are unpublished. **0 rows were filtered in the pilot** |
| Search errors | The bakeoff searcher's own retries run first, then up to 4 attempts of the whole call on 408/429/5xx/timeouts. Any other failure (or exhausted retries) ends the task as an execution error. Such a task is not graded and is re-run on the next invocation | AA retries fatal provider errors "until success" |
| No `finish` in 25 turns | Graded NOT_ATTEMPTED (counts 0 in OI and accuracy) without calling the grader | AA: "scores zero" |
| Answer transport | OpenRouter `openai/gpt-5.6-luna` through Stirrup's `OpenResponsesClient` (Responses API), `reasoning.effort=medium`, `encrypted_reasoning=True` (reasoning items passed back each turn), `max_output_tokens=127,999`. Stirrup's `ChatCompletionsClient` route exists as `--transport chat` but was not used | All OpenAI models were called through OpenRouter. Responses with reasoning passback is how GPT-5.x runs natively |
| Grader | OpenRouter `openai/gpt-5.6-luna`, Chat Completions, `reasoning.effort=medium`. Paper A.2 prompt **verbatim** (trailing spaces kept; the HTML's nine em-space indents written as one space) as the single user message, stored in `aastirrup/grader_prompt.txt` (SHA-256 pinned in a test). Reply parsed as A–D (or the grade word); an unparseable reply is retried | AA's rubric text is unpublished. The paper and pinned dataset card publish related rubrics; this run uses the paper version |
| Scoring | Paper §2.4 formulas; no domain weighting. Reported: OI, accuracy (AA's Search Index metric), C/I/P/NA, hallucination rate | |
| Sample | Domain-balanced draw from the public 600: each domain shuffled with seed 20261026, domains dealt round-robin in sorted order (4+4+3+3+3+3 for n=20). Questions from the bakeoff loader `bakeoff.suites.load_aa_omniscience` (pinned, SHA-256 checked), imported unchanged | |
| Systems | Bakeoff catalog searchers built by `bakeoff.register.install()` + `harness.systems.build_searcher`, with options exactly as in the catalog: `expand` (Expand Search, `POST /v1/search`, 10 results), `perplexity-fast`, `perplexity-web`, `exa-fast-highlights`, `exa-lite-highlights`, `exa-auto-highlights`, `parallel-turbo`, `parallel-fast`, `firecrawl-search`, `deepseek`, `tavily-advanced`, `brave-llm-context`, plus AA's `model-only` baseline | |
| Concurrency | Expand 5, DeepSeek 5, others 10. Systems ran in several windows (Status above), so results may reflect web changes between windows | Task limits. DeepSeek is lowered as in the bakeoff's run-suite |
| Cost | Model and grader: OpenRouter `usage.cost` per call (list price, cache discounts as actually applied). Search: the searcher's `cost_usd` (provider-reported where available, otherwise list price) | AA prices earlier-turn input at the cache-hit rate. OpenRouter's actual cache hits were 80–90% of input here |
| Time | Measured. Wall time per task (agent + grader), measured `web_search` time, and measured model request time. Not AA's derived model time | |

## Pilot: 20 public questions, 2026-10-26

Run: `runs/pilot-20/`. The manifest records seed 20261026, the question ids, the Stirrup commit and the settings. One JSON file per (system, question) holds:
- the answer, grade and raw grader reply
- turns, every search (query, latency, cost, results, filtered) and fetch
- per-call token usage and cost
- a readable trace and the fetched URLs in fresh runs; the committed records keep search-result and fetch counts, not the trace, result URLs or fetch URLs (see `../runs/EXCLUDED.md`)

Questions:

`aao-079 aao-116 aao-299 aao-305 aao-496 aao-551 aao-088 aao-192 aao-224 aao-400 aao-431 aao-512 aao-090 aao-101 aao-230 aao-346 aao-481 aao-596 aao-072 aao-143`

| System | n | OI | Acc % | C / I / P / NA | Halluc. % | Searches/q | Fetches/q | Turns/q | In tok/q (cached) | Out tok/q (reasoning) | Search $/q | Model $/q | Grader $/q | Total $/q | Wall s/q mean (p50) | s/search | Errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Perplexity fast | 20 | 95.0 | 95.0 | 19 / 0 / 0 / 1 | 0.0 | 4.2 | 0.8 | 4.5 | 74,165 (56,180) | 407 (193) | 0.0043 | 0.0061 | 0.0001 | 0.0104 | 15 (10) | 0.26 | 0 |
| Exa fast highlights | 20 | 90.0 | 95.0 | 19 / 1 / 0 / 0 | 100.0 | 4.2 | 0.8 | 4.3 | 96,361 (74,698) | 407 (193) | 0.0298 | 0.0074 | 0.0002 | 0.0373 | 15 (10) | 0.37 | 0 |
| Parallel turbo | 20 | 80.0 | 90.0 | 18 / 2 / 0 / 0 | 100.0 | 4.5 | 1.1 | 5.2 | 141,297 (117,391) | 505 (259) | 0.0046 | 0.0089 | 0.0002 | 0.0136 | 18 (11) | 0.39 | 0 |
| Firecrawl search | 20 | 70.0 | 85.0 | 17 / 3 / 0 / 0 | 100.0 | 6.0 | 1.9 | 7.0 | 58,264 (47,577) | 638 (313) | 0.0110 | 0.0044 | 0.0001 | 0.0155 | 26 (20) | 1.03 | 0 |
| DeepSeek | 20 | 65.0 | 80.0 | 16 / 3 / 0 / 1 | 75.0 | 6.5 | 1.1 | 7.3 | 361,059 (321,340) | 723 (421) | 0.0046 | 0.0172 | 0.0001 | 0.0219 | 26 (10) | 0.56 | 0 |
| Model only (no search) | 20 | -5.0 | 45.0 | 9 / 10 / 0 / 1 | 90.9 | 0.0 | 0.0 | 1.0 | 121 (0) | 991 (978) | 0.0000 | 0.0012 | 0.0004 | 0.0016 | 13 (9) | 0.00 | 0 |

| System | Full public set (600) $ | of which search $ | Hours at concurrency | Concurrency |
|---|---|---|---|---|
| Perplexity fast | 6.23 | 2.55 | 0.26 | 10 |
| Exa fast highlights | 22.39 | 17.85 | 0.25 | 10 |
| Parallel turbo | 8.18 | 2.73 | 0.30 | 10 |
| Firecrawl search | 9.27 | 6.59 | 0.43 | 10 |
| DeepSeek | 13.12 | 2.75 | 0.86 | 5 |
| Model only (no search) | 0.95 | 0.00 | 0.22 | 10 |

Column notes:
- **OI** is the Omniscience Index. **Acc** is accuracy, the number AA's Search Index uses.
- **C/I/P/NA** are correct, incorrect, partial and not-attempted counts.
- **Halluc.** is i/(p+i+a).
- **$/q** includes search, answer model and grader.
- **Wall s/q** is per task, including the grader.
- **s/search** is mean measured `web_search` latency.

The second table extrapolates the pilot means to all 600 public questions: cost = $/q × 600; hours = mean wall s/q × 600 ÷ concurrency.

What the pilot shows:

- **It ran cleanly.** There were 0 execution errors. No search needed a retry and no contamination rows were dropped. One task hit the 25-turn limit without calling `finish` (DeepSeek, aao-116).
- **Perplexity fast was piloted separately.** At preflight every Perplexity call returned `401 insufficient_quota` (`runs/evidence/preflight.txt`); once the quota was restored, Perplexity fast ran the same 20 questions (`runs/pilot-20/logs/perplexity-pilot.log`). The required 2-question smoke was run with Parallel turbo (2/2 correct; its traces are not kept in this repository).
- **Exa was not blocked.** No 402 errors this session.
- **The search systems cannot be told apart on 20 questions.** Every search system scored 80–95% accuracy against 45% for model-only. Every search system answered the same 15 of the 20 questions correctly; the gaps come from five questions (aao-116, -143, -192, -230, -400). Accuracy here is higher than AA's 56–73 on its private 600 (model-only 38), so this public sample is easier, or partly findable online, or both.
- **Search cost drives Exa; model cost drives DeepSeek.** Exa fast + highlights costs $0.007 per search, the highest search cost per question. DeepSeek's long `summary` text puts about 360k input tokens per question into the model (80–90% cached), so model cost is the largest part of DeepSeek's cost.
- **About half of fetches failed.** Of the `web_fetch` calls, many got `403 Forbidden` (sites blocking Stirrup's fetcher) and others were refused because the URL had not been returned by `web_search`. Most refused URLs were ones the model made up. A few were real results the model sent back with `&amp;` or a `#fragment` added. **After the pilot**, the returned-URL check was changed to ignore HTML escaping and fragments (`tools.url_key`, tested). That is the only code change since the pilot, and the full run used it.

## Go / no-go for the full public run

**GO for the full public set (600 questions) on every search system plus model-only, with one condition:**
start from a new run directory, so the post-pilot URL-matching change is not mixed with pilot rows.

Estimated cost and time, from pilot means × 600: Perplexity fast $6.2 (0.3 h), Exa fast highlights $22.4 (0.25 h), Parallel turbo $8.2 (0.3 h), Firecrawl search $9.3 (0.4 h), DeepSeek $13.1 (0.9 h at concurrency 5), model-only $1.0 (0.2 h); systems that were not piloted were assumed to cost about what Parallel turbo costs. All systems run at once.

What a full run can and cannot show: on 600 questions the 95% interval on accuracy is about ±3 points. The search systems sit near the ceiling on these public questions, so expect gaps of a few points and compare them per question (paired). The full run is worth doing for a relative ranking on AA's protocol and for each provider's cost and latency profile. It does not give a number comparable to AA's leaderboard.

## Caveats

- **Public subset, not AA's private 600.** These are AA's public 10% (600 of 6,000). AA's search leaderboard uses 600 different, private questions. The paper says the public set tracks the full set for model-only scoring. That has not been shown with search, and the public set has been online since 2025-11, so search engines can surface pages that quote it. The filter drops the obvious copies (none appeared in the pilot); paraphrases are not caught. Do not put these numbers next to AA's.
- **Rendering differs from AA's.** AA hands the model each provider's native JSON ("standardized to snippets"); here every provider is rendered through Stirrup's Brave XML from the bakeoff's normalised `SearchResult`. That makes the providers comparable to each other, but each provider's own extra fields (dates, scores, several highlights as a list) are flattened into one `description`. DeepSeek's long summaries can exceed Stirrup's 40,000-character cap per search, and the middle results are then cut (Stirrup's own behaviour).
- **Prompts and rubric are ours where AA is silent** (user turn, tool descriptions, finish schema, topic/category mapping). The grader prompt is the paper's, not AA's current one, and is run on GPT-5.6 Luna rather than the paper's Gemini 2.5 Flash.
- **OpenRouter transport.** The answerer calls `openai/gpt-5.6-luna` through OpenRouter's Responses endpoint and the grader through Chat Completions. Cost is OpenRouter's reported `usage.cost`. Time is measured, while AA's model time is derived from token counts.
- **Sample size.** n=20 per system gives a 95% interval of about ±15–20 points on accuracy and wider on OI. The pilot checks cost, time and failure modes; it cannot rank systems. On the full 600 the measured interval is about ±2.5 points on accuracy (`runs/full-600/summary.md`), so small gaps need the paired, per-question comparison (repository README, "Paired differences").
- **Shared credentials.** Every key is shared with the bakeoff run in `../runs/`. Perplexity's quota ran out during this session, and other providers' rate limits can also be hit by both runs at once.

## Files

| Path | What |
|---|---|
| `aa` | Wrapper. Sources the bakeoff-root `.env` (`search/.env`) (values are never printed or passed as arguments), sets `PYTHONPATH` to this directory, `..` (bakeoff) and `../upstream` (pinned Exa harness), sets `PYTHONDONTWRITEBYTECODE=1` (so nothing is written into the other run's tree), then runs `python -m aastirrup`. `AA_PYTEST=1 ./aa` runs the offline tests with no credentials |
| `aastirrup/omniscience.py`, `aastirrup/grader_prompt.txt` | Paper prompts, task template, loader + sampler, grade parser, OI/accuracy/hallucination scoring |
| `aastirrup/tools.py` | `SearchToolProvider`: the single Stirrup tool provider, parametrised by searcher (`web_search`, `web_fetch`, contamination filter, retries, telemetry) |
| `aastirrup/systems.py` | System → bakeoff catalog searcher, concurrency, label |
| `aastirrup/llm.py` | OpenRouter answer client (Stirrup Responses or Chat), grader, model-only call, usage and cost capture |
| `aastirrup/runner.py` | Per-task Stirrup agent run, grading, resumable JSON output |
| `aastirrup/report.py`, `aastirrup/__main__.py` | Summary table and 600-question extrapolation; CLI (`prepare`, `preflight`, `run`, `report`) |
| `tests/`, `pytest.ini` | Offline regression tests (own `pytest.ini`, so the bakeoff's is not picked up): Brave-rendering byte-equality with Stirrup, filter, retry and fatal errors, fetch restriction, a full Stirrup agent loop with a scripted model (search → fetch → finish → grade), 25-turn exhaustion, the fatal-search-error path, scoring formulas, grader-prompt hash, deterministic balanced sampling |
| `runs/pilot-20/` | Pilot manifest, per-task JSON, `summary.md` / `summary.json`, `logs/` |
| `runs/evidence/` | Preflight output, pytest output, package versions, the paper's grader text, and the URL, read date and archived copy of every AA page (`README.md`) |

## Commands

```sh
# From search/ (the bakeoff root): pinned Stirrup clone + venv (once), see the Makefile.
make stirrup aa-venv
cd aa-stirrup

AA_PYTEST=1 ./aa                                   # offline tests
./aa preflight                                     # one live search per system
./aa prepare --run runs/full-600-rerun --n 600 --resume  # reuse only a matching manifest
./aa run --run runs/full-600-rerun --systems expand perplexity-fast perplexity-web exa-fast-highlights exa-lite-highlights exa-auto-highlights parallel-turbo parallel-fast firecrawl-search deepseek tavily-advanced brave-llm-context model-only
./aa run --run runs/full-600-rerun --systems ...         # re-run = resume (errors retried, completed tasks skipped)
./aa report --run runs/full-600-rerun
```

New system folders carry a settings fingerprint (`run-config.json`: source, models, transport, dataset and
resolved search options), and resuming with different settings is refused. The stored folders predate the
fingerprint; `report` reads them, and live reruns go in a new folder. Failed attempts are archived under
`<system>/attempts/<question-id>/` before a retry.
