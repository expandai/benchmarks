# Evidence read for the AA-Omniscience reproduction

Artificial Analysis' pages were read on 2026-10-26 and are summarised in `../../README.md` ("AA's
methodology as published"). Verbatim copies of the pages are not kept in this repository; read them
at the source or in the Internet Archive (snapshots nearest the read date, located with the Wayback
Machine availability API):

| Page | URL | Read | Archived copy |
|---|---|---|---|
| Search-API benchmarking methodology | https://artificialanalysis.ai/methodology/search-api | 2026-10-26 | https://web.archive.org/web/20261021010716/https://artificialanalysis.ai/methodology/search-api (2026-10-21) |
| Launch article, "Announcing the Artificial Analysis Search Index: Same Agent, Different Search" (2026-08-18) | https://artificialanalysis.ai/articles/search-api | 2026-10-26 | https://web.archive.org/web/20260910005608/https://artificialanalysis.ai/articles/search-api (2026-09-10) |
| Leaderboard (first 12 server-rendered rows) | https://artificialanalysis.ai/agents/search-api | 2026-10-26 | https://web.archive.org/web/20261016152228/https://artificialanalysis.ai/agents/search-api (2026-10-16) |
| Intelligence-benchmarking methodology (grader history) | https://artificialanalysis.ai/methodology/intelligence-benchmarking | 2026-10-26 | https://web.archive.org/web/20261027172121/https://artificialanalysis.ai/methodology/intelligence-benchmarking (2026-10-27) |
| AA-Omniscience paper, Appendix A.1/A.2 | https://arxiv.org/html/2511.13029v1 | 2026-10-26 | arXiv is the archive |

Files kept here:

- `grader_prompt_from_paper.txt`: the paper's Appendix A.2 grader prompt as extracted (the copy the
  runner uses is `../../aastirrup/grader_prompt.txt`, SHA-256 pinned by a test).
- `preflight.txt`: `./aa preflight` output captured on 2026-10-26, before later systems were added
  (one live search per system then configured; the Perplexity quota error noted in the README).
- `pytest.txt`: offline test output captured on 2026-10-26, before later systems and tests were added.
- `venv-versions.txt`: installed package versions.
