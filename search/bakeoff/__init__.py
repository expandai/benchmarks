"""The search bakeoff's overlay on the pinned exa-labs/benchmarks harness, registered without upstream edits.

Searchers: Expand, Firecrawl and DeepSeek adapters plus the no-search ``none`` baseline
(``register``); suites: SimpleQA Verified, SealQA and AA-Omniscience on upstream's graders
(``suites``) and the official-grader suites (``official_*``); an optional OpenRouter
transport for the ``openai/*`` answer and judge calls (``openrouter``).
"""
