#!/usr/bin/env bash
# load-env.sh — assemble clemtock's runtime environment WITHOUT writing any secret to disk.
#
#   source scripts/load-env.sh
#
# Sources tee-empire's .env (OpenAI gpt-image-1 + OpenRouter) and pulls floor2-only keys
# (kie.ai, HeyGen, xAI, publish) over ssh into the CURRENT shell. Nothing is persisted.
# Must be sourced, not executed, so the exports survive.

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  echo "load-env.sh must be sourced:  source scripts/load-env.sh" >&2
  exit 1
fi

# --- control-host keys: OpenAI (gpt-image-1) + OpenRouter ---
_TEE_ENV="${CLEMTOCK_TEE_ENV:-/app/tee-empire/.env}"
if [ -f "$_TEE_ENV" ]; then
  set -a; . "$_TEE_ENV"; set +a
  echo "load-env: sourced $_TEE_ENV (OPENAI_API_KEY, OPENROUTER_API_KEY)"
else
  echo "load-env: WARN $_TEE_ENV not found — OpenAI image-gen will be unavailable" >&2
fi

# --- floor2-only keys: kie.ai, HeyGen, xAI (pulled over ssh, never stored) ---
_FLOOR2_HOST="${CLEMTOCK_FLOOR2_HOST:-floor2}"
_FLOOR2_ENV="${CLEMTOCK_FLOOR2_ENV:-/home/floor2/content-machine/.env.agents}"
_pull() {  # $1 = var name on floor2
  ssh -o ConnectTimeout=8 -o BatchMode=yes "$_FLOOR2_HOST" \
    "set -a; . '$_FLOOR2_ENV' 2>/dev/null; printf '%s' \"\$$1\"" 2>/dev/null
}
if ssh -o ConnectTimeout=8 -o BatchMode=yes "$_FLOOR2_HOST" true 2>/dev/null; then
  export KIEAI_API_KEY="$(_pull KIEAI_API_KEY)"
  export HEYGEN_API_KEY="$(_pull HEYGEN_API_KEY)"
  export HEYGEN_VOICE_CLONE_ID="$(_pull HEYGEN_VOICE_CLONE_ID)"
  export HEYGEN_CARTOON_AVATAR_ID="$(_pull HEYGEN_CARTOON_AVATAR_ID)"
  export XAI_API_KEY="$(_pull XAI_API_KEY)"
  # prefer the control-host OpenRouter key; fall back to floor2's if unset
  [ -z "${OPENROUTER_API_KEY:-}" ] && export OPENROUTER_API_KEY="$(_pull OPENROUTER_API_KEY)"
  echo "load-env: pulled floor2 keys (KIEAI, HEYGEN, XAI) from $_FLOOR2_HOST:$_FLOOR2_ENV"
else
  echo "load-env: WARN cannot reach '$_FLOOR2_HOST' — video/avatar gen unavailable" >&2
fi

# default non-secret model config
export OPENROUTER_IMAGE_MODEL="${OPENROUTER_IMAGE_MODEL:-black-forest-labs/flux-schnell}"
export CLEMTOCK_SCRIPT_MODEL="${CLEMTOCK_SCRIPT_MODEL:-anthropic/claude-sonnet-4.5}"
export KIEAI_MODEL="${KIEAI_MODEL:-flux-kontext-pro}"
unset -f _pull
echo "load-env: ready. Run scripts/probe-providers.sh to verify."
