"""CLI: ``prepare`` a fixed question sample, ``preflight`` one search per system, ``run``, ``report``."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from . import llm, runner
from .omniscience import load_questions, sample_questions
from .report import markdown, summarize
from .systems import MODEL_ONLY, SYSTEMS, build_searcher
from .tools import NUM_RESULTS, render_results

STIRRUP_REPO = "https://github.com/ArtificialAnalysis/stirrup"
STIRRUP_COMMIT = "c092cee80ce09cd1dfb93aef053296a9ecd9dbb6"  # v0.2.1, 2026-10-22


def manifest_path(run_dir: Path) -> Path:
    return run_dir / "manifest.json"


def run_settings(transport: str) -> dict[str, Any]:
    return {
        "answer_model": llm.ANSWER_MODEL,
        "grader_model": llm.GRADER_MODEL,
        "reasoning_effort": llm.REASONING_EFFORT,
        "max_output_tokens": llm.MAX_OUTPUT_TOKENS,
        "max_turns": runner.MAX_TURNS,
        "num_results": NUM_RESULTS,
        "transport": transport,
    }


def validate_settings(manifest: dict[str, Any], transport: str) -> None:
    if (manifest["settings"] != run_settings(transport)
            or manifest["stirrup"]["commit"] != STIRRUP_COMMIT):
        raise ValueError("run settings differ from the manifest; use a new run directory")


def cmd_prepare(args: argparse.Namespace) -> int:
    run_dir = Path(args.run)
    path = manifest_path(run_dir)
    if args.n < 1:
        raise ValueError("n must be positive")
    questions = sample_questions(load_questions(), args.n, args.seed)
    if len(questions) != args.n:
        raise ValueError(f"requested {args.n} questions, but only {len(questions)} are available")
    if path.exists():
        existing = load_manifest(run_dir)
        if not args.resume:
            print(f"{path} exists; refusing to overwrite (use --resume)", file=sys.stderr)
            return 2
        validate_settings(existing, args.transport)
        if (existing["question_ids"] != [q.id for q in questions]
                or existing["seed"] != args.seed or existing["n"] != args.n):
            print(f"{path} has different sample or transport settings; use a new run directory", file=sys.stderr)
            return 2
        print(f"resuming {path}: {len(questions)} questions")
        return 0
    manifest: dict[str, Any] = {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "dataset": "ArtificialAnalysis/AA-Omniscience-Public (600), via bakeoff.suites.load_aa_omniscience",
        "seed": args.seed,
        "n": len(questions),
        "question_ids": [q.id for q in questions],
        "domains": {q.id: q.domain for q in questions},
        "stirrup": {"repo": STIRRUP_REPO, "commit": STIRRUP_COMMIT},
        "settings": run_settings(args.transport),
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=1))
    print(f"wrote {path}: {len(questions)} questions, seed {args.seed}")
    return 0


def load_manifest(run_dir: Path) -> dict[str, Any]:
    return json.loads(manifest_path(run_dir).read_text())


async def _preflight(systems: list[str], query: str) -> int:
    failures = 0
    for system in systems:
        if system == MODEL_ONLY:
            continue
        searcher = build_searcher(system)
        start = time.perf_counter()
        try:
            response = await searcher.run(query, NUM_RESULTS)
            xml = render_results(response.results)
            print(f"[{system}] ok {len(response.results)} results, {len(xml)} chars, "
                  f"cost={response.cost_usd}, {time.perf_counter() - start:.1f}s")  # fmt: skip
        except Exception as error:  # noqa: BLE001 - reported, not raised
            failures += 1
            print(f"[{system}] FAILED {type(error).__name__}: {str(error)[:300]}")
        finally:
            await searcher.close()
    return 1 if failures else 0


def cmd_preflight(args: argparse.Namespace) -> int:
    return asyncio.run(_preflight(args.systems, args.query))


async def _run(args: argparse.Namespace) -> int:
    run_dir = Path(args.run)
    manifest = load_manifest(run_dir)
    validate_settings(manifest, args.transport)
    wanted = set(manifest["question_ids"])
    questions = [q for q in load_questions() if q.id in wanted]
    if len(wanted) != manifest["n"] or {q.id for q in questions} != wanted:
        raise ValueError("manifest question IDs do not match the loaded dataset")
    order = {qid: i for i, qid in enumerate(manifest["question_ids"])}
    questions.sort(key=lambda q: order[q.id])
    if args.limit:
        questions = questions[: args.limit]
    failures = await asyncio.gather(
        *(runner.run_system(s, questions, run_dir, args.transport, args.concurrency) for s in args.systems)
    )
    return sum(failures)


def cmd_run(args: argparse.Namespace) -> int:
    return 1 if asyncio.run(_run(args)) else 0


def cmd_report(args: argparse.Namespace) -> int:
    run_dir = Path(args.run)
    expected = load_manifest(run_dir)["n"]
    summaries = [s for s in (summarize(run_dir, name, expected) for name in SYSTEMS) if s]
    (run_dir / "summary.json").write_text(json.dumps(summaries, indent=1))
    table = markdown(summaries)
    (run_dir / "summary.md").write_text(table + "\n")
    print(table)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aastirrup")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare")
    prepare.add_argument("--run", required=True)
    prepare.add_argument("--n", type=int, default=20)
    prepare.add_argument("--resume", action="store_true", help="reuse an existing matching manifest")
    prepare.add_argument("--seed", type=int, default=20261026)
    prepare.add_argument("--transport", choices=("responses", "chat"), default="responses")
    prepare.set_defaults(func=cmd_prepare)

    preflight = sub.add_parser("preflight")
    preflight.add_argument("--systems", nargs="+", default=list(SYSTEMS), choices=list(SYSTEMS))
    preflight.add_argument("--query", default="ASC 606 series of distinct goods or services criteria")
    preflight.set_defaults(func=cmd_preflight)

    run = sub.add_parser("run")
    run.add_argument("--run", required=True)
    run.add_argument("--systems", nargs="+", required=True, choices=list(SYSTEMS))
    run.add_argument("--transport", choices=("responses", "chat"), default="responses")
    run.add_argument("--concurrency", type=int, default=None, help="override per-system default")
    run.add_argument("--limit", type=int, default=None, help="first N questions of the manifest")
    run.set_defaults(func=cmd_run)

    report = sub.add_parser("report")
    report.add_argument("--run", required=True)
    report.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
