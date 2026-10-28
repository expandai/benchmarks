"""Reduce the stored run records to per-record aggregates: no per-result URL, title or text.

Applied uniformly to every system and suite (runs/EXCLUDED.md lists what each record keeps):

* ``runs/**/tasks/*/result.json``: ``citations`` becomes ``num_citations``, ``citation_text_tokens``
  and ``citation_text_chars`` (sums of the per-citation counts; o200k_base tokens, the unit the
  tables report); ``filtered_results`` / ``skipped_results`` become ``*_by_reason`` counts;
  ``messages`` (the answer prompt) is dropped.
* ``runs/**/tasks/*/grade.json``: ``details.evidence`` and ``details.answer_source_urls`` are
  dropped; ``details.num_answer_sources`` keeps the count.
* ``aa-stirrup/runs/**/aao-*.json`` and the superseded attempts under ``attempts/aao-*/``: ``trace``
  and every ``tools.fetches[].url`` are dropped (fetch latency, success and filter flags stay).
* ``runs/leak-audit/`` outputs: citation URLs, titles and judge evidence quotes are dropped; counts,
  reasons, indices and verdicts stay.

Questions, answers, judge labels and reasoning, scores, costs, latencies and token counts are not
touched. Every record that changes records the removed fields in ``_redacted``. A fresh run writes
full records; run this on them before committing (``CONTRIBUTING.md``). Citation ``text`` in a
fresh record is counted with tiktoken, so run it with the bakeoff venv then:

    python3 -I tools/strip_result_details.py            # rewrite in place, print the counts
    python3 -I tools/strip_result_details.py --check    # exit 1 if anything would change (CI)
    .venv/bin/python -I tools/strip_result_details.py   # fresh records that still carry citation text

Idempotent: a stripped record is left byte-identical. Each file keeps its indent and escaping.
"""
from __future__ import annotations

import collections
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ROOTS = [ROOT / "runs", ROOT / "aa-stirrup" / "runs"]
LEAK_AUDIT = ROOT / "runs" / "leak-audit"
SEE = "runs/EXCLUDED.md"
_ENCODING: Any = None


def text_tokens(text: str) -> int:
    global _ENCODING
    if _ENCODING is None:
        import tiktoken  # only fresh records carry text; the stored ones have the counts

        _ENCODING = tiktoken.get_encoding("o200k_base")
    return len(_ENCODING.encode(text, disallowed_special=()))


def citation_counts(citation: dict[str, Any]) -> tuple[int, int]:
    """(tokens, chars) of one citation, from the stored counts or the text itself."""
    if "text_tokens" in citation:
        return int(citation["text_tokens"]), int(citation.get("text_chars", 0))
    text = citation.get("text") or ""
    return text_tokens(text), len(text)


def by_reason(items: list[dict[str, Any]]) -> dict[str, int]:
    return dict(collections.Counter(item.get("reason", "?") for item in items))


def mark(record: dict[str, Any], removed: list[str]) -> None:
    if not removed:
        return
    redacted = record.setdefault("_redacted", {"removed": [], "see": SEE})
    redacted["removed"] += [field for field in removed if field not in redacted["removed"]]


def strip_result(record: dict[str, Any]) -> list[str]:
    removed = []
    out: dict[str, Any] = {}
    for key, value in record.items():
        if key == "messages":
            removed.append(key)
        elif key == "citations" and isinstance(value, list):
            counts = [citation_counts(c) for c in value]
            out["num_citations"] = len(value)
            out["citation_text_tokens"] = sum(t for t, _c in counts)
            out["citation_text_chars"] = sum(c for _t, c in counts)
            removed.append(key)
        elif key in ("filtered_results", "skipped_results") and isinstance(value, list):
            out[f"{key}_by_reason"] = by_reason(value)
            removed.append(key)
        else:
            out[key] = value
    record.clear()
    record.update(out)
    return removed


def strip_grade(record: dict[str, Any]) -> list[str]:
    details = record.get("details", {})
    removed = []
    if "evidence" in details:
        del details["evidence"]
        removed.append("details.evidence")
    if "answer_source_urls" in details:
        details["num_answer_sources"] = len(details.pop("answer_source_urls") or [])
        removed.append("details.answer_source_urls")
    return removed


