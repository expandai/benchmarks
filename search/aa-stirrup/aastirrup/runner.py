"""Run AA-Omniscience questions through a Stirrup agent whose ``web_search`` is one bakeoff searcher.

Per task: Stirrup ``Agent`` (25 turns, ``web_search`` + ``web_fetch`` + ``finish(answer)``), then the paper's
grader. One JSON file per (system, question) under ``<run>/<system>/``; a file with ``status: complete`` is
never re-run, so re-running the same command resumes. Execution errors are stored with ``status: error`` and
retried on the next invocation; they are never scored.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
import traceback
from pathlib import Path
from typing import Annotated, Any

from bakeoff.provenance import implementation_digest
from bakeoff.suites import AA_OMNISCIENCE_SHA256
from pydantic import BaseModel, Field
from stirrup.core.agent import Agent
from stirrup.core.models import (
    AssistantMessage,
    ChatMessage,
    SystemMessage,
    Tool,
    ToolMessage,
    ToolResult,
    ToolUseCountMetadata,
    UserMessage,
    joined_text,
    tool_call_blocks,
)
from stirrup.utils.logging import AgentLoggerBase

from . import llm
from .omniscience import (
    NOT_ATTEMPTED,
    Question,
    answerer_system_prompt,
    grader_prompt,
    task_prompt,
)
from .systems import MODEL_ONLY, SYSTEMS, build_searcher, searcher_entry
from .tools import SearchToolProvider

MAX_TURNS = 25
TRACE_TOOL_CHARS = 4000


class AnswerParams(BaseModel):
    answer: Annotated[
        str,
        Field(description="Your final answer: JUST the answer (no explanation), or say clearly that you do not know."),
    ]


async def _finish_executor(params: AnswerParams) -> ToolResult[ToolUseCountMetadata]:
    return ToolResult(content=params.answer, metadata=ToolUseCountMetadata())


FINISH_TOOL = Tool[AnswerParams, ToolUseCountMetadata](
    name="finish",
    description=(
        "Submit your final answer and end the task. Note that you will need a separate turn to finish."
    ),
    parameters=AnswerParams,
    executor=_finish_executor,
)


class QuietLogger(AgentLoggerBase):
    """Stirrup's logger interface with no console output (many agents run concurrently)."""

    def __init__(self) -> None:
        self.name = "aa_omniscience"
        self.model = None
        self.max_turns = None
        self.depth = 0
        self.finish_params = None
        self.run_metadata = None
        self.output_dir = None

    def __enter__(self) -> QuietLogger:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: object) -> None:
        return None

    def on_step(self, step: int, tool_calls: int = 0, input_tokens: int = 0, output_tokens: int = 0) -> None:
        return None

    def assistant_message(self, turn: int, max_turns: int, assistant_message: AssistantMessage) -> None:
        return None

    def user_message(self, user_message: UserMessage) -> None:
        return None

    def task_message(self, task: str | list[Any]) -> None:
        return None

    def tool_result(self, tool_message: ToolMessage) -> None:
        return None

    def context_summarization_start(self, pct_used: float, cutoff: float) -> None:
        return None

    def context_summarization_complete(self, summary: str, bridge: str) -> None:
        return None

    def debug(self, message: str, *args: object) -> None:
        return None

    def info(self, message: str, *args: object) -> None:
        return None

    def warning(self, message: str, *args: object) -> None:
        return None

    def error(self, message: str, *args: object) -> None:
        return None


def _content_text(content: Any) -> str:
    return content if isinstance(content, str) else json.dumps(content, default=str)[:TRACE_TOOL_CHARS]


