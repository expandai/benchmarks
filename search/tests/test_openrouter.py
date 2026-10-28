"""OpenRouter transport: request shape, schema passthrough, usage/cost mapping, retries, install."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from benchmarks.graders.rag import GroundednessResult
from conftest import mock_client
from harness import cli
from harness.llm.judge import Judge, track_judge_usage
from harness.llm.openai import OpenAIClient
from harness.llm.pricing import token_cost
from harness.llm.types import ContextWindowExceeded
from harness.rag import SingleStepRAG
from harness.systems import Catalog

import bakeoff.register as register
from bakeoff import openrouter
from bakeoff.openrouter import OpenRouterClient, OpenRouterError

MESSAGES = [
    {"role": "system", "content": "You grade things."},
    {"role": "user", "content": "Grade this."},
]
SCHEMA = {
    "name": "Verdict",
    "schema": {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    },
}


def completion(
    content: str = '{"ok": true}',
    *,
    cost: float | None = 0.00123,
    tool_calls: list[dict[str, Any]] | None = None,
    reasoning: str | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
        message["content"] = None
    if reasoning is not None:
        message["reasoning"] = reasoning
    usage: dict[str, Any] = {
        "prompt_tokens": 1200,
        "completion_tokens": 340,
        "total_tokens": 1540,
        "prompt_tokens_details": {"cached_tokens": 200},
        "completion_tokens_details": {"reasoning_tokens": 300},
    }
    if cost is not None:
        usage["cost"] = cost
    return {
        "id": "gen-1",
        "model": "openai/gpt-6-luna",
        "choices": [{"index": 0, "finish_reason": "stop", "message": message}],
        "usage": usage,
    }


class Recorder:
    """A MockTransport handler that records requests and replays scripted responses."""

    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(response, Exception):
            raise response
        return response

    def body(self, index: int = -1) -> dict[str, Any]:
        return json.loads(self.requests[index].content)


def client(recorder: Recorder, model: str = "openai/gpt-6-luna") -> OpenRouterClient:
    return OpenRouterClient(model, client=mock_client(recorder), max_retries=3)


@pytest.fixture(autouse=True)
def openrouter_key(monkeypatch):
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "test-openrouter-key")
    openrouter.STATS.__init__()


def test_model_name_is_validated_and_mapped():
    assert OpenRouterClient("openai/gpt-5.6-luna").openrouter_model == "openai/gpt-5.6-luna"
    with pytest.raises(ValueError):
        OpenRouterClient("anthropic/claude-sonnet-5")


def test_build_request_shape_for_a_reasoning_model_with_schema():
    request = OpenRouterClient("openai/gpt-6-luna").build_request(
        MESSAGES,
        tools=None,
        hosted_web_search=None,
        max_output_tokens=16_000,
        temperature=0.0,
        reasoning_effort="low",
        response_schema=SCHEMA,
    )
    assert request["model"] == "openai/gpt-6-luna"
    assert request["messages"] == MESSAGES
    assert request["max_tokens"] == 16_000
    assert request["reasoning"] == {"effort": "low"}
    assert "temperature" not in request  # reasoning models reject it, as upstream
    assert request["provider"] == {"require_parameters": True}
    assert request["usage"] == {"include": True}
    assert request["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "Verdict", "strict": True, "schema": SCHEMA["schema"]},
    }
    assert "tools" not in request


def test_build_request_without_effort_leaves_reasoning_at_the_model_default():
    request = OpenRouterClient("openai/gpt-5.6-luna").build_request(
        MESSAGES,
        tools=None,
        hosted_web_search=None,
        max_output_tokens=None,
        temperature=None,
        reasoning_effort=None,
    )
    assert set(request) == {"model", "messages", "provider", "usage"}


def test_build_request_non_reasoning_model_passes_temperature_and_tools():
    request = OpenRouterClient("openai/gpt-4.1").build_request(
        MESSAGES,
        tools=[{"name": "search", "description": "d", "parameters": {"type": "object"}, "strict": True}],
        hosted_web_search=None,
        max_output_tokens=None,
        temperature=0.2,
        reasoning_effort="high",
    )
    assert request["temperature"] == 0.2
    assert "reasoning" not in request
    assert request["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "search",
                "description": "d",
                "parameters": {"type": "object"},
                "strict": True,
            },
        }
    ]


def test_hosted_web_search_is_rejected():
    with pytest.raises(ValueError, match="hosted web search"):
        OpenRouterClient("openai/gpt-6-luna").build_request(
            MESSAGES,
            tools=None,
            hosted_web_search={},
            max_output_tokens=None,
            temperature=None,
            reasoning_effort=None,
        )


async def test_generate_sends_bearer_key_and_maps_usage_and_reported_cost():
    recorder = Recorder(httpx.Response(200, json=completion(reasoning="thinking...")))
    generation = await client(recorder).generate(
        MESSAGES, max_output_tokens=16_000, response_schema=SCHEMA
    )
    request = recorder.requests[0]
    assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test-openrouter-key"
    assert recorder.body()["response_format"]["json_schema"]["strict"] is True
    assert generation.text == '{"ok": true}'
    assert generation.usage.input_tokens == 1200
    assert generation.usage.output_tokens == 340
    assert generation.usage.cached_input_tokens == 200
    assert generation.usage.reasoning_tokens == 300
    assert generation.cost_usd == pytest.approx(0.00123)
    assert generation.reasoning == ["thinking..."]
    assert generation.hosted_search is None
    assert generation.raw["transport"]["attempts"] == 1
    assert generation.raw["transport"]["reported_cost_usd"] == pytest.approx(0.00123)
    assert openrouter.STATS.calls == 1
    assert openrouter.STATS.cost_usd == pytest.approx(0.00123)


async def test_generate_falls_back_to_the_pricing_table_without_usage_cost():
    recorder = Recorder(httpx.Response(200, json=completion(cost=None)))
    generation = await client(recorder).generate(MESSAGES)
    expected = token_cost("openai/gpt-6-luna", generation.usage, cached_included_in_input=True)
    assert expected is not None
    assert generation.cost_usd == pytest.approx(expected)
    assert generation.raw["transport"]["reported_cost_usd"] is None


async def test_base_url_override(monkeypatch):
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://gateway.example/or/v1/")
    recorder = Recorder(httpx.Response(200, json=completion()))
    await client(recorder).generate(MESSAGES)
    assert str(recorder.requests[0].url) == "https://gateway.example/or/v1/chat/completions"


async def test_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("OPEN_ROUTER_API_KEY")
    recorder = Recorder(httpx.Response(200, json=completion()))
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY or OPEN_ROUTER_API_KEY"):
        await client(recorder).generate(MESSAGES)
    assert recorder.requests == []


async def test_tool_calls_are_parsed():
    calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "search", "arguments": '{"q": "x"}'},
        }
    ]
    recorder = Recorder(httpx.Response(200, json=completion(tool_calls=calls)))
    generation = await client(recorder).generate(MESSAGES, tools=[{"name": "search", "parameters": {}}])
    assert generation.text == ""
    assert [(c.id, c.name, c.arguments) for c in generation.tool_calls] == [
        ("call_1", "search", '{"q": "x"}')
    ]


async def test_retries_429_and_5xx_then_succeeds():
    recorder = Recorder(
        httpx.Response(429, text="slow down", headers={"retry-after": "0"}),
        httpx.Response(502, text="bad gateway"),
        httpx.ConnectError("boom"),
        httpx.Response(200, json=completion()),
    )
    generation = await client(recorder).generate(MESSAGES)
    assert len(recorder.requests) == 4
    assert generation.raw["transport"]["attempts"] == 4
    assert openrouter.STATS.retries == 3
    assert openrouter.STATS.retried_statuses == {"429": 1, "502": 1, "ConnectError": 1}
    assert openrouter.STATS.failures == 0


async def test_provider_error_wrapped_in_200_is_retried():
    recorder = Recorder(
        httpx.Response(200, json={"error": {"code": 502, "message": "upstream"}}),
        httpx.Response(200, json=completion()),
    )
    generation = await client(recorder).generate(MESSAGES)
    assert generation.raw["transport"]["attempts"] == 2


async def test_gives_up_after_max_retries():
    recorder = Recorder(httpx.Response(503, text="down"))
    with pytest.raises(OpenRouterError, match="gave up after 4 attempts"):
        await client(recorder).generate(MESSAGES)
    assert len(recorder.requests) == 4
    assert openrouter.STATS.failures == 1


async def test_401_is_not_retried():
    recorder = Recorder(httpx.Response(401, json={"error": {"message": "No auth"}}))
    with pytest.raises(OpenRouterError, match="OpenRouter 401") as info:
        await client(recorder).generate(MESSAGES)
    assert info.value.status == 401
    assert len(recorder.requests) == 1
    assert openrouter.STATS.retries == 0


async def test_context_window_error_maps_to_upstream_exception():
    recorder = Recorder(
        httpx.Response(
            400, json={"error": {"message": "This model's maximum context length is 400000"}}
        )
    )
    with pytest.raises(ContextWindowExceeded):
        await client(recorder).generate(MESSAGES)


async def test_empty_choices_is_an_error():
    recorder = Recorder(httpx.Response(200, json={"choices": [], "usage": {}}))
    with pytest.raises(OpenRouterError, match="no choices"):
        await client(recorder).generate(MESSAGES)


# --- install / routing -------------------------------------------------------


def test_default_transport_is_upstream_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    register.install()
    assert not openrouter.is_installed()
    assert isinstance(Judge("openai/gpt-6-luna").client, OpenAIClient)
    assert cli.PROVIDER_KEYS["openai"] == ("OPENAI_API_KEY",)


def test_bad_transport_value_is_rejected(monkeypatch):
    monkeypatch.setenv("BAKEOFF_LLM_TRANSPORT", "azure")
    with pytest.raises(ValueError, match="BAKEOFF_LLM_TRANSPORT"):
        register.install()


def test_install_routes_judge_rag_and_preflight(monkeypatch):
    monkeypatch.setenv("BAKEOFF_LLM_TRANSPORT", "openrouter")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "p")
    register.install()
    assert openrouter.is_installed()
    assert isinstance(Judge("openai/gpt-6-luna").client, OpenRouterClient)
    spec = Catalog.load().resolve("rag-perplexity-fast")
    # SingleStepRAG only stores the searcher; the client comes from harness.rag's binding.
    stub_searcher = object()
    system = SingleStepRAG(stub_searcher, spec.model, num_results=10)  # type: ignore[arg-type]
    assert isinstance(system.client, OpenRouterClient)
    assert cli.PROVIDER_KEYS["openai"] == openrouter.KEY_ENV
    assert cli.missing_credentials(spec, "openai/gpt-6-luna") == []
    monkeypatch.delenv("OPEN_ROUTER_API_KEY")
    missing = cli.missing_credentials(spec, "openai/gpt-6-luna")
    assert missing and all("OPENROUTER_API_KEY" in m for m in missing)
    # Run-directory inputs are untouched: same model names, same hash.
    assert spec.model == "openai/gpt-5.6-luna"
    openrouter.uninstall()
    assert not openrouter.is_installed()


def test_repeat_install_keeps_the_run_counters():
    openrouter.install()
    openrouter.STATS.calls = 7
    openrouter.install()
    assert openrouter.STATS.calls == 7
    openrouter.uninstall()
    openrouter.install()
    assert openrouter.STATS.calls == 0


async def test_judge_complete_json_round_trip_through_openrouter(monkeypatch):
    monkeypatch.setenv("BAKEOFF_LLM_TRANSPORT", "openrouter")
    register.install()
    reply = {
        "evidence": "The docs say 42.",
        "reasoning": "Found it.",
        "groundedness": "GROUNDED",
        "source_indices": [2],
    }
    recorder = Recorder(httpx.Response(200, json=completion(json.dumps(reply), cost=0.0004)))
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **_kw: real_async_client(transport=httpx.MockTransport(recorder)),
    )
    judge = Judge("openai/gpt-6-luna")
    with track_judge_usage() as spend:
        parsed, response = await judge.complete_json(
            "Question: q", GroundednessResult, system="You are a retrieval quality auditor."
        )
    assert isinstance(parsed, GroundednessResult)
    assert parsed.groundedness == "GROUNDED" and parsed.source_indices == [2]
    assert response.cost_usd == pytest.approx(0.0004)
    assert spend.calls == 1 and spend.known and spend.total_usd == pytest.approx(0.0004)
    body = recorder.body()
    assert body["model"] == "openai/gpt-6-luna"
    assert body["max_tokens"] == 16_000
    assert "reasoning" not in body
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    schema = body["response_format"]["json_schema"]
    assert schema["name"] == "GroundednessResult" and schema["strict"] is True
    assert schema["schema"]["additionalProperties"] is False
    assert set(schema["schema"]["required"]) == set(reply)
