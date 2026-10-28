"""Post-hoc benchmark-leak audit of the WebCode RAG runs. Read-only over the run directories.

Rules: ``bakeoff.official_rag.contamination_reason`` (the official suites' filter, unchanged:
``host``, ``term``, ``canary``, ``verbatim_question``) is applied first, then WebCode-specific
extensions (``webcode_host``, ``webcode_term``, ``verbatim_query``, ``answer_with_query``).

Outputs (all under runs/leak-audit/):
  leaked_citations.jsonl   one line per leaked citation (system, task, index, url, reason, judge_used)
  regrade_plan.json        the (system, task) pairs that need a groundedness re-grade and the
                           citations that remain after the leaked ones are removed
  audit.json               per-system counts, per-reason counts, leaking domains

Usage (from the bakeoff root):  .venv/bin/python -I runs/leak-audit/audit.py
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path[:0] = ["upstream", "."]
from bakeoff.official_rag import contamination_reason, normalize_text  # noqa: E402

BAKEOFF = Path(".")
OUT = BAKEOFF / "runs" / "leak-audit"
GOLD = BAKEOFF / "upstream" / "data" / "webcode" / "rag.jsonl"
RUN_GLOBS = (("pilot-20", "*-webcode-rag-*"), ("webcode-rag", "*-webcode-rag-*"))

# WebCode extensions: the benchmark's own hosts and name, checked on the lower-cased URL /
# title / text exactly like the official rules.
WEBCODE_HOSTS = ("github.com/exa-labs", "exa-labs/benchmarks", "artificialanalysis.ai")
WEBCODE_HOST_PATTERNS = (re.compile(r"huggingface\.co/datasets/[^\s]*webcode"),)
WEBCODE_TERMS = (re.compile(r"\bwebcode\b"), re.compile(r"\bexa[- ]labs\b"))
ANSWER_MIN_CHARS = 15


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def webcode_reason(record: dict[str, Any], query: str, expected_answer: str) -> str | None:
    """Why a citation leaks WebCode specifically, or ``None``.

    ``webcode_host``: the benchmark repo, AA microevals, or a Hugging Face dataset named
    webcode. ``webcode_term``: the benchmark's name in URL, title or text. ``verbatim_query``:
    the whole normalized query appears in the text, the title, or the URL slug (WebCode
    queries are 37-90 character keyword strings, so the official rule's 60-character floor
    and text-only check are relaxed). ``answer_with_query``: text contains both the query and
    the expected answer (the answer alone is what a legitimate source page contains).
    """
    url = (record.get("url") or "").lower()
    title = record.get("title") or ""
    text = record.get("text") or ""
    if any(host in url for host in WEBCODE_HOSTS) or any(p.search(url) for p in WEBCODE_HOST_PATTERNS):
        return "webcode_host"
    haystack = normalize_text(f"{url} {title} {text}")
    if any(p.search(haystack) for p in WEBCODE_TERMS):
        return "webcode_term"
    needle = normalize_text(query)
    text_norm = normalize_text(text)
    if needle in text_norm or needle in normalize_text(title) or slug(query) in slug(url):
        return "verbatim_query"
    answer = normalize_text(expected_answer)
    if len(answer) >= ANSWER_MIN_CHARS and answer in text_norm and needle in text_norm:
        return "answer_with_query"
    return None


def leak_reason(record: dict[str, Any], query: str, expected_answer: str) -> str | None:
    return contamination_reason(record, None, query) or webcode_reason(record, query, expected_answer)


def load_gold() -> dict[str, dict[str, Any]]:
    rows = [json.loads(line) for line in GOLD.read_text().splitlines() if line.strip()]
    return {row["id"]: row for row in rows}


def run_dirs() -> list[tuple[str, Path]]:
    found = []
    for group, pattern in RUN_GLOBS:
        for path in sorted((BAKEOFF / "runs" / group).glob(pattern)):
            found.append((path.name.split("-webcode-rag-")[0], path))
    return found


def main() -> None:
    gold = load_gold()
    leaked_lines: list[dict[str, Any]] = []
    plan: list[dict[str, Any]] = []
    per_system: dict[str, dict[str, Any]] = {}
    reasons = collections.Counter()
    domains = collections.Counter()
    domain_reasons: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)

    for system, run in run_dirs():
        summary = json.loads((run / "summary.json").read_text())
        stats = {
            "run_dir": str(run),
            "tasks": 0,
            "graded": 0,
            "citations": 0,
            "leaked_citations": 0,
            "tasks_with_leak": 0,
            "tasks_leak_in_judge_sources": 0,
            "grounded_recorded_sum": 0.0,
            "grounded_recorded": summary["metrics"]["grounded"],
            "leak_tasks": [],
        }
        for tdir in sorted((run / "tasks").iterdir()):
            result_file = tdir / "result.json"
            grade_file = tdir / "grade.json"
            if not result_file.exists():
                continue
            stats["tasks"] += 1
            result = json.loads(result_file.read_text())
            task_id = result["task_id"]
            grade = json.loads(grade_file.read_text()) if grade_file.exists() else None
            if grade is not None:
                stats["graded"] += 1
                stats["grounded_recorded_sum"] += grade["scores"]["grounded"]
            judge_urls = set((grade or {}).get("details", {}).get("answer_source_urls") or [])
            g = gold[task_id]
            citations = result["citations"]
            stats["citations"] += len(citations)
            kept, leaked = [], []
            for index, citation in enumerate(citations, start=1):
                reason = leak_reason(citation, g["query"], g["expected_answer"])
                if reason is None:
                    kept.append(citation)
                    continue
                domain = urlparse((citation.get("url") or "").lower()).netloc
                judge_used = citation.get("url") in judge_urls
                leaked.append(index)
                reasons[reason] += 1
                domains[domain] += 1
                domain_reasons[domain][reason] += 1
                leaked_lines.append(
                    {
                        "system": system,
                        "task_id": task_id,
                        "citation_index": index,
                        "url": citation.get("url"),
                        "title": citation.get("title"),
                        "reason": reason,
                        "judge_used": judge_used,
                        "recorded_groundedness": (grade or {}).get("details", {}).get("groundedness"),
                    }
                )
            if not leaked:
                continue
            stats["leaked_citations"] += len(leaked)
            stats["tasks_with_leak"] += 1
            leak_in_judge = any(line["judge_used"] for line in leaked_lines[-len(leaked) :])
            if leak_in_judge:
                stats["tasks_leak_in_judge_sources"] += 1
            stats["leak_tasks"].append(task_id)
            plan.append(
                {
                    "system": system,
                    "task_id": task_id,
                    "run_dir": str(run),
                    "query": g["query"],
                    "expected_answer": g["expected_answer"],
                    "recorded_groundedness": (grade or {}).get("details", {}).get("groundedness"),
                    "recorded_grounded": (grade or {}).get("scores", {}).get("grounded"),
                    "leaked_indices": leaked,
                    "leak_in_judge_sources": leak_in_judge,
                    "remaining_citations": [
                        {"url": c["url"], "title": c["title"], "text": c["text"]} for c in kept
                    ],
                }
            )
        per_system[system] = stats

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "leaked_citations.jsonl").write_text(
        "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in leaked_lines)
    )
    (OUT / "regrade_plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False))
    audit = {
        "rules": {
            "official": "bakeoff.official_rag.contamination_reason (host, term, canary, verbatim_question)",
            "webcode_hosts": list(WEBCODE_HOSTS) + [p.pattern for p in WEBCODE_HOST_PATTERNS],
            "webcode_terms": [p.pattern for p in WEBCODE_TERMS],
            "verbatim_query": "whole normalized query in text, title, or URL slug (no length floor)",
            "answer_with_query": f"text contains both the query and the expected answer (answer >= {ANSWER_MIN_CHARS} chars)",
        },
        "per_system": per_system,
        "reasons": dict(reasons),
        "domains": {d: {"count": n, "reasons": dict(domain_reasons[d])} for d, n in domains.most_common()},
        "regrade_pairs": len(plan),
    }
    (OUT / "audit.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False))

    print(f"{'system':32s} {'cits':>6s} {'leaked':>6s} {'tasks>=1':>8s} {'judge-used':>10s} {'grounded':>9s}")
    for system, s in per_system.items():
        print(
            f"{system:32s} {s['citations']:6d} {s['leaked_citations']:6d} {s['tasks_with_leak']:8d} "
            f"{s['tasks_leak_in_judge_sources']:10d} {100 * s['grounded_recorded']:8.1f}%"
        )
    print("\nreasons:", dict(reasons))
    print("domains:")
    for d, n in domains.most_common():
        print(f"  {n:4d} {d} {dict(domain_reasons[d])}")
    print(f"\nre-grade pairs: {len(plan)}")


if __name__ == "__main__":
    main()
