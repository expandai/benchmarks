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
