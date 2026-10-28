"""Run the harness's ``openai/<model>`` answer and judge calls through OpenRouter.

Upstream's ``OpenAIClient`` speaks the OpenAI Responses API with a direct OpenAI
key. This client keeps the same harness model names (``openai/gpt-5.6-luna``,
``openai/gpt-6-luna``), while sending calls to OpenRouter's Chat Completions endpoint instead.
The overlay's provenance guard records the transport and endpoint in new run
configurations so they cannot share resumable records with the direct route. Differences from the direct route that matter for results:

* Transport is Chat Completions (``messages``), not Responses (``instructions`` +
  ``input``). System prompts travel as ``system`` messages.
* Structured output is ``response_format: {type: json_schema, strict: true}`` with
  ``provider.require_parameters = true``, so OpenRouter only picks a provider that
  enforces the schema (routing metadata is retained when the response supplies it).
* Reasoning effort is forwarded as ``reasoning.effort`` when the harness sets one.
  The WebCode defaults leave effort unset; official suites may set it explicitly.
  API defaults need not be identical between Chat Completions and Responses.
* Cost is the ``usage.cost`` OpenRouter reports for the call (USD at provider
  list price), falling back to the harness's own pricing table only when the
  field is missing. ``Generation.raw`` records both numbers.

``install()`` swaps the client in wherever upstream bound ``create_client`` and
points the ``openai`` credential preflight at the OpenRouter key. Upstream files
are not edited.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
from harness import cli, rag, scout
from harness.llm import clients, judge
from harness.llm.clients import ModelClient
from harness.llm.openai import supports_reasoning
from harness.llm.pricing import token_cost
from harness.llm.types import ContextWindowExceeded, Generation, ToolCall, Usage

logger = logging.getLogger(__name__)

TRANSPORT_ENV = "BAKEOFF_LLM_TRANSPORT"  # "openai" (upstream, default) or "openrouter"
KEY_ENV = ("OPENROUTER_API_KEY", "OPEN_ROUTER_API_KEY")
BASE_URL_ENV = "OPENROUTER_BASE_URL"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

RETRY_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_CONTEXT_ERROR = re.compile(r"context_length_exceeded|maximum context length|context window", re.I)


class OpenRouterError(RuntimeError):
    """A non-retryable, or retried-out, OpenRouter response."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"OpenRouter {status}: {body[:500]}")
        self.status = status


@dataclass
class TransportStats:
    """In-process counters for the run report; reset by ``install``."""

    calls: int = 0
    retries: int = 0
    failures: int = 0
    cost_usd: float = 0.0
    retried_statuses: dict[str, int] = field(default_factory=dict)

    def note_retry(self, reason: str) -> None:
        self.retries += 1
        self.retried_statuses[reason] = self.retried_statuses.get(reason, 0) + 1

    def summary(self) -> str:
        reasons = ", ".join(f"{k}×{v}" for k, v in sorted(self.retried_statuses.items()))
        return (
            f"openrouter: {self.calls} calls, {self.retries} retries"
            f"{f' ({reasons})' if reasons else ''}, {self.failures} failed, "
            f"${self.cost_usd:.4f} reported cost"
        )


STATS = TransportStats()


def api_key() -> str:
    for name in KEY_ENV:
        value = os.environ.get(name)
        if value:
            return value
    raise ValueError(f"set {' or '.join(KEY_ENV)} to use the OpenRouter transport")


def parse_usage(body: dict[str, Any]) -> Usage:
    """Map Chat Completions usage; cached tokens are a subset of prompt tokens."""
    usage = body.get("usage") or {}
    return Usage(
        input_tokens=usage.get("prompt_tokens") or 0,
        output_tokens=usage.get("completion_tokens") or 0,
        cached_input_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0,
        reasoning_tokens=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        or 0,
    )


