"""The real Stirrup agent loop end to end, with a scripted model, a fake searcher and a fake grader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from harness.searchers import SearchResult
from stirrup.core.models import AssistantMessage, ChatMessage, TextBlock, TokenUsage, Tool, ToolCall

from bakeoff.expand import EXPAND_SEARCH_COST_PER_REQUEST

from aastirrup import llm, runner
from aastirrup.omniscience import CORRECT, NOT_ATTEMPTED, Question
from aastirrup.report import markdown, summarize

from .conftest import FakeSearcher

Q = Question("aao-001", 1, "Finance", "Accounting", "Accounting",
             "Which ASC 606 paragraph lists the two series criteria?", "ASC 606-10-25-15")  # fmt: skip


def call(name: str, arguments: dict[str, Any]) -> AssistantMessage:
    return AssistantMessage(
        blocks=[ToolCall(name=name, arguments=json.dumps(arguments))],
        token_usage=TokenUsage(input=100, answer=10, reasoning=5),
        request_start_time=0.0,
        request_end_time=0.5,
    )


class ScriptedClient:
    def __init__(self, script: list[AssistantMessage], usage: llm.UsageLog) -> None:
        self.script = script
        self.usage = usage
        self.seen: list[list[ChatMessage]] = []
        self.tools: list[dict[str, Tool]] = []

    @property
    def model_slug(self) -> str:
        return "scripted"

    @property
    def context_window_tokens(self) -> int:
        return 1_000_000

    @property
    def max_tokens(self) -> int:
        return 1000

    async def generate(self, messages: list[ChatMessage], tools: dict[str, Tool]) -> AssistantMessage:
        self.seen.append(list(messages))
        self.tools.append(tools)
        self.usage.calls.append(llm.CallUsage("answer", 100, 40, 15, 5, 0.0002, 0.5))
        if self.script:
            return self.script.pop(0)
        return AssistantMessage(blocks=[TextBlock(text="thinking...")], token_usage=TokenUsage(input=1))


class FakeGrader:
    replies: list[str] = []

    def __init__(self, usage: llm.UsageLog, sdk: Any) -> None:
        self.usage = usage

    async def grade(self, prompt: str) -> tuple[str, str]:
        FakeGrader.replies.append(prompt)
        self.usage.calls.append(llm.CallUsage("grader", 2000, 0, 3, 0, 0.0001, 0.2))
        return CORRECT, "A"


@pytest.fixture
def clients(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    holder: dict[str, Any] = {"script": []}

    def answer_client(transport: str, usage: llm.UsageLog) -> ScriptedClient:
        holder["client"] = ScriptedClient(holder["script"], usage)
        return holder["client"]

    monkeypatch.setattr(llm, "answer_client", answer_client)
    monkeypatch.setattr(llm, "Grader", FakeGrader)
    FakeGrader.replies = []
    return holder


@pytest.fixture
def stub_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    from .test_tools import _stub_fetch_tool

    monkeypatch.setattr(runner, "SearchToolProvider", _with_fetch_stub(_stub_fetch_tool()))


def _with_fetch_stub(stub: Tool) -> Any:
    from aastirrup.tools import SearchToolProvider

    def factory(searcher: Any, **kwargs: Any) -> SearchToolProvider:
        return SearchToolProvider(searcher, fetch_tool=stub, **kwargs)

    return factory


async def test_full_task_search_fetch_finish_grade(
    tmp_path: Path, rows: list[SearchResult], clients: dict[str, Any], stub_fetch: None
) -> None:
    clients["script"].extend(
        [
            call("web_search", {"query": "ASC 606 series criteria"}),
            call("web_fetch", {"url": "https://example.com/a"}),
            call("finish", {"answer": "ASC 606-10-25-15"}),
        ]
    )
    searcher = FakeSearcher(rows)
    out = tmp_path / "expand" / "aao-001.json"
    record = await runner.run_task(Q, "expand", "responses", searcher, out, None)

    assert record["status"] == "complete", record.get("traceback")
    assert record["answer"] == "ASC 606-10-25-15" and record["grade"] == CORRECT
    assert record["turns"] == 3 and record["finished"]
    assert record["search"] == {"calls": 1, "cost_usd": 0.001, "cost_missing_calls": 0,
                                "seconds": pytest.approx(record["search"]["seconds"]),
                                "filtered_results": 1, "fetches": 1}  # fmt: skip
    assert record["usage"]["answer"]["calls"] == 3 and record["usage"]["grader"]["calls"] == 1
    assert json.loads(out.read_text())["status"] == "complete"

    client = clients["client"]
    system = client.seen[0][0].content
    assert system.startswith("You are an AI agent that will be given a specific task. You are to complete that "
                             "task using the tools provided in 25 steps.")  # fmt: skip
    assert "You are answering questions about Finance, and in particular Accounting." in system
    assert "Question: Which ASC 606 paragraph" in client.seen[0][1].content
    tools = client.tools[0]
    assert sorted(tools) == ["finish", "web_fetch", "web_search"]
    assert list(tools["web_search"].parameters.model_json_schema()["properties"]) == ["query"]
    assert list(tools["finish"].parameters.model_json_schema()["properties"]) == ["answer"]
    tool_result = client.seen[1][-1]
    assert tool_result.name == "web_search" and tool_result.content.startswith("<results>\n<result>")
    assert "huggingface.co" not in tool_result.content
    assert "Predicted answer: ASC 606-10-25-15 " in FakeGrader.replies[0]

    summary = summarize(tmp_path, "expand", expected=1)
    assert summary is not None
    assert (summary["correct"], summary["omniscience_index"], summary["searches_per_q"]) == (1, 100.0, 1.0)
    # The fake search recorded $0.001; the report prices Expand's billed search at list price.
    assert summary["search_usd_per_q"] == pytest.approx(EXPAND_SEARCH_COST_PER_REQUEST)
    assert summary["total_usd_per_q"] == pytest.approx(EXPAND_SEARCH_COST_PER_REQUEST + 3 * 0.0002 + 0.0001)
    assert summary["full_set_usd"] == pytest.approx(600 * summary["total_usd_per_q"])
    assert "| Expand Search |" in markdown([summary])


async def test_no_finish_in_25_turns_is_not_attempted(
    tmp_path: Path, rows: list[SearchResult], clients: dict[str, Any], stub_fetch: None
) -> None:
    record = await runner.run_task(Q, "expand", "responses", FakeSearcher(rows), tmp_path / "x.json", None)
    assert record["status"] == "complete"
    assert record["turns"] == runner.MAX_TURNS and not record["finished"]
    assert record["grade"] == NOT_ATTEMPTED and FakeGrader.replies == []
    warnings = [m for m in clients["client"].seen[-1] if getattr(m, "kind", "") == "turn_warning"]
    assert warnings and "last turn" in warnings[-1].content


async def test_fatal_search_error_is_an_execution_error_not_a_grade(
    tmp_path: Path, rows: list[SearchResult], clients: dict[str, Any], stub_fetch: None
) -> None:
    clients["script"].append(call("web_search", {"query": "q"}))
    request = httpx.Request("POST", "https://api.exa.ai/search")
    error = httpx.HTTPStatusError("402", request=request, response=httpx.Response(402, request=request))
    out = tmp_path / "exa" / "aao-001.json"
    record = await runner.run_task(Q, "exa-fast-highlights", "responses", FakeSearcher(rows, fail_times=9, error=error), out, None)
    assert record["status"] == "error" and "HTTPStatusError" in record["error"]
    assert "grade" not in record
    assert not runner.is_complete(out)
    summary = summarize(tmp_path, "exa", expected=1)
    assert summary is not None and summary["errors"] == 1 and summary["complete"] == 0


async def test_error_preserves_searches_and_retry_archives_previous_attempt(
    tmp_path: Path, rows: list[SearchResult], clients: dict[str, Any], stub_fetch: None,
) -> None:
    clients["script"].extend([
        call("web_search", {"query": "first"}),
        call("web_search", {"query": "fails"}),
    ])
    request = httpx.Request("POST", "https://api.exa.ai/search")
    error = httpx.HTTPStatusError("402", request=request, response=httpx.Response(402, request=request))

    class FailsSecondSearch(FakeSearcher):
        async def run(self, query: str, num_results: int = 10, **options: object):
            if query == "fails":
                raise error
            return await super().run(query, num_results, **options)

    out = tmp_path / "expand" / "aao-001.json"
    record = await runner.run_task(Q, "expand", "responses", FailsSecondSearch(rows), out, None)
    assert record["status"] == "error"
    assert record["search"]["calls"] == 2
    assert record["search"]["cost_usd"] == 0.001
    assert record["tools"]["searches"][1]["error"] is not None
    previous = out.read_bytes()
    clients["script"].append(call("finish", {"answer": "ASC 606-10-25-15"}))
    retried = await runner.run_task(Q, "expand", "responses", FakeSearcher(rows), out, None)
    assert retried["status"] == "complete"
    archives = list((out.parent / "attempts" / out.stem).glob("*.json"))
    assert len(archives) == 1 and archives[0].read_bytes() == previous


async def test_partial_report_keeps_manifest_denominator(
    tmp_path: Path, rows: list[SearchResult], clients: dict[str, Any], stub_fetch: None,
) -> None:
    clients["script"].append(call("finish", {"answer": "ASC 606-10-25-15"}))
    await runner.run_task(Q, "expand", "responses", FakeSearcher(rows), tmp_path / "expand" / "aao-001.json", None)
    summary = summarize(tmp_path, "expand", expected=2)
    assert summary["missing"] == 1
    assert summary["n_failed_as_zero"] == 2
    assert summary["accuracy_failed_as_zero"] == 50.0
    assert "INCOMPLETE RUN" in markdown([summary])
    with pytest.raises(ValueError, match="exceed"):
        summarize(tmp_path, "expand", expected=0)
