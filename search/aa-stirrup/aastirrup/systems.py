"""The search systems under test: each is a bakeoff catalog searcher, built by the bakeoff's own registry.

``register.install()`` adds the Expand, Firecrawl and DeepSeek providers and merges
``bakeoff/systems.toml`` into the pinned Exa catalog; Exa, Perplexity, Parallel, Tavily and Brave come
from upstream. Searcher options (tier, mode, highlights, search depth) are exactly the catalog's.

``evidence_chars`` caps the ``description`` of each rendered result for providers that return page
text rather than snippets (Brave LLM Context: up to ``max_tokens_per_url`` = 4,096 tokens per URL) at
4,000 characters per page. Without it ten Brave results would
exceed Stirrup's 40,000-character tool-result cap and be middle-truncated as a block. Snippet
providers are left uncapped, exactly as in the stored runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harness.searchers import Searcher

MODEL_ONLY = "model-only"


@dataclass(frozen=True)
class SystemDef:
    name: str
    searcher: str | None  # catalog searcher name; None = AA's model_only baseline
    concurrency: int
    label: str
    evidence_chars: int | None = None  # per-result cap on the rendered description (None = no cap)


SYSTEMS: dict[str, SystemDef] = {
    s.name: s
    for s in (
        SystemDef("expand", "expand", 5, "Expand Search"),  # POST /v1/search
        SystemDef("perplexity-fast", "perplexity-fast", 10, "Perplexity fast"),
        SystemDef("perplexity-web", "perplexity-web", 10, "Perplexity web"),
        SystemDef("exa-fast-highlights", "exa-fast-highlights", 10, "Exa fast highlights"),
        SystemDef("exa-lite-highlights", "exa-lite-highlights", 10, "Exa lite highlights"),
        SystemDef("exa-auto-highlights", "exa-auto-highlights", 10, "Exa auto highlights"),
        SystemDef("parallel-turbo", "parallel-turbo", 10, "Parallel turbo"),
        SystemDef("parallel-fast", "parallel-fast", 10, "Parallel fast"),
        SystemDef("firecrawl-search", "firecrawl-search", 10, "Firecrawl search"),
        SystemDef("deepseek", "deepseek", 5, "DeepSeek"),
        # Comparators from the upstream catalog: TAVILY_API_KEY; BRAVE_SEARCH_API_KEY or BRAVE_API_KEY.
        SystemDef("tavily-advanced", "tavily-advanced", 10, "Tavily (advanced)"),
        SystemDef("brave-llm-context", "brave-llm-context", 10, "Brave (LLM context)", evidence_chars=4000),
        SystemDef(MODEL_ONLY, None, 10, "Model only (no search)"),
    )
}


def searcher_entry(name: str) -> dict[str, Any]:
    """The catalog entry (provider + options) for a system's searcher."""
    from bakeoff import register
    from harness.systems import Catalog

    register.install()
    catalog = Catalog.load()
    searcher = SYSTEMS[name].searcher
    if searcher is None:
        raise ValueError(f"{name} has no searcher")
    return dict(catalog.searchers[searcher])


def build_searcher(name: str) -> Searcher:
    from harness import systems

    entry = searcher_entry(name)
    provider = entry.pop("provider")
    return systems.build_searcher(provider, entry)
