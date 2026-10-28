"""The bakeoff's retrieval protocol for the official-grader suites, plus the no-search baseline.

Upstream's ``SingleStepRAG`` tells the model it has "NO internal knowledge" and must answer
"I don't know" unless the snippets suffice. SimpleQA Verified and SealQA are parametric or
mixed-knowledge benchmarks (``METHODOLOGY.md`` §§4–5) and FRAMES' own baseline is
the model's knowledge, so the official suites use this pipeline instead:

* one search per question with the question text as the query, ``num_results`` from the
  system (10), the provider's result order kept, results without a URL or evidence dropped
  (upstream ``normalize_results``), then a benchmark-leak filter (``contamination_reason``:
  dataset hosts, benchmark names, the canary, and pages that repeat the question verbatim);
* one answer call to the system's model (``openai/gpt-5.6-luna`` for every system) with a
  single neutral user message (``SEARCH_PROMPT``): the dated documents, then the question;
  the model may use the documents and its own knowledge. No system message. Reasoning
  effort comes from the suite (``AnswerProtocol``; SealQA asks for high, the others use the
  model's default). Nothing is substituted for an empty reply;
* ``rag-model-only`` (searcher ``none`` → ``NullSearcher``) skips the search and sends the
  question alone as the whole prompt, which is exactly the designers' own setting.

``install()`` wraps ``harness.systems.System.execute``: tasks of a suite that declares an
``answer_protocol`` take this path; every other suite still runs upstream's code. The result
dict keeps upstream's contract (``answer``, ``citations``, ``search_queries``, costs,
``usage``, ``latency_ms``, ``messages``) and adds ``answer_protocol``, ``num_searches``,
``filtered_results`` and ``query_clipped``.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from harness import cli, systems
from harness.searchers import Searcher, SearchResponse, SearchResult
from harness.suite import Suite, Task
from harness.tools import normalize_results

NULL_PROVIDER = "none"
# Hard caps per task so a hung connection becomes a retriable execution error instead of a
# stalled worker slot. Generous against observed p90s (search < 10 s, high-reasoning answers < 90 s).
SEARCH_TIMEOUT_S = 180.0
ANSWER_TIMEOUT_S = 600.0

SEARCH_PROMPT = """Answer the question below. You are given web search results that may help; they can be \
incomplete, outdated or contradictory, so weigh them against each other and against what you \
already know, and give your best answer. Today's date is {current_date}.

Search results:
{documents}

Question: {question}"""

DOCUMENT_TEMPLATE = "[{index}] Title: {title}\nURL: {url}\n{published}Text: {text}"

# Pages that could leak the benchmarks themselves (dataset hosts and benchmark names). Checked
# against the lower-cased URL, title and text of every result; matches are dropped and counted.
CONTAMINATION_HOSTS = ("huggingface.co/datasets", "kaggle.com/")
CONTAMINATION_TERMS = (
    "sealqa",
    "seal-0",
    "seal_0",
    "seal-hard",
    "seal_hard",
    "simpleqa",
    "simple_qa",
    "frames-benchmark",
    "frames_benchmark",
)


@dataclass(frozen=True)
class AnswerProtocol:
    """What the answer call does beyond the shared prompt."""

    name: str
    reasoning_effort: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NullSearcher(Searcher):
    """Returns no results at no cost: the model-only (no search) baseline."""

    name = NULL_PROVIDER

    async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        return []

    async def run(
        self,
        query: str,
        num_results: int = 10,
        *,
        objective: str | None = None,
        search_queries: list[str] | None = None,
    ) -> SearchResponse:
        del objective, search_queries
        return SearchResponse(results=[], cost_usd=0.0, latency_ms=0.0, queries=[])


VERBATIM_MIN_QUESTION_CHARS = 60
VERBATIM_PREFIX_CHARS = 120


def normalize_text(text: str) -> str:
    """Whitespace runs collapsed to one space, trimmed, lower-cased: the leak rules' match form."""
    return re.sub(r"\s+", " ", text).strip().lower()


def contamination_reason(
    record: dict[str, Any], canary: str | None = None, question: str | None = None
) -> str | None:
    """Why a result is a benchmark leak, or ``None``.

    ``host``: a dataset host (Hugging Face datasets, Kaggle). ``term``: a benchmark name in the
    URL, title or text. ``canary``: the dataset's canary string. ``verbatim_question``: the
    text repeats the question itself (first 120 normalized characters, questions of 60+
    characters) — mirrors, eval dashboards and blog posts that reproduce benchmark items.
    """
    url = (record.get("url") or "").lower()
    if any(host in url for host in CONTAMINATION_HOSTS):
        return "host"
    haystack = normalize_text(" ".join(str(record.get(k) or "") for k in ("url", "title", "text")))
    if any(term in haystack for term in CONTAMINATION_TERMS):
        return "term"
    if canary and canary.lower() in haystack:
        return "canary"
    if question:
        needle = normalize_text(question)
        if len(needle) >= VERBATIM_MIN_QUESTION_CHARS and needle[:VERBATIM_PREFIX_CHARS] in normalize_text(
            str(record.get("text") or "")
        ):
            return "verbatim_question"
    return None


