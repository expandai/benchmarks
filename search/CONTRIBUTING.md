# Contributing

The harness is a pinned clone that is never edited, every system is a catalog entry, every grader prompt is
checked against the methodology document, and every published score recomputes from its committed per-task
grades. Changes should keep it that way, and new measurements go in new run directories.

## Offline tests

```sh
make upstream                 # clone exa-labs/benchmarks at the pinned commit (once)
make venv                     # uv sync --locked -> ./.venv
make test                     # tests/: adapters, registration, suites, graders, comparators
make stirrup aa-venv test-aa  # aa-stirrup/tests/: the AA-Omniscience adapter on the pinned Stirrup
```

No test reads a real key or opens a connection to a provider: `tests/conftest.py` deletes every provider
variable and sets `HF_HUB_OFFLINE=1`. The one network fetch is tiktoken downloading the `o200k_base`
encoding (3.6 MB) into `.tiktoken-cache/` the first time; CI caches it. Five tests check pinned dataset
row counts and skip until `make download` has filled `.hf-cache/`; CI runs `make download` first.

The GitHub Actions workflow (`../.github/workflows/test.yml`, working directory `search/`) runs `make upstream`,
`make venv`, `make download` (the public datasets, cached between runs, so the pin and row-count tests run),
`make test`, and last `tools/scrub_paths.py --check`; a second job builds the Stirrup venv (`make aa-venv`, no
`make venv`) and runs the Stirrup adapter tests. It runs on every push and pull request and needs no secrets.

## Adding a search provider

A provider is a `Searcher` subclass plus a catalog entry. Upstream already has Exa, Perplexity, Parallel,
Tavily and Brave; the overlay adds Expand, Firecrawl and DeepSeek (`bakeoff/expand.py`,
`bakeoff/firecrawl.py`, `bakeoff/deepseek.py`). Follow one of those files:

1. **Adapter** `bakeoff/<provider>.py`: subclass `harness.searchers.Searcher`, set `name`, implement
   `async run(query, num_results, *, objective=None, search_queries=None) -> SearchResponse` (and
   `search()` returning `.results`). Each result is a `SearchResult(url, title, text | highlights,
   metadata={"rank", "published_date", ...})`; the evidence the answer model sees is `highlights`
   when present, else `text`. Report `cost_usd` (provider-reported where available, else the list
   price; `None` only if unknown), `latency_ms`, `queries` and `request_id`. Read the key from the
   environment in `__init__` and fail there if it is missing, so preflight catches it before any
   paid call. Send requests through `bakeoff._http.post_with_backoff` (shared by the Expand, Firecrawl and DeepSeek adapters: 408, 429, 5xx and transport errors retried with backoff by default, `Retry-After` honoured, one error-message format; Expand passes its own set, 429/502/503/504, and does not retry 500); do not retry other 4xx. Keep response-body validation in the adapter. Never print the key.
2. **Registration** `bakeoff/register.py`: add the class to `PROVIDERS` and its environment variable(s)
   to `PROVIDER_KEYS` (a tuple; several names are joined with "or" in preflight output).
3. **Catalog** `bakeoff/systems.toml`: `[searchers.<name>]` with `provider = "<provider>"` and the
   request options, then `[systems.rag-<name>]` with `kind = "rag"` and `searcher = "<name>"`. Do not
   add a `[defaults]` table and do not reuse an upstream name; both are rejected at load time.
4. **Tests** `tests/test_<provider>.py`, mirroring `tests/test_expand.py` with an `httpx.MockTransport`:
   request shape and endpoint, key from the environment and from `api_key=`, missing key fails before
   any request, result-to-citation mapping, result count never exceeds the request, cost, empty
   results, permanent errors not retried, transient errors retried then raised, malformed body is an
   error. `tests/test_registration.py` and `tests/test_comparators.py` show the registration, catalog
   and dry-run assertions to add; `test_official_suite_runs_comparators_with_the_leak_filter` is the
   template for running a new system through an official suite offline.
5. **Runners**: add the system to `WEBCODE_SYSTEMS` and `OFFICIAL_SYSTEMS` in the `Makefile`; add a
   `SystemDef` in `aa-stirrup/aastirrup/systems.py` (set `evidence_chars` only for providers that
   return page text rather than snippets) and the name to `AA_SYSTEMS`; add the key to `.env.example` with its pricing
   basis, and a row to the systems table in `README.md` and the pricing table in `METHODOLOGY.md`.
