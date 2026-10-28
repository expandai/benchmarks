# Search-API bakeoff: one target per step of the reproduction (README "Reproduce").
# Live targets spend money and need the keys in .env; `make test` needs only `make upstream` and `make venv`.
# Costs in the help text are the recorded costs of the stored runs (runs/report.json, runs/official/report.json
# "spend", aa-stirrup/runs/*/summary.json; Expand's search at list price, bakeoff/pricing.py), not estimates.

UV ?= uv
UPSTREAM_REPO    := https://github.com/exa-labs/benchmarks
UPSTREAM_COMMIT  := 0d817af66fb6c47afb7b097b9f4e40a763b6fc3a
STIRRUP_REPO     := https://github.com/ArtificialAnalysis/stirrup
STIRRUP_COMMIT   := c092cee80ce09cd1dfb93aef053296a9ecd9dbb6
# Stirrup's venv: the pinned Stirrup clone plus the harness dependencies the AA runner imports.
STIRRUP_DEPS     := ./aa-stirrup/.stirrup-src anthropic curl-cffi datasets dateparser httpx huggingface-hub numpy openai \
                    pandas pydantic rich tenacity tiktoken pytest pytest-asyncio

# Systems as they appear in the published tables.
WEBCODE_SYSTEMS  := rag-exa-fast-highlights rag-exa-instant-highlights rag-exa-webcode rag-exa-lite-highlights \
                    rag-exa-auto-highlights rag-parallel-turbo rag-parallel-fast rag-perplexity-fast rag-perplexity-web rag-firecrawl-search \
                    rag-deepseek rag-expand rag-tavily-advanced rag-brave-llm-context
OFFICIAL_SYSTEMS := rag-model-only rag-perplexity-fast rag-perplexity-web rag-exa-fast-highlights rag-exa-lite-highlights rag-exa-auto-highlights \
                    rag-parallel-turbo rag-parallel-fast rag-firecrawl-search rag-deepseek rag-expand rag-tavily-advanced \
                    rag-brave-llm-context
AA_SYSTEMS       := expand perplexity-fast perplexity-web exa-fast-highlights exa-lite-highlights exa-auto-highlights parallel-turbo parallel-fast \
                    firecrawl-search deepseek tavily-advanced brave-llm-context model-only

.PHONY: index help upstream venv test download dry-run stirrup aa-venv test-aa scrub-check \
        webcode-rag webcode-rag-pilot official seal-0-official seal-hard-official simpleqa-verified-official frames-official \
        leak-audit aa-omniscience aa-omniscience-pilot report paired

help:
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | column -t -s "$$(printf '\t')"

# ---------------------------------------------------------------------------------------------------- setup

upstream: ## Clone exa-labs/benchmarks at the pinned commit into ./upstream (never vendored, never edited)
	@test -d upstream/.git || git clone --quiet $(UPSTREAM_REPO) upstream
	@git -C upstream fetch --quiet origin $(UPSTREAM_COMMIT) 2>/dev/null || true
	@git -C upstream checkout --quiet --detach $(UPSTREAM_COMMIT)
	@test "$$(git -C upstream rev-parse HEAD)" = "$(UPSTREAM_COMMIT)" || { echo "upstream is not at $(UPSTREAM_COMMIT)" >&2; exit 1; }
	@echo "upstream @ $$(git -C upstream rev-parse --short HEAD)"

venv: ## Create ./.venv from uv.lock (Python 3.12; upstream installed editable from ./upstream)
	$(UV) sync --locked

test: ## Offline tests for the overlay (no network, no keys): adapters, registration, graders, suites, comparators
	PYTHONDONTWRITEBYTECODE=1 TIKTOKEN_CACHE_DIR=.tiktoken-cache .venv/bin/python -m pytest -q -p no:cacheprovider

download: ## Fetch and verify the pinned datasets into ./.hf-cache (public; no token needed)
	for s in webcode-rag frames-official simpleqa-verified-official seal-0-official seal-hard-official; do ./bench download --suite $$s || exit 1; done

dry-run: ## Preflight every published system on one suite: credentials, data pins, catalog (no paid call)
	./bench run --suite seal-0-official --system $(OFFICIAL_SYSTEMS) --judge-model openai/gpt-4o-mini --dry-run

stirrup: ## Clone ArtificialAnalysis/stirrup at the pinned commit (the AA-Omniscience agent)
	@test -d aa-stirrup/.stirrup-src/.git || git clone --quiet $(STIRRUP_REPO) aa-stirrup/.stirrup-src
	@git -C aa-stirrup/.stirrup-src checkout --quiet --detach $(STIRRUP_COMMIT)
	@test "$$(git -C aa-stirrup/.stirrup-src rev-parse HEAD)" = "$(STIRRUP_COMMIT)" || { echo "stirrup is not at $(STIRRUP_COMMIT)" >&2; exit 1; }
	@echo "stirrup @ $$(git -C aa-stirrup/.stirrup-src rev-parse --short HEAD)"

