"""tools/strip_result_details.py: a stripped record reports the same numbers as the fresh one (offline)."""

import copy
import importlib.util
import json
import sys
from pathlib import Path

import tiktoken

BAKEOFF = Path(__file__).resolve().parents[1]
RUNS = BAKEOFF / "runs"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(RUNS))
strip = load("strip_result_details", BAKEOFF / "tools" / "strip_result_details.py")
report = load("runs_report", RUNS / "report.py")
from _records import citation_count, filtered_by_reason  # noqa: E402

FRESH_RESULT = {
    "task_id": "t-1",
    "prompt": "q",
    "answer": "a",
    "messages": [{"role": "user", "content": "q"}],
    "citations": [
        {"url": "https://a.example/1", "title": "One", "text": "first passage of text", "published_date": None},
        {"url": "https://b.example/2", "title": "Two", "text": "second", "published_date": "2026-01-01"},
    ],
    "filtered_results": [
        {"url": "https://huggingface.co/datasets/x", "title": "X", "reason": "host"},
        {"url": "https://c.example/sealqa", "title": "Y", "reason": "term"},
        {"url": "https://kaggle.com/z", "title": "Z", "reason": "host"},
    ],
    "skipped_results": [{"url": "https://d.example/", "reason": "empty_text"}],
    "latency_ms": 1.0,
}


def test_stripped_result_keeps_the_aggregates_the_reports_read():
    stripped = copy.deepcopy(FRESH_RESULT)
    removed = strip.strip_result(stripped)
    strip.mark(stripped, removed)
    assert "https://" not in json.dumps(stripped)
    assert "messages" not in stripped and "citations" not in stripped
    assert citation_count(stripped) == citation_count(FRESH_RESULT) == 2
    assert filtered_by_reason(stripped) == filtered_by_reason(FRESH_RESULT) == {"host": 2, "term": 1}
    assert stripped["skipped_results_by_reason"] == {"empty_text": 1}
    encoding = tiktoken.get_encoding("o200k_base")
    assert report.mean_citation_tokens(encoding, stripped) == report.mean_citation_tokens(encoding, FRESH_RESULT)
    assert stripped["citation_text_chars"] == len("first passage of text") + len("second")
    assert stripped["_redacted"]["removed"] == ["messages", "citations", "filtered_results", "skipped_results"]


def test_grade_and_aa_records_drop_urls_and_quotes_but_keep_counts():
    grade = {"task_id": "t-1", "scores": {"grounded": 1.0},
             "details": {"evidence": "[1] “quote”", "answer_source_urls": ["https://a.example/1"], "groundedness_reasoning": "r"}}
    assert strip.strip_grade(grade) == ["details.evidence", "details.answer_source_urls"]
    assert grade["details"] == {"groundedness_reasoning": "r", "num_answer_sources": 1}
    record = {"id": "aao-001", "trace": [], "tools": {"searches": [{"query": "q", "results": 10}],
              "fetches": [{"url": "https://a.example/", "latency_s": 0.1, "success": True}]}}
    assert strip.strip_aa(record) == ["trace", "tools.fetches[].url"]
    assert record["tools"]["fetches"] == [{"latency_s": 0.1, "success": True}]


def test_process_is_idempotent_and_keeps_the_file_format(tmp_path):
    path = tmp_path / "tasks" / "t-1" / "result.json"
    path.parent.mkdir(parents=True)
    raw = json.dumps(FRESH_RESULT, indent=1)
    once, removed = strip.process(path, raw)
    assert removed and once.startswith('{\n "task_id"')
    twice, removed_again = strip.process(path, once)
    assert twice == once and removed_again == []
