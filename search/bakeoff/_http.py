"""The POST-with-backoff loop the Expand, Firecrawl and DeepSeek adapters share.

Transport errors (timeouts included) and the retryable statuses (408, 429 and 5xx gateway
errors by default) are retried with exponential backoff, 1 s, 2 s, 4 s, …, or the response's
``Retry-After`` seconds when longer. Any other non-2xx status, or the last attempt's failure,
raises: ``httpx.HTTPStatusError("<Provider> API error <status>: <body[:500]>")`` for a status,
the transport error itself otherwise. Each adapter validates its own success body.
"""

from __future__ import annotations

import asyncio
from collections.abc import Collection
from typing import Any

import httpx

RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})


def retry_delay(attempt: int, response: httpx.Response | None) -> float:
    """``2 ** attempt`` seconds, or the response's ``Retry-After`` seconds when longer."""
    delay = 2.0**attempt
    retry_after = response.headers.get("retry-after") if response is not None else None
    if retry_after:
        try:
            delay = max(delay, float(retry_after))
        except ValueError:
            pass  # an HTTP-date Retry-After; keep the exponential delay
    return delay


async def post_with_backoff(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    provider: str,
    max_attempts: int,
    retryable: Collection[int] = RETRYABLE_STATUS,
) -> httpx.Response:
    """POST ``payload`` as JSON and return the first 2xx response."""
    for attempt in range(max_attempts):
        final = attempt == max_attempts - 1
        response: httpx.Response | None = None
        try:
            response = await client.post(url, headers=headers, json=payload)
        except (httpx.TimeoutException, httpx.TransportError):
            if final:
                raise
        else:
            if response.is_success:
                return response
            if response.status_code not in retryable or final:
                raise httpx.HTTPStatusError(
                    f"{provider} API error {response.status_code}: {response.text[:500]}",
                    request=response.request,
                    response=response,
                )
        await asyncio.sleep(retry_delay(attempt, response))
    raise AssertionError("unreachable")
