"""List prices the report generators apply to billed searches.

The published tables price each search of a searcher listed here at its current list price,
counting billed searches in the stored records (a search is billed when its stored cost is
non-zero; Expand refunds a search that found nothing). Every other searcher's cost is the stored
per-search cost (provider-reported or the adapter's list price). Stored records are never
rewritten, and stored and fresh runs are priced alike.

Expand is priced at its list price of $1.50 per 1,000 searches (2026-10-28).
"""

from __future__ import annotations

from .expand import EXPAND_SEARCH_COST_PER_REQUEST

# Catalog searcher name -> list price in USD per billed search.
LIST_PRICE_PER_SEARCH: dict[str, float] = {"expand": EXPAND_SEARCH_COST_PER_REQUEST}


def search_usd(searcher: str | None, recorded_usd: float, billed_searches: int) -> float:
    """Search cost of a record: billed searches at list price for a listed searcher, else as recorded."""
    price = LIST_PRICE_PER_SEARCH.get(searcher or "")
    return recorded_usd if price is None else billed_searches * price