6. **Preflight before paying**: `./bench run --suite webcode-rag --system rag-<name> --dry-run` must
   name the missing variable with no key set and pass with one. Then `LIMIT=5 runs/run-suite.sh
   webcode-rag rag-<name>` as a smoke, then the full suite in the same window as the rows you compare
   against (`runs/run-suite.sh webcode-rag rag-<name> rag-perplexity-fast ...`).

## Adding a suite

- A **loader** pins a Hugging Face revision and a file SHA-256 (`bakeoff/suites.py`,
  `load_simpleqa_verified`, `load_sealqa`, `load_aa_omniscience`); the suite's `revision` string
  carries the pin plus a grader version tag so run-directory hashes change when either changes.
- An **official-grader suite** (`bakeoff/official_suites.py`) subclasses the loader suite, names its
  judge model and refuses any other, declares an `AnswerProtocol` (neutral prompt, reasoning effort) so
  `bakeoff/official_rag.py` takes over execution, and implements `grade` with a grader from
  `bakeoff/official_graders.py` whose prompt lives verbatim in `bakeoff/official_prompts.py` **and**
  in `METHODOLOGY.md` Appendix A; `tests/test_official.py` asserts the two are byte-identical.
- Register the suite in `bakeoff/register.py` (`register_suites`, collision-checked), add the dataset
  to `make download`, add tests (`tests/test_suites.py`, `tests/test_official.py`), a run target in
  the `Makefile`, and a section in `METHODOLOGY.md` with the official protocol, its source, what is
  run and every deviation.

## Results: layout, storage, redaction

- A harness run writes `runs/<suite>/<system>-<suite>-<hash>/` with `config.json`, `summary.json` and
  `tasks/<task-id>/{result,grade,cost}.json` (`error.json` on failure), plus a per-system summary
  `runs/<suite>/<system>.json` with bootstrap CIs. The Stirrup runners write one JSON per
  (system, question) under `aa-stirrup/runs/<run>/<system>/`.
- `make report` prints the harness tables and updates their JSON summaries; `make paired index` rewrites
  the README's paired and index tables; `runs/official/assemble.py` refreshes `runs/official/RESULTS.md`;
  after AA setup, `./aa-stirrup/aa report --run aa-stirrup/runs/full-600` refreshes the AA summary. The
  other README tables are copied from these reports; update them in the same commit.
- A harness run's directory hash covers the upstream system, suite and judge configuration plus the
  Expand endpoint, model transport and overlay source digest. AA stores a per-system `run-config.json`
  and refuses to resume a folder whose settings differ. The report readers reject two runs of the same
  system and suite, so start a new output directory for live reruns.
- **Committed records are immutable.** Never edit a number, a grade or a record under `runs/` or
  `aa-stirrup/runs/`. Add a new run directory; if a stored number turns out to be wrong, say so next to it and add the corrected run beside it.
- **Before committing a run.** Stored records keep questions, answers, judge labels and reasoning,
  scores, costs, latencies and per-record citation counts and evidence-token totals; per-result URLs,
  titles and text are removed (`runs/EXCLUDED.md`). A fresh run writes full records, so run, in order:
  `.venv/bin/python -I tools/strip_result_details.py` (reduces `result.json`, `grade.json` and the AA
  records to those fields; it counts any remaining citation text with tiktoken), then
  `python3 -I tools/scrub_presigned_urls.py`, which replaces the query string of any presigned S3/CDN
  or Azure SAS URL left in answers, errors or logs with `?<presigned-params-redacted>`, and
  `python3 -I tools/scrub_paths.py`, which replaces absolute machine paths in tracebacks and logs with
  `<repo>` / `<home>` / `<venv>`. CI runs the first and last with `--check` (`make scrub-check`). Check
  `git diff --stat` for `.env`, `logs/` with key material, or anything larger than a few MB before committing.
- Never commit `.env`; the root `.gitignore` covers it, the caches and the pinned clones.

## Style

The overlay package is still called `bakeoff` (its working name) rather than something like `search_benchmarks`:
the committed run records name it in error tracebacks, log lines and the run scripts, and those records are
immutable, so renaming the package would leave them pointing at a module that no longer exists.

Python 3.12, `uv`, `pytest` with `@pytest.mark.asyncio` in auto mode. Prefer small, offline, fast
tests with mocked transports. Keep upstream byte-identical (`PYTHONDONTWRITEBYTECODE=1` is set by
every wrapper so no `.pyc` lands in `upstream/`). Document every deviation from an official protocol in
`METHODOLOGY.md` in the same commit as the code.