def filter_contaminated(
    records: list[dict[str, Any]], canary: str | None = None, question: str | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split records into kept and dropped; each dropped record carries its ``reason``."""
    kept, dropped = [], []
    for record in records:
        reason = contamination_reason(record, canary, question)
        if reason is None:
            kept.append(record)
        else:
            dropped.append({**record, "reason": reason})
    return kept, dropped


def format_documents(citations: list[dict[str, Any]]) -> str:
    parts = []
    for index, c in enumerate(citations, start=1):
        published = f"Published: {c['published_date']}\n" if c.get("published_date") else ""
        parts.append(
            DOCUMENT_TEMPLATE.format(
                index=index, title=c["title"], url=c["url"], published=published, text=c["text"]
            )
        )
    return "\n\n".join(parts)


def build_messages(
    question: str, citations: list[dict[str, Any]], *, with_search: bool, current_date: str
) -> list[dict[str, str]]:
    """One user message; the bare question when there is no search."""
    if not with_search:
        return [{"role": "user", "content": question}]
    return [
        {
            "role": "user",
            "content": SEARCH_PROMPT.format(
                current_date=current_date,
                documents=format_documents(citations) or "(no results)",
                question=question,
            ),
        }
    ]


async def official_execute(system: Any, task: Task, suite: Suite) -> dict[str, Any]:
    """Search once (unless ``rag-model-only``), answer once with the neutral prompt."""
    protocol: AnswerProtocol = getattr(suite, "answer_protocol")
    question = suite.prompt(task)
    searcher = system._searcher
    with_search = not isinstance(searcher, NullSearcher)
    start = time.monotonic()
    response = await asyncio.wait_for(searcher.run(question, system.num_results), SEARCH_TIMEOUT_S)
    kept, skipped = normalize_results(response.results)
    kept, dropped = filter_contaminated(kept, task.metadata.get("canary"), question)
    citations = [
        {"url": r["url"], "title": r["title"], "text": r["text"], "published_date": r["published_date"]}
        for r in kept
    ]
    current_date = datetime.now(timezone.utc).strftime("%B %d, %Y")
    messages = build_messages(question, citations, with_search=with_search, current_date=current_date)
    generation = await asyncio.wait_for(
        # The client upstream's SingleStepRAG built for this system (``rag.create_client``,
        # the transport-patched binding); its search and prompt are not used here.
        system._runner.client.generate(messages, reasoning_effort=protocol.reasoning_effort),
        ANSWER_TIMEOUT_S,
    )
    answer = generation.text.strip()
    transcript = [*messages, {"role": "assistant", "content": answer}]
    sent_query = response.queries[0] if response.queries else None
    return {
        "answer": answer,
        "citations": citations,
        "search_queries": list(response.queries),
        "query_clipped": bool(sent_query) and sent_query.strip() != question.strip(),
        "num_searches": 1 if with_search else 0,
        "filtered_results": [{"url": d["url"], "title": d["title"], "reason": d["reason"]} for d in dropped],
        "skipped_results": skipped,
        "answer_protocol": {
            **protocol.to_dict(),
            "with_search": with_search,
            "model": system.spec.model,
            "current_date": current_date,
        },
        "model_cost_usd": generation.cost_usd or 0.0,
        "search_cost_usd": response.cost_usd or 0.0,
        "total_cost_usd": (generation.cost_usd or 0.0) + (response.cost_usd or 0.0),
        "cost_known": generation.cost_usd is not None and response.cost_usd is not None,
        "usage": generation.usage.to_dict(),
        "latency_ms": (time.monotonic() - start) * 1000,
        "messages": transcript,
    }


_installed = False


def install() -> None:
    """Route official-suite tasks through ``official_execute``; register the ``none`` searcher."""
    global _installed
    if _installed:
        return
    upstream_execute = systems.System.execute

    async def execute(self: Any, task: Task, suite: Suite) -> dict[str, Any]:
        if getattr(suite, "answer_protocol", None) is not None:
            return await official_execute(self, task, suite)
        return await upstream_execute(self, task, suite)

    systems.System.execute = execute  # type: ignore[method-assign]

    upstream_missing = cli.missing_credentials

    def missing_credentials(spec: Any, judge_model: str | None) -> list[str]:
        # The ``none`` provider has no key: drop the empty entry upstream's join produces.
        return [name for name in upstream_missing(spec, judge_model) if name]

    cli.missing_credentials = missing_credentials
    _installed = True
