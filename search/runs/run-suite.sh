#!/bin/sh
# One suite, one `bench run` process per system, all at the same time, so every system searches the
# same live web. Credentials and caches from runs/env.sh (keys sourced, never printed); answer and judge
# models go through OpenRouter (BAKEOFF_LLM_TRANSPORT=openrouter).
#
# Usage: run-suite.sh SUITE [system ...]
#        SUITE is a harness suite (webcode-rag, seal-0, ...; output under runs/SUITE/) or an
#        official-grader suite (*-official; output under runs/official/SUITE/, judge fixed per suite:
#        gpt-4.1 for frames-official and simpleqa-verified-official, gpt-4o-mini for the SealQA suites,
#        which refuse any other).
#        Default systems: the six original competitors (harness suites); model-only and the seven
#        systems of the first window (official suites).
# Env:   LIMIT (default: whole suite), CONCURRENCY (default 10), PASSES (default 4),
#        DEEPSEEK_CONCURRENCY (default 4), EXPAND_CONCURRENCY (default 3 on the official suites, no cap
#        elsewhere); a system's concurrency is min(CONCURRENCY, its cap). DRY_RUN=1: preflight only.
#
# Resumable. A pass that ends with failed tasks (bench exit 1) is followed by another pass after a
# backoff (60 s, 120 s, 240 s ...); the runner skips every task with a grade.json, so a pass only
# re-runs tasks that ended in an execution error, never a graded wrong answer.
# Output: <out>/<system>-SUITE-<hash>/, <out>/<system>.json, <out>/logs/ (wall.txt: one line per pass).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
BAKEOFF=$(cd "$HERE/.." && pwd)
SUITE="$1"
shift
export EXA_BENCH_VENV="${EXA_BENCH_VENV:-$BAKEOFF/.venv}"
. "$HERE/env.sh"
export BAKEOFF_LLM_TRANSPORT=openrouter

JUDGE=""
case "$SUITE" in
  frames-official|simpleqa-verified-official) JUDGE=openai/gpt-4.1 ;;
  seal-0-official|seal-hard-official) JUDGE=openai/gpt-4o-mini ;;
  *-official) echo "unknown official suite $SUITE" >&2; exit 2 ;;
esac
if [ -n "$JUDGE" ]; then
  OUT="$HERE/official/$SUITE"
  JUDGE_ARGS="--judge-model $JUDGE"
  EXPAND_CAP="${EXPAND_CONCURRENCY:-3}"
  DEFAULT_SYSTEMS="rag-model-only rag-perplexity-fast rag-exa-fast-highlights rag-parallel-turbo rag-parallel-fast rag-firecrawl-search rag-deepseek"
else
  OUT="$HERE/$SUITE"
  JUDGE_ARGS=""
  EXPAND_CAP="${EXPAND_CONCURRENCY:-}"
  DEFAULT_SYSTEMS="rag-exa-fast-highlights rag-exa-instant-highlights rag-exa-webcode rag-parallel-turbo rag-perplexity-fast rag-firecrawl-search"
fi

CONCURRENCY="${CONCURRENCY:-10}"
PASSES="${PASSES:-4}"
LIMIT_ARGS=""
if [ -n "${LIMIT:-}" ]; then LIMIT_ARGS="--limit $LIMIT"; fi
if [ "$#" -gt 0 ]; then SYSTEMS="$*"; else SYSTEMS="$DEFAULT_SYSTEMS"; fi

if [ -n "${DRY_RUN:-}" ]; then
  # Preflight only (credentials, data pins, suite/system compatibility); no paid call.
  # shellcheck disable=SC2086
  exec "$BAKEOFF/bench" run --suite "$SUITE" --system $SYSTEMS $LIMIT_ARGS $JUDGE_ARGS --dry-run
fi
require_openrouter

mkdir -p "$OUT/logs"
PIDS=""
for S in $SYSTEMS; do
  C="$CONCURRENCY"
  case "$S" in
    *deepseek*) if [ "${DEEPSEEK_CONCURRENCY:-4}" -lt "$C" ]; then C="${DEEPSEEK_CONCURRENCY:-4}"; fi ;;
    *expand*)   if [ -n "$EXPAND_CAP" ] && [ "$EXPAND_CAP" -lt "$C" ]; then C="$EXPAND_CAP"; fi ;;
  esac
  (
    set +e   # bench exits 1 when any task failed
    PASS=1
    DELAY=60
    while :; do
      START=$(date +%s)
      # shellcheck disable=SC2086
      "$BAKEOFF/bench" run --suite "$SUITE" --system "$S" $LIMIT_ARGS $JUDGE_ARGS \
        --concurrency "$C" --runs-dir "$OUT" -o "$OUT/$S.json" \
        >>"$OUT/logs/$S.log" 2>&1
      STATUS=$?
      END=$(date +%s)
      echo "$(date -u +%FT%TZ) $S limit=${LIMIT:-all} pass=$PASS exit=$STATUS wall_s=$((END - START)) concurrency=$C${JUDGE:+ judge=$JUDGE}" >>"$OUT/logs/wall.txt"
      if [ "$STATUS" -ne 1 ] || [ "$PASS" -ge "$PASSES" ]; then exit "$STATUS"; fi
      sleep "$DELAY"
      PASS=$((PASS + 1))
      DELAY=$((DELAY * 2))
    done
  ) &
  PIDS="$PIDS $!"
done
STATUS=0
for PID in $PIDS; do
  if wait "$PID"; then :; else STATUS=1; fi
done
cat "$OUT/logs/wall.txt"
exit "$STATUS"
