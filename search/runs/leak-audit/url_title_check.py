"""URL- and title-level leak check of the WebCode runs the text-level audit did not cover.

The Expand, Tavily and Brave WebCode runs were made after ``audit.py`` ran, and the records it ran on
no longer carried citation text, so only the rules that read a citation's URL and title were applied: the official suites' ``host`` rule (``CONTAMINATION_HOSTS``) and ``term`` rule
(``CONTAMINATION_TERMS``, benchmark names in URL or title), and the WebCode extensions
``webcode_host``, ``webcode_term`` and ``verbatim_query`` (title and URL slug only). The text-only
rules (``canary``, ``verbatim_question``, ``answer_with_query``, ``verbatim_query`` on text) cannot run.

The committed records keep only citation counts (``../EXCLUDED.md``), so this needs a fresh WebCode run.

Usage (from the bakeoff root, offline):  .venv/bin/python -I runs/leak-audit/url_title_check.py
Writes runs/leak-audit/url_title_check.json and prints a table.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent)]
from audit import BAKEOFF, OUT, leak_reason, load_gold  # noqa: E402

SYSTEMS = ("rag-expand", "rag-tavily-advanced", "rag-brave-llm-context", "rag-perplexity-web", "rag-exa-lite-highlights", "rag-exa-auto-highlights")
REASONS = ("host", "term", "webcode_host", "webcode_term", "verbatim_query")


def main() -> None:
    gold = load_gold()
    report = {}
    for system in SYSTEMS:
        (run,) = sorted((BAKEOFF / "runs" / "webcode-rag").glob(f"{system}-webcode-rag-*"))
        counts: collections.Counter[str] = collections.Counter()
        citations = 0
        flagged = []
        for tdir in sorted((run / "tasks").iterdir()):
            result_file = tdir / "result.json"
            if not result_file.exists():
                continue
            result = json.loads(result_file.read_text())
            if "citations" not in result:
                raise SystemExit(f"{result_file}: no citation URLs or titles in the stored record; needs a fresh run")
            row = gold[result["task_id"]]
            for index, citation in enumerate(result.get("citations", [])):
                citations += 1
                record = {"url": citation.get("url"), "title": citation.get("title"), "text": ""}
                reason = leak_reason(record, row["query"], row["expected_answer"])
                if reason:
                    counts[reason] += 1
                    flagged.append({"task_id": result["task_id"], "index": index, "url": citation.get("url"), "reason": reason})
        report[system] = {
            "run_dir": str(run),
            "citations": citations,
            "flagged": sum(counts.values()),
            "by_reason": {reason: counts.get(reason, 0) for reason in REASONS},
            "flagged_citations": flagged,
        }
    (OUT / "url_title_check.json").write_text(json.dumps(report, indent=1) + "\n")
    print("| System | Citations | " + " | ".join(REASONS) + " | Flagged |")
    print("|---|---:|" + "---:|" * (len(REASONS) + 1))
    for system, r in report.items():
        print(f"| {system} | {r['citations']} | " + " | ".join(str(r["by_reason"][k]) for k in REASONS) + f" | {r['flagged']} |")
    for system, r in report.items():
        for f in r["flagged_citations"]:
            print(system, f["task_id"], f["reason"], f["url"])


if __name__ == "__main__":
    main()