def compact_trace(history: list[list[ChatMessage]]) -> list[dict[str, Any]]:
    """Readable trace without encrypted reasoning payloads; tool outputs clipped for size."""
    trace: list[dict[str, Any]] = []
    for group in history:
        for message in group:
            if isinstance(message, SystemMessage):
                trace.append({"role": "system", "content": _content_text(message.content)})
            elif isinstance(message, AssistantMessage):
                trace.append(
                    {
                        "role": "assistant",
                        "text": joined_text(message.blocks),
                        "tool_calls": [{"name": c.name, "arguments": c.arguments} for c in tool_call_blocks(message.blocks)],
                        "tokens": message.token_usage.model_dump(),
                        "seconds": (message.request_end_time or 0) - (message.request_start_time or 0),
                    }
                )  # fmt: skip
            elif isinstance(message, ToolMessage):
                trace.append(
                    {
                        "role": "tool",
                        "name": message.name,
                        "success": message.success,
                        "content": _content_text(message.content)[:TRACE_TOOL_CHARS],
                    }
                )
            elif isinstance(message, UserMessage):
                trace.append({"role": "user", "kind": message.kind, "content": _content_text(message.content)})
    return trace


def count_turns(history: list[list[ChatMessage]]) -> int:
    return sum(isinstance(m, AssistantMessage) for group in history for m in group)


def model_seconds(history: list[list[ChatMessage]]) -> float:
    return sum(
        (m.request_end_time or 0) - (m.request_start_time or 0)
        for group in history
        for m in group
        if isinstance(m, AssistantMessage)
    )


async def run_agent(
    question: Question,
    provider: SearchToolProvider,
    transport: str,
    usage: llm.UsageLog,
) -> dict[str, Any]:
    agent = Agent(
        client=llm.answer_client(transport, usage),
        name="aa_omniscience",
        max_turns=MAX_TURNS,
        system_prompt=answerer_system_prompt(question),
        tools=[provider],
        finish_tool=FINISH_TOOL,
        logger=QuietLogger(),
    )
    async with agent.session(cache_on_interrupt=False, clear_cache_on_success=True) as session:
        finish, history, _metadata = await session.run(task_prompt(question))
    return {
        "finished": finish is not None,
        "answer": finish.answer if finish is not None else "",
        "turns": count_turns(history),
        "model_seconds": model_seconds(history),
        "tools": provider.telemetry.to_dict(),
        "trace": compact_trace(history),
    }


async def run_task(
    question: Question, system: str, transport: str, searcher: Any, out: Path, sdk: Any
) -> dict[str, Any]:
    """One question end to end; ``sdk`` is the system's shared ``llm.openrouter_client()``."""
    # A retry must not erase the earlier attempt's usage, errors or evidence.
    if out.exists():
        attempts = out.parent / "attempts" / out.stem
        attempts.mkdir(parents=True, exist_ok=True)
        previous = attempts / f"{time.time_ns()}.json"
        shutil.copy2(out, previous)
    usage = llm.UsageLog()
    provider = None if system == MODEL_ONLY else SearchToolProvider(
        searcher, question=question.question, max_evidence_chars=SYSTEMS[system].evidence_chars
    )
    started = time.perf_counter()
    record: dict[str, Any] = {
        "id": question.id,
        "question_id": question.question_id,
        "domain": question.domain,
        "topic": question.topic,
        "system": system,
        "transport": transport,
        "question": question.question,
        "gold": question.answer,
        "started_at": time.time(),
    }
    try:
        if system == MODEL_ONLY:
            answer = await llm.model_only_answer(sdk, answerer_system_prompt(question), question.question, usage)
            record.update({"finished": True, "answer": answer, "turns": 1, "model_seconds": None,
                           "tools": {"searches": [], "fetches": []}, "trace": []})  # fmt: skip
        else:
            assert provider is not None
            record.update(await run_agent(question, provider, transport, usage))
        record["agent_seconds"] = time.perf_counter() - started
        if record["finished"]:
            record["grade"], record["grader_reply"] = await llm.Grader(usage, sdk).grade(
                grader_prompt(question, record["answer"])
            )
        else:
            # Turn budget exhausted without finish: AA scores zero; no answer was submitted.
            record["grade"], record["grader_reply"] = NOT_ATTEMPTED, "(no finish within 25 turns)"
        record["status"] = "complete"
    except Exception as error:  # noqa: BLE001 - stored, retried on resume, never scored
        record["status"] = "error"
        record["error"] = f"{type(error).__name__}: {str(error)[:1000]}"
        record["traceback"] = traceback.format_exc()[-4000:]
    # run_agent can fail after several successful, paid searches. Keep their telemetry even
    # when it never returns a result; otherwise the error record incorrectly says zero searches.
    if provider is not None:
        record["tools"] = provider.telemetry.to_dict()
    record["wall_seconds"] = time.perf_counter() - started
    record["usage"] = {
        "answer": usage.totals("answer"),
        "grader": usage.totals("grader"),
        "calls": [vars(call) for call in usage.calls],
    }
    searches = record.get("tools", {}).get("searches", [])
    record["search"] = {
        "calls": len(searches),
        "cost_usd": sum(s["cost_usd"] or 0.0 for s in searches),
        "cost_missing_calls": sum(s["cost_usd"] is None and s["error"] is None for s in searches),
        "seconds": sum(s["latency_s"] for s in searches),
        "filtered_results": sum(s["filtered"] for s in searches),
        "fetches": len(record.get("tools", {}).get("fetches", [])),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=1, default=str))
    tmp.replace(out)
    return record


