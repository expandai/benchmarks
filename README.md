# Expand benchmarks

Reproducible public benchmarks published by Expand, with the harness, the per-task run records and the
methodology for each. Each benchmark documents its protocol, its adaptations and the commands that
regenerate its tables from the stored records. Repository: https://github.com/expandai/benchmarks.

| Benchmark | What it measures | Directory |
|---|---|---|
| Search APIs for agents | Web-search APIs (Expand, Exa, Perplexity, Parallel, Firecrawl, DeepSeek, Tavily, Brave) on WebCode RAG, SimpleQA Verified, SealQA, FRAMES and AA-Omniscience | [`search/`](search/) |

## Running a benchmark

Each directory is self-contained: `cd` into it and follow its README. For the search benchmark:

```sh
git clone https://github.com/expandai/benchmarks && cd benchmarks/search
make upstream venv test     # pinned harness clone, venv, offline tests (no keys needed)
make report paired index    # recompute harness reports and comparison tables from stored records
```

The root `Makefile` forwards any target to `search/` (`make test` here is `make -C search test`). The
GitHub Actions workflow in `.github/workflows/` runs each benchmark's offline tests on every push.

## License

MIT for everything written here ([`LICENSE`](LICENSE)), which also lists the third-party material each
benchmark pins or redistributes.
