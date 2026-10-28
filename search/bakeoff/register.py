"""Register the Expand, Firecrawl and DeepSeek searchers and the extra suites with the pinned
harness, without editing it.

The harness has three closed lists a new provider must join:

* ``harness.systems.build_searcher`` maps a catalog ``provider`` to a class;
* ``harness.cli.PROVIDER_KEYS`` names each provider's credential for preflight;
* ``Catalog.load`` reads exactly one TOML file.

``install()`` wraps the first, adds to the second and makes every catalog load
also merge ``bakeoff/systems.toml``. It also adds the overlay suites
(``bakeoff/suites.py``) to ``benchmarks.SUITES``, the dict behind ``get_suite`` and
``list_suites``. Upstream entries are never overridden: a name
collision, or an overlay ``[defaults]`` table, is an error, so shared settings
(answering model, ``num_results = 10``) stay exactly as upstream ships them.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import benchmarks
import tomllib
from harness import cli, systems
from harness.searchers import Searcher
from harness.systems import Catalog

from . import openrouter, provenance
from .deepseek import DeepSeekSearcher
from .expand import DEFAULT_BASE_URL, ExpandSearcher
from .firecrawl import FirecrawlSearcher
from .official_rag import NULL_PROVIDER, NullSearcher
from .official_rag import install as install_official_execution
from .official_suites import SUITES as OFFICIAL_SUITES
from .suites import SUITES as OVERLAY_SUITES

OVERLAY_CATALOG = Path(__file__).with_name("systems.toml")

PROVIDERS: dict[str, Any] = {
    "expand": ExpandSearcher,
    "firecrawl": FirecrawlSearcher,
    "deepseek": DeepSeekSearcher,
    NULL_PROVIDER: NullSearcher,
}
PROVIDER_KEYS = {
    "expand": ("EXPAND_API_KEY",),
    "firecrawl": ("FIRECRAWL_API_KEY",),
    "deepseek": ("DEEPSEEK_API_KEY",),
    NULL_PROVIDER: (),  # no credential; official_rag.install drops the empty preflight entry
}

_installed = False


def load_overlay(path: Path = OVERLAY_CATALOG) -> dict[str, Any]:
    with open(path, "rb") as handle:
        overlay = tomllib.load(handle)
    unknown = set(overlay) - {"searchers", "systems"}
    if unknown:
        raise ValueError(
            f"overlay catalog may only add searchers and systems, not {sorted(unknown)}"
        )
    return overlay


def merge_overlay(catalog: Catalog, overlay: dict[str, Any]) -> Catalog:
    """Add overlay searchers and systems to ``catalog``, refusing to replace any."""
    for table in ("searchers", "systems"):
        existing: dict[str, Any] = getattr(catalog, table)
        for name, entry in overlay.get(table, {}).items():
            if name in existing:
                if existing[name] == entry:
                    continue
                raise ValueError(
                    f"overlay {table[:-1]} {name!r} collides with the upstream catalog"
                )
            existing[name] = copy.deepcopy(entry)
    return catalog


def install() -> None:
    """Patch the harness in-process. Idempotent.

    The answer/judge transport (``BAKEOFF_LLM_TRANSPORT``) is re-read on every call,
    so a process can switch it with the environment; see ``bakeoff.openrouter``.
    """
    global _installed
    openrouter.install_if_configured()
    if _installed:
        return
    upstream_build = systems.build_searcher

    def build_searcher(provider: str, options: dict[str, Any]) -> Searcher:
        if provider in PROVIDERS:
            return PROVIDERS[provider](**dict(options))
        return upstream_build(provider, options)

    systems.build_searcher = build_searcher
    for provider, names in PROVIDER_KEYS.items():
        cli.PROVIDER_KEYS.setdefault(provider, names)

    upstream_load = Catalog.load.__func__  # type: ignore[attr-defined]
    overlay = load_overlay()

    def load(cls: type[Catalog], path: Path | str = systems.DEFAULT_CATALOG) -> Catalog:
        catalog = merge_overlay(upstream_load(cls, path), overlay)
        # A non-default EXPAND_SEARCH_BASE_URL enters the resolved spec (and the run hash).
        for entry in catalog.searchers.values():
            if entry.get("provider") == "expand":
                entry.setdefault("base_url", (os.getenv("EXPAND_SEARCH_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"))
        return catalog

    Catalog.load = classmethod(load)  # type: ignore[method-assign]
    register_suites()
    install_official_execution()
    provenance.install()
    _installed = True


def register_suites() -> None:
    """Add the overlay suites to the upstream registry, refusing to replace any."""
    for name, suite in {**OVERLAY_SUITES, **OFFICIAL_SUITES}.items():
        existing = benchmarks.SUITES.get(name)
        if existing is not None and existing is not suite:
            raise ValueError(f"overlay suite {name!r} collides with an upstream suite")
        benchmarks.SUITES[name] = suite


def added_systems() -> list[str]:
    """System names the overlay adds, for help text."""
    return sorted(load_overlay().get("systems", {}))