def task_path(run_dir: Path, system: str, question: Question) -> Path:
    return run_dir / system / f"{question.id}.json"


def is_complete(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return json.loads(path.read_text()).get("status") == "complete"
    except json.JSONDecodeError:
        return False


def check_run_config(system: str, run_dir: Path, transport: str) -> None:
    """Reject mixing endpoints, settings or implementations in a resumed AA system folder."""
    import bakeoff

    config = {
        "system": system,
        "searcher": None if system == MODEL_ONLY else searcher_entry(system),
        "evidence_chars": SYSTEMS[system].evidence_chars,
        "transport": transport,
        "answer_model": llm.ANSWER_MODEL,
        "grader_model": llm.GRADER_MODEL,
        "reasoning_effort": llm.REASONING_EFFORT,
        "max_output_tokens": llm.MAX_OUTPUT_TOKENS,
        "max_turns": MAX_TURNS,
        "llm_base_url": llm.OPENROUTER_BASE_URL,
        "dataset_sha256": AA_OMNISCIENCE_SHA256,
        "overlay_sha256": implementation_digest(Path(bakeoff.__file__).parent),
        "agent_sha256": implementation_digest(Path(__file__).parent),
    }
    folder = run_dir / system
    path = folder / "run-config.json"
    if path.exists():
        if json.loads(path.read_text()) != config:
            raise ValueError(f"{folder}: execution settings changed; use a new run directory")
    elif list(folder.glob("aao-*.json")):
        raise ValueError(f"{folder}: historical records have no execution fingerprint; use a new run directory")
    else:
        folder.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(config, indent=1))
        temporary.replace(path)


async def run_system(
    system: str, questions: list[Question], run_dir: Path, transport: str, concurrency: int | None
) -> int:
    if concurrency is not None and concurrency < 1:
        raise ValueError("concurrency must be positive")
    check_run_config(system, run_dir, transport)
    pending = [q for q in questions if not is_complete(task_path(run_dir, system, q))]
    if not pending:
        print(f"[{system}] all {len(questions)} complete", flush=True)
        return 0
    sdk = llm.openrouter_client()
    searcher = None if system == MODEL_ONLY else build_searcher(system)
    limit = asyncio.Semaphore(concurrency or SYSTEMS[system].concurrency)
    done = 0

    async def one(question: Question) -> bool:
        nonlocal done
        async with limit:
            record = await run_task(question, system, transport, searcher, task_path(run_dir, system, question), sdk)
        done += 1
        status = record.get("grade") if record["status"] == "complete" else f"ERROR {record.get('error', '')[:160]}"
        print(f"[{system}] {done}/{len(pending)} {question.id} {status} "
              f"searches={record['search']['calls']} {record['wall_seconds']:.0f}s", flush=True)  # fmt: skip
        return record["status"] != "complete"

    try:
        return sum(await asyncio.gather(*(one(q) for q in pending)))
    finally:
        await sdk.close()
        if searcher is not None:
            await searcher.close()
