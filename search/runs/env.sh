# Shared environment for the run scripts (runs/run-suite.sh, runs/pilot-20/run-pilot.sh, aa-stirrup/aa).
# Source it with BAKEOFF set to the bakeoff root (search/). Credentials come from $BAKEOFF/.env (copy
# .env.example; override the path with BAKEOFF_ENV_FILE) and are never printed or passed as arguments.
export TERM=dumb COLUMNS=120
# Pinned datasets come from the Hugging Face cache; plain HTTPS download, no Xet.
export HF_HOME="${HF_HOME:-$BAKEOFF/.hf-cache}" HF_HUB_DISABLE_XET=1 HF_HUB_DISABLE_TELEMETRY=1
export TIKTOKEN_CACHE_DIR="${TIKTOKEN_CACHE_DIR:-$BAKEOFF/.tiktoken-cache}"
ENV_FILE="${BAKEOFF_ENV_FILE:-$BAKEOFF/.env}"
if [ -f "$ENV_FILE" ]; then set -a; . "$ENV_FILE"; set +a; fi
unset OPENAI_API_KEY   # every model call goes through OpenRouter; never fall back to a direct OpenAI key
if [ -z "${OPENROUTER_API_KEY:-}" ] && [ -n "${OPEN_ROUTER_API_KEY:-}" ]; then
  OPENROUTER_API_KEY="$OPEN_ROUTER_API_KEY"
  export OPENROUTER_API_KEY
fi

require_openrouter() {
  if [ -z "${OPENROUTER_API_KEY:-}" ]; then
    echo "no OPENROUTER_API_KEY / OPEN_ROUTER_API_KEY in $ENV_FILE or the environment" >&2
    exit 2
  fi
}
