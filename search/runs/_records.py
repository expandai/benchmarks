"""Shared readers for the stored run records: the report scripts and ``paired.py`` import this.

A harness run directory is ``<system>-<suite>-<hash>/`` with ``config.json`` and
``tasks/<task>/{result,grade,cost,error}.json``; OpenRouter transport counters are the last line of
each ``bench`` pass in ``logs/<system>.log``. CIs use upstream's ``harness.statistics.bootstrap_mean``
(percentile bootstrap over tasks, 10,000 resamples, seed 0), so they match ``summary.json``.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

RUNS = Path(__file__).resolve().parent
BAKEOFF_ROOT = RUNS.parent
sys.dont_write_bytecode = True  # keep the pinned upstream tree byte-identical
for _path in (BAKEOFF_ROOT / "upstream", BAKEOFF_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
from harness.statistics import bootstrap_mean  # noqa: E402

from bakeoff.pricing import LIST_PRICE_PER_SEARCH, search_usd  # noqa: E402

# Row order of every generated table and report.json; systems not listed sort last, by name.
SYSTEM_ORDER = (
    "rag-model-only",
    "rag-expand",
    "rag-perplexity-fast",
    "rag-perplexity-web",
    "rag-exa-fast-highlights",
    "rag-exa-instant-highlights",
    "rag-exa-webcode",
    "rag-exa-lite-highlights",
    "rag-exa-auto-highlights",
    "rag-parallel-turbo",
    "rag-parallel-fast",
    "rag-firecrawl-search",
    "rag-deepseek",
    "rag-tavily-advanced",
    "rag-brave-llm-context",
)
STATS_LINE = re.compile(
    r"openrouter: (\d+) calls, (\d+) retries(?: \(([^)]*)\))?, (\d+) failed, \$([0-9.]+) reported cost"
)


def read(path: Path) -> Any:
    return json.loads(path.read_text())


def read_all(paths: list[Path]) -> list[Any]:
    """Read the files that exist; a run in progress may move or rewrite one mid-scan."""
    out = []
    for path in paths:
        try:
            out.append(read(path))
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    return out


def citation_count(result: dict[str, Any]) -> int:
    """Citations in a ``result.json``. Stored records keep only ``num_citations`` (runs/EXCLUDED.md);
    a fresh run's records carry the ``citations`` list."""
    if "citations" in result:
        return len(result["citations"])
    return int(result.get("num_citations", 0))


def filtered_by_reason(result: dict[str, Any]) -> dict[str, int]:
    """Leak-filter drops in a ``result.json`` by reason, from ``filtered_results`` (fresh run) or the
    stored ``filtered_results_by_reason`` counts."""
    if "filtered_results" in result:
        counts: dict[str, int] = {}
        for dropped in result["filtered_results"]:
            reason = dropped.get("reason", "?")
            counts[reason] = counts.get(reason, 0) + 1
        return counts
    return dict(result.get("filtered_results_by_reason", {}))


def searcher_name(config: dict[str, Any]) -> str | None:
    """Catalog searcher of a run's ``config.json`` (``None`` for the no-search baseline)."""
    return (config["system"].get("searcher") or {}).get("name")


def result_search_usd(searcher: str | None, result: dict[str, Any]) -> float:
    """Search cost of a ``result.json``, list-priced for the searchers in ``bakeoff.pricing``.

    A RAG task makes one search request, billed when its stored cost is non-zero."""
    recorded = float(result.get("search_cost_usd", 0.0))
    if searcher in LIST_PRICE_PER_SEARCH and len(result.get("search_queries", [])) > 1:
        raise ValueError(f"{searcher}: task {result.get('task_id')} has more than one search request")
    return search_usd(searcher, recorded, 1 if recorded > 0 else 0)


def mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def p90(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[int(0.9 * (len(ordered) - 1))] if ordered else 0.0


def ci(values: list[float]) -> dict[str, float | None] | None:
    if not values:
        return None
    interval = bootstrap_mean(values)
    return {"mean": interval.estimate, "low": interval.low, "high": interval.high}


def pct(interval: dict[str, Any] | None, unit: str = "") -> str:
    """``mean [low–high]`` in percent; ``unit`` follows the mean (``"%"`` in the WebCode tables)."""
    if not interval or interval.get("mean") is None:
        return "—"
    if interval.get("low") is None:
        return f"{interval['mean'] * 100:.1f}{unit}"
    return f"{interval['mean'] * 100:.1f}{unit} [{interval['low'] * 100:.1f}–{interval['high'] * 100:.1f}]"


def transport(log_dir: Path, system: str) -> dict[str, Any]:
    """Sum the OpenRouter counters over every pass logged for ``system``."""
    path = log_dir / f"{system}.log"
    out: dict[str, Any] = {"calls": 0, "retries": 0, "failed_calls": 0, "reported_cost_usd": 0.0}
    if path.exists():
        for match in STATS_LINE.finditer(path.read_text()):
            out["calls"] += int(match.group(1))
            out["retries"] += int(match.group(2))
            out["failed_calls"] += int(match.group(4))
            out["reported_cost_usd"] += float(match.group(5))
    return out


def task_dirs(run_dir: Path) -> list[Path]:
    task_root = run_dir / "tasks"
    return sorted(p for p in task_root.iterdir() if p.is_dir()) if task_root.exists() else []


def run_dirs(roots: list[Path], suite: str) -> dict[str, tuple[Path, Path]]:
    """System name -> (run directory, the root it was found in) for ``suite``.

    Each system must have exactly one run across the supplied roots. Ambiguous reruns are
    rejected so filesystem ordering cannot silently choose which measurements get published.
    """
    found: dict[str, tuple[Path, Path]] = {}
    for root in roots:
        if not root.exists():
            continue
        for run_dir in sorted(root.iterdir()):
            config_path = run_dir / "config.json"
            if not config_path.exists():
                continue
            config = read(config_path)
            name = config["system"]["name"]
            if config["suite"] != suite:
                continue
            if name in found:
                previous = found[name][0]
                raise ValueError(
                    f"Ambiguous runs for suite {suite!r}, system {name!r}: {previous} and {run_dir}. "
                    "Select exactly one run per system in the report roots; keep reruns in a separate output root."
                )
            found[name] = (run_dir, root)
    return found


def by_system_order(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order = {name: i for i, name in enumerate(SYSTEM_ORDER)}
    return sorted(rows, key=lambda r: (order.get(r["system"], 99), r["system"]))
