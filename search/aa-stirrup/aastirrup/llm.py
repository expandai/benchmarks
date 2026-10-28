"""Answer and grader models through OpenRouter, with per-call usage and USD cost recorded.

AA: candidate model GPT-5.6 Luna (medium), max output 127,999 tokens; grader GPT-5.6 Luna (medium)
(https://artificialanalysis.ai/methodology/search-api). Both go through OpenRouter
(``openai/gpt-5.6-luna``).

Answer transport (``--transport``):

* ``responses`` (default): Stirrup's ``OpenResponsesClient`` against OpenRouter's Responses endpoint, with
  ``encrypted_reasoning=True`` so each turn's reasoning items are passed back, as the OpenAI Responses API
  does for GPT-5.x.
* ``chat``: Stirrup's ``ChatCompletionsClient`` (Stirrup's default and its documented OpenRouter route).
  Reasoning is not carried between turns on this route.

Cost is the ``usage.cost`` OpenRouter reports per call (USD, provider list price, cache discounts applied).
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

ANSWER_MODEL = "openai/gpt-5.6-luna"
GRADER_MODEL = "openai/gpt-5.6-luna"
REASONING_EFFORT = "medium"
MAX_OUTPUT_TOKENS = 127_999
CONTEXT_WINDOW_TOKENS = 1_050_000
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
GRADER_MAX_TOKENS = 16_000


def openrouter_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPEN_ROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY (or OPEN_ROUTER_API_KEY) is not set")
    return key


def openrouter_client() -> AsyncOpenAI:
    """The OpenRouter client one system's grader and model-only calls share (``runner.run_system`` owns it)."""
    return AsyncOpenAI(base_url=OPENROUTER_BASE_URL, api_key=openrouter_key(), max_retries=6)


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    value = getattr(obj, name, default)
    if value is default and hasattr(obj, "model_extra") and obj.model_extra:
        value = obj.model_extra.get(name, default)
    return value


@dataclass
class CallUsage:
    kind: str
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cost_usd: float | None
    latency_s: float
    provider: str | None = None


def usage_from_response(kind: str, response: Any, latency_s: float) -> CallUsage:
    """Chat Completions (prompt/completion_tokens) or Responses (input/output_tokens) usage."""
    usage = _get(response, "usage")
    input_tokens = _get(usage, "prompt_tokens") or _get(usage, "input_tokens") or 0
    output_tokens = _get(usage, "completion_tokens") or _get(usage, "output_tokens") or 0
    in_details = _get(usage, "prompt_tokens_details") or _get(usage, "input_tokens_details")
    out_details = _get(usage, "completion_tokens_details") or _get(usage, "output_tokens_details")
    cost = _get(usage, "cost")
    return CallUsage(
        kind=kind,
        input_tokens=int(input_tokens),
        cached_tokens=int(_get(in_details, "cached_tokens") or 0),
        output_tokens=int(output_tokens),
        reasoning_tokens=int(_get(out_details, "reasoning_tokens") or 0),
        cost_usd=float(cost) if isinstance(cost, (int, float)) else None,
        latency_s=latency_s,
        provider=_get(response, "provider"),
    )


@dataclass
class UsageLog:
    calls: list[CallUsage] = field(default_factory=list)

    def wrap(self, method: Any, kind: str) -> Any:
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            response = await method(*args, **kwargs)
            self.calls.append(usage_from_response(kind, response, time.perf_counter() - start))
            return response

        return wrapped

    def totals(self, kind: str) -> dict[str, Any]:
        calls = [call for call in self.calls if call.kind == kind]
        costs = [call.cost_usd for call in calls]
        return {
            "calls": len(calls),
            "input_tokens": sum(call.input_tokens for call in calls),
            "cached_tokens": sum(call.cached_tokens for call in calls),
            "output_tokens": sum(call.output_tokens for call in calls),
            "reasoning_tokens": sum(call.reasoning_tokens for call in calls),
            "cost_usd": sum(cost for cost in costs if cost is not None),
            "cost_missing_calls": sum(cost is None for cost in costs),
            "latency_s": sum(call.latency_s for call in calls),
        }


def answer_client(transport: str, usage: UsageLog) -> Any:
    """A Stirrup client whose underlying OpenAI SDK calls are logged into ``usage``."""
    if transport == "responses":
        from stirrup.clients.open_responses_client import OpenResponsesClient

        client = OpenResponsesClient(
            model=ANSWER_MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            context_window_tokens=CONTEXT_WINDOW_TOKENS,
            base_url=OPENROUTER_BASE_URL,
            api_key=openrouter_key(),
            reasoning_effort=REASONING_EFFORT,
            encrypted_reasoning=True,
            timeout=600,
            max_retries=6,
        )
        # Stirrup keeps its AsyncOpenAI instance private; wrapping its create() is the only usage hook.
        sdk = client._client  # noqa: SLF001
        sdk.responses.create = usage.wrap(sdk.responses.create, "answer")
        return client
    if transport == "chat":
        from stirrup.clients.chat_completions_client import ChatCompletionsClient

        client = ChatCompletionsClient(
            model=ANSWER_MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            context_window_tokens=CONTEXT_WINDOW_TOKENS,
            base_url=OPENROUTER_BASE_URL,
            api_key=openrouter_key(),
            timeout=600,
            max_retries=6,
            kwargs={"extra_body": {"reasoning": {"effort": REASONING_EFFORT}, "usage": {"include": True}}},
        )
        sdk = client._client  # noqa: SLF001
        sdk.chat.completions.create = usage.wrap(sdk.chat.completions.create, "answer")
        return client
    raise ValueError(f"unknown transport {transport!r}")


class Grader:
    """GPT-5.6 Luna (medium) with the paper's grader prompt as the single user message."""

    def __init__(self, usage: UsageLog, sdk: AsyncOpenAI, max_attempts: int = 4) -> None:
        self._sdk = sdk
        self._usage = usage
        self._max_attempts = max_attempts

    async def grade(self, prompt: str) -> tuple[str, str]:
        """Return (grade, raw reply). Retries once more if the reply cannot be parsed."""
        from .omniscience import parse_grade

        last_error: Exception | None = None
        for attempt in range(self._max_attempts):
            start = time.perf_counter()
            response = await self._sdk.chat.completions.create(
                model=GRADER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=GRADER_MAX_TOKENS,
                extra_body={"reasoning": {"effort": REASONING_EFFORT}, "usage": {"include": True}},
                timeout=300,
            )
            self._usage.calls.append(usage_from_response("grader", response, time.perf_counter() - start))
            text = response.choices[0].message.content or ""
            try:
                return parse_grade(text), text
            except ValueError as error:
                last_error = error
                await asyncio.sleep(2**attempt)
        raise RuntimeError(f"grader gave no parseable grade: {last_error}")


async def model_only_answer(sdk: AsyncOpenAI, system_prompt: str, question: str, usage: UsageLog) -> str:
    """AA's ``model_only`` baseline: one call, the benchmark prompt, no tools."""
    start = time.perf_counter()
    response = await sdk.chat.completions.create(
        model=ANSWER_MODEL,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": question}],
        max_completion_tokens=MAX_OUTPUT_TOKENS,
        extra_body={"reasoning": {"effort": REASONING_EFFORT}, "usage": {"include": True}},
        timeout=600,
    )
    usage.calls.append(usage_from_response("answer", response, time.perf_counter() - start))
    return response.choices[0].message.content or ""