aa-venv: stirrup ## Create aa-stirrup/.venv (Stirrup pinned + the harness dependencies), Python 3.12
	$(UV) venv --python 3.12 aa-stirrup/.venv
	$(UV) pip install --python aa-stirrup/.venv/bin/python $(STIRRUP_DEPS)

test-aa: ## Offline tests of the AA-Omniscience Stirrup adapter (needs aa-venv)
	AA_PYTEST=1 ./aa-stirrup/aa

scrub-check: ## Fail if a stored record or log still carries a machine path or per-result detail (fix with `python3 -I tools/scrub_paths.py` / `tools/strip_result_details.py`)
	python3 -I tools/scrub_paths.py --check && python3 -I tools/strip_result_details.py --check

# ---------------------------------------------------------------------------------------------------- benchmarks (live; spend money)

webcode-rag-pilot: ## WebCode RAG, first 20 tasks, six competitor systems in parallel (recorded $0.70, 38–92 s per system; runs/pilot-20/ also holds their full 307-task runs, LIMIT=307)
	LIMIT=20 CONCURRENCY=5 runs/pilot-20/run-pilot.sh

webcode-rag: ## WebCode RAG, all 307 tasks, every published system (recorded $28.74 for the 14 published rows; 4–16 min per system in parallel)
	runs/run-suite.sh webcode-rag $(WEBCODE_SYSTEMS)

seal-0-official: ## SealQA Seal-0 under the official grader, all published systems (recorded $10.91 incl. pilots; 4–13 min per system)
	runs/run-suite.sh seal-0-official $(OFFICIAL_SYSTEMS)

seal-hard-official: ## SealQA Seal-Hard under the official grader (recorded $21.80 incl. pilots; 5–21 min per system)
	runs/run-suite.sh seal-hard-official $(OFFICIAL_SYSTEMS)

simpleqa-verified-official: ## SimpleQA Verified under the official grader and F1 (recorded $97.76 incl. pilots; 6–22 min per system)
	runs/run-suite.sh simpleqa-verified-official $(OFFICIAL_SYSTEMS)

frames-official: ## FRAMES under the Figure 6 grader (recorded $73.55; 8–44 min per system)
	runs/run-suite.sh frames-official $(OFFICIAL_SYSTEMS)

official: seal-0-official seal-hard-official simpleqa-verified-official frames-official ## All four official-grader suites (recorded $204.02)

leak-audit: ## Post-hoc WebCode leak audit over the stored WebCode runs (needs unredacted result.json, i.e. a fresh run)
	.venv/bin/python -I runs/leak-audit/audit.py && .venv/bin/python -I runs/leak-audit/regrade.py && .venv/bin/python -I runs/leak-audit/report.py

aa-omniscience-pilot: ## AA-Omniscience (public 600) via Stirrup, 20 balanced questions, all systems (recorded $2.01 for the six systems in the stored pilot)
	./aa-stirrup/aa prepare --run aa-stirrup/runs/pilot-20-rerun --n 20 --resume && ./aa-stirrup/aa run --run aa-stirrup/runs/pilot-20-rerun --systems $(AA_SYSTEMS) && ./aa-stirrup/aa report --run aa-stirrup/runs/pilot-20-rerun

aa-omniscience: ## AA-Omniscience (public 600) via Stirrup, all 600 questions, all systems (recorded $162.45; 0.17–1.03 h per system, in parallel)
	./aa-stirrup/aa prepare --run aa-stirrup/runs/full-600-rerun --n 600 --resume && ./aa-stirrup/aa run --run aa-stirrup/runs/full-600-rerun --systems $(AA_SYSTEMS) && ./aa-stirrup/aa report --run aa-stirrup/runs/full-600-rerun

# ---------------------------------------------------------------------------------------------------- tables

report: ## Regenerate harness tables and JSON reports from stored records (offline)
	.venv/bin/python runs/report.py && .venv/bin/python runs/official/report.py && .venv/bin/python runs/pilot-20/pilot_report.py

paired: ## Paired Expand-vs-competitor differences with bootstrap CIs from the stored per-task grades (offline; runs/paired.json, README table)
	.venv/bin/python runs/paired.py

index: ## Composite answer-accuracy index over the five independent datasets, with bootstrap CIs (offline; runs/index.json, README table)
	.venv/bin/python runs/index.py && .venv/bin/python runs/index.py --webcode-grounded > /dev/null