def parse_message(body: dict[str, Any]) -> tuple[str, list[ToolCall], list[str]]:
    """Extract the reply text, function calls and any reasoning text."""
    choices = body.get("choices") or []
    if not choices:
        raise OpenRouterError(200, f"no choices in response: {json.dumps(body)[:300]}")
    choice = choices[0]
    if choice.get("error"):
        raise OpenRouterError(200, f"provider error: {json.dumps(choice['error'])}")
    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, list):  # some providers return content parts
        content = "".join(part.get("text") or "" for part in content if isinstance(part, dict))
    text = content or ""
    tool_calls = [
        ToolCall(
            call.get("id") or "",
            (call.get("function") or {}).get("name") or "",
            (call.get("function") or {}).get("arguments") or "",
        )
        for call in message.get("tool_calls") or []
    ]
    reasoning: list[str] = []
    if message.get("reasoning"):
        reasoning.append(str(message["reasoning"]))
    for detail in message.get("reasoning_details") or []:
        if isinstance(detail, dict) and detail.get("summary"):
            reasoning.append(str(detail["summary"]))
    return text, tool_calls, reasoning


class OpenRouterClient(ModelClient):
    """``openai/<model>`` through ``POST {base_url}/chat/completions`` on OpenRouter."""

    provider = "openai"
    supports_response_schema = True

    def __init__(
        self,
        model: str,
        *,
        timeout: float = 900.0,
        max_retries: int = 3,
        client: httpx.AsyncClient | None = None,
        base_url: str | None = None,
    ) -> None:
        super().__init__(model)
        self.max_retries = max_retries
        self.base_url = (base_url or os.environ.get(BASE_URL_ENV) or DEFAULT_BASE_URL).rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=timeout)
        # The harness's ``openai/<model>`` names are already OpenRouter model ids.
        self.openrouter_model = f"openai/{self.model_name}"

    def build_request(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None,
        hosted_web_search: dict[str, Any] | None,
        max_output_tokens: int | None,
        temperature: float | None,
        reasoning_effort: str | None,
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build the Chat Completions JSON body for one call."""
        if hosted_web_search is not None:
            raise ValueError(
                "hosted web search is an OpenAI Responses feature; the OpenRouter "
                "transport only serves RAG answers and judges"
            )
        request: dict[str, Any] = {
            "model": self.openrouter_model,
            "messages": messages,
            "provider": {"require_parameters": True},
            "usage": {"include": True},
        }
        if tools:
            request["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool["parameters"],
                        **({"strict": tool["strict"]} if "strict" in tool else {}),
                    },
                }
                for tool in tools
            ]
        if max_output_tokens is not None:
            request["max_tokens"] = max_output_tokens
        if supports_reasoning(self.model_name):
            if reasoning_effort:
                request["reasoning"] = {"effort": reasoning_effort}
        elif temperature is not None:
            request["temperature"] = temperature
        if response_schema is not None:
            request["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema["name"],
                    "strict": True,
                    "schema": response_schema["schema"],
                },
            }
        return request

    async def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        hosted_web_search: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
        reasoning_effort: str | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> Generation:
        request = self.build_request(
            messages,
            tools=tools,
            hosted_web_search=hosted_web_search,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            response_schema=response_schema,
        )
        body, attempts = await self._post(request)
        text, tool_calls, reasoning = parse_message(body)
        usage = parse_usage(body)
        reported = (body.get("usage") or {}).get("cost")
        table_cost = token_cost(self.model, usage, cached_included_in_input=True)
        cost = float(reported) if reported is not None else table_cost
        if cost is not None:
            STATS.cost_usd += cost
        return Generation(
            text=text,
            tool_calls=tool_calls,
            hosted_search=None,
            usage=usage,
            cost_usd=cost,
            reasoning=reasoning,
            raw={
                "response": body,
                "transport": {
                    "name": "openrouter",
                    "model": self.openrouter_model,
                    "attempts": attempts,
                    "reported_cost_usd": reported,
                    "table_cost_usd": table_cost,
                },
            },
        )

    async def _post(self, request: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """POST with retries on 429/5xx/network errors. Returns the body and attempt count."""
        headers = {
            "Authorization": f"Bearer {api_key()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://expand.ai",
            "X-Title": "expand search bakeoff",
        }
        url = f"{self.base_url}/chat/completions"
        STATS.calls += 1
        last: str = ""
        for attempt in range(1, self.max_retries + 2):
            try:
                response = await self._client.post(url, json=request, headers=headers)
            except httpx.TransportError as error:
                last = f"{type(error).__name__}: {error}"
                reason = type(error).__name__
                status = None
            else:
                status = response.status_code
                if status == 200:
                    body = response.json()
                    if body.get("error"):  # OpenRouter can wrap provider errors in a 200
                        error = body["error"]
                        code = error.get("code") if isinstance(error, dict) else None
                        if isinstance(code, int) and code in RETRY_STATUSES:
                            last = json.dumps(error)[:500]
                            reason = str(code)
                        else:
                            STATS.failures += 1
                            raise OpenRouterError(200, json.dumps(error))
                    else:
                        return body, attempt
                else:
                    last = response.text
                    reason = str(status)
                    if status not in RETRY_STATUSES:
                        STATS.failures += 1
                        if status == 400 and _CONTEXT_ERROR.search(last):
                            raise ContextWindowExceeded(last[:500])
                        raise OpenRouterError(status, last)
            if attempt > self.max_retries:
                break
            delay = _retry_delay(attempt, response.headers if status is not None else None)
            STATS.note_retry(reason)
            logger.warning(
                "openrouter %s attempt %d/%d failed (%s); retrying in %.1fs",
                self.openrouter_model,
                attempt,
                self.max_retries + 1,
                reason,
                delay,
            )
            await asyncio.sleep(delay)
        STATS.failures += 1
        raise OpenRouterError(status or 0, f"gave up after {self.max_retries + 1} attempts: {last}")


def _retry_delay(attempt: int, headers: httpx.Headers | None) -> float:
    if headers is not None:
        retry_after = headers.get("retry-after")
        if retry_after:
            try:
                return min(60.0, max(0.0, float(retry_after)))
            except ValueError:
                pass
    return min(30.0, 2.0 ** (attempt - 1)) + random.uniform(0, 0.5)


def transport_from_env() -> str:
    value = (os.environ.get(TRANSPORT_ENV) or "openai").strip().lower()
    if value not in ("openai", "openrouter"):
        raise ValueError(f"{TRANSPORT_ENV} must be 'openai' or 'openrouter', got {value!r}")
    return value


_upstream_create_client = clients.create_client
_upstream_openai_keys = cli.PROVIDER_KEYS["openai"]
_CREATE_CLIENT_BINDINGS = (clients, judge, rag, scout)


def create_client(model: str, **options: Any) -> ModelClient:
    """``create_client`` with ``openai/*`` served by OpenRouter."""
    if clients.provider_of(model) == "openai":
        return OpenRouterClient(model, **options)
    return _upstream_create_client(model, **options)


def install() -> None:
    """Route ``openai/*`` through OpenRouter and reset ``STATS``. Idempotent: a repeat call keeps both."""
    global STATS
    if is_installed():
        return
    STATS = TransportStats()
    for module in _CREATE_CLIENT_BINDINGS:
        module.create_client = create_client  # type: ignore[attr-defined]
    cli.PROVIDER_KEYS["openai"] = KEY_ENV


def uninstall() -> None:
    """Restore upstream's direct OpenAI route."""
    for module in _CREATE_CLIENT_BINDINGS:
        module.create_client = _upstream_create_client  # type: ignore[attr-defined]
    cli.PROVIDER_KEYS["openai"] = _upstream_openai_keys


def is_installed() -> bool:
    return clients.create_client is create_client


def install_if_configured() -> bool:
    """Apply ``BAKEOFF_LLM_TRANSPORT``; returns whether OpenRouter is now active."""
    if transport_from_env() == "openrouter":
        install()
        return True
    uninstall()
    return False
