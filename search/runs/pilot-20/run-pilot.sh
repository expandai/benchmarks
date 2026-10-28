#!/bin/sh
# 20-task WebCode RAG pilot: one process per system, all at the same time, so every
# system searches the same live web. Keys are sourced here and never printed.
# Answer and judge models go through OpenRouter (BAKEOFF_LLM_TRANSPORT=openrouter);
# run hashes include the overlay implementation and effective transport endpoint.
# Usage: run-pilot.sh [system ...]   (default: the six pilot systems); env LIMIT (20), CONCURRENCY (5)
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
BAKEOFF=$(cd "$HERE/../.." && pwd)
export EXA_BENCH_VENV="${EXA_BENCH_VENV:-$BAKEOFF/.venv}"
. "$BAKEOFF/runs/env.sh"   # credentials from search/.env (never printed), caches
export BAKEOFF_LLM_TRANSPORT=openrouter
require_openrouter

LIMIT="${LIMIT:-20}"
CONCURRENCY="${CONCURRENCY:-5}"
if [ "$#" -gt 0 ]; then
  SYSTEMS="$*"
else
  SYSTEMS="rag-exa-fast-highlights rag-exa-instant-highlights rag-exa-webcode rag-parallel-turbo rag-perplexity-fast rag-firecrawl-search"
fi

mkdir -p "$HERE/logs"
PIDS=""
for S in $SYSTEMS; do
  (
    set +e   # bench exits 1 when any task failed; still record the wall time
    START=$(date +%s)
    "$BAKEOFF/bench" run --suite webcode-rag --system "$S" --limit "$LIMIT" \
      --concurrency "$CONCURRENCY" --runs-dir "$HERE" -o "$HERE/$S.json" \
      >"$HERE/logs/$S.log" 2>&1
    STATUS=$?
    END=$(date +%s)
    echo "$(date -u +%FT%TZ) $S limit=$LIMIT exit=$STATUS wall_s=$((END - START))" >>"$HERE/logs/wall.txt"
    exit "$STATUS"
  ) &
  PIDS="$PIDS $!"
done
STATUS=0
for PID in $PIDS; do
  if wait "$PID"; then :; else STATUS=1; fi
done
cat "$HERE/logs/wall.txt"
exit "$STATUS"