def strip_aa(record: dict[str, Any]) -> list[str]:
    removed = []
    if "trace" in record:
        del record["trace"]
        removed.append("trace")
    fetches = record.get("tools", {}).get("fetches", [])
    if any("url" in fetch for fetch in fetches):
        for fetch in fetches:
            fetch.pop("url", None)
        removed.append("tools.fetches[].url")
    return removed


def strip_leak_audit(name: str, data: Any) -> bool:
    """The leak-audit outputs keep counts, reasons, indices and verdicts; True if anything was dropped."""
    changed = False

    def drop(obj: dict[str, Any], *keys: str) -> None:
        nonlocal changed
        for key in keys:
            if key in obj:
                del obj[key]
                changed = True

    if name == "leaked_citations.jsonl":
        for line in data:
            drop(line, "url", "title")
    elif name == "regrade_plan.json":
        for pair in data:
            kept = pair.get("remaining_citations")
            if isinstance(kept, list):
                counts = [citation_counts(c) for c in kept]
                pair["remaining_citations"] = len(kept)
                pair["remaining_citation_text_tokens"] = sum(t for t, _c in counts)
                changed = True
    elif name == "regrades.json":
        for regrade in data.values():
            drop(regrade, "answer_source_urls", "evidence")
    elif name == "regrade_repeats.json":
        for repeats in data.values():
            for repeat in repeats:
                drop(repeat, "evidence")
    elif name == "url_title_check.json":
        for system in data.values():
            for flagged in system.get("flagged_citations", []):
                drop(flagged, "url")
    return changed


def dumps(data: Any, raw: str) -> str:
    """Serialise like the file it came from: same indent, escaping and trailing newline."""
    second = raw.split("\n", 2)[1] if raw.count("\n") >= 1 else ""
    indent = len(second) - len(second.lstrip(" ")) or None
    ensure_ascii = raw.isascii() and "\\u" in raw
    return json.dumps(data, indent=indent, ensure_ascii=ensure_ascii) + ("\n" if raw.endswith("\n") else "")


def is_aa_record(path: Path) -> bool:
    if path.suffix != ".json":
        return False
    return path.name.startswith("aao-") or (path.parent.name.startswith("aao-") and path.parent.parent.name == "attempts")


def process(path: Path, raw: str) -> tuple[str, list[str]]:
    """The rewritten text (``raw`` when nothing changes) and the removed fields."""
    if path.parent == LEAK_AUDIT and path.name == "leaked_citations.jsonl":
        lines = [json.loads(line) for line in raw.splitlines() if line.strip()]
        if not strip_leak_audit(path.name, lines):
            return raw, []
        ensure_ascii = raw.isascii() and "\\u" in raw
        return "".join(json.dumps(line, ensure_ascii=ensure_ascii) + "\n" for line in lines), ["url", "title"]
    data = json.loads(raw)
    if path.parent == LEAK_AUDIT:
        return (dumps(data, raw), ["leak-audit"]) if strip_leak_audit(path.name, data) else (raw, [])
    if path.name == "result.json" and path.parent.parent.name == "tasks":
        removed = strip_result(data)
    elif path.name == "grade.json" and path.parent.parent.name == "tasks":
        removed = strip_grade(data)
    elif is_aa_record(path):
        removed = strip_aa(data)
    else:
        return raw, []
    if not removed:
        return raw, []
    mark(data, removed)
    return dumps(data, raw), removed


def candidates() -> list[Path]:
    found = []
    for root in ROOTS:
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                path = Path(dirpath) / name
                if name in ("result.json", "grade.json") or is_aa_record(path):
                    found.append(path)
                elif path.parent == LEAK_AUDIT and path.suffix in (".json", ".jsonl"):
                    found.append(path)
    return sorted(found)


def main() -> int:
    check = "--check" in sys.argv
    changed = 0
    fields: collections.Counter[str] = collections.Counter()
    for path in candidates():
        raw = path.read_text(encoding="utf-8")
        updated, removed = process(path, raw)
        if updated == raw:
            continue
        changed += 1
        kind = "aao-*.json" if is_aa_record(path) else path.name
        fields.update(f"{kind}: {field}" for field in removed)
        if not check:
            path.write_text(updated, encoding="utf-8")
    for field, count in sorted(fields.items()):
        print(f"{count:8d} {field}")
    print(f"{'would change' if check else 'stripped'} {changed} file(s)")
    return 1 if (check and changed) else 0


if __name__ == "__main__":
    sys.exit(main())
