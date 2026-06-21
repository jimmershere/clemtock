#!/usr/bin/env bash
# probe-providers.sh — auth-only health check for every clemtock provider.
# Prints HTTP status codes only; never spends generation credits, never prints a key.
# Run AFTER `source scripts/load-env.sh`.

code() { curl -s -m 12 -o /dev/null -w "%{http_code}" "$@" 2>/dev/null || echo ERR; }
ok()   { case "$1" in 200|201) echo "OK  ($1)";; 000|ERR) echo "UNREACHABLE ($1)";; *) echo "FAIL ($1)";; esac; }

echo "== clemtock provider probe =="

if [ -n "${OPENAI_API_KEY:-}" ]; then
  echo "OpenAI gpt-image-1   : $(ok "$(code -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models)")"
else echo "OpenAI gpt-image-1   : SKIP (OPENAI_API_KEY unset)"; fi

if [ -n "${OPENROUTER_API_KEY:-}" ]; then
  echo "OpenRouter (script)  : $(ok "$(code -H "Authorization: Bearer $OPENROUTER_API_KEY" https://openrouter.ai/api/v1/key)")"
else echo "OpenRouter (script)  : SKIP (OPENROUTER_API_KEY unset)"; fi

if [ -n "${KIEAI_API_KEY:-}" ]; then
  echo "kie.ai (video)       : $(ok "$(code -H "Authorization: Bearer $KIEAI_API_KEY" https://api.kie.ai/api/v1/chat/credit)")"
else echo "kie.ai (video)       : SKIP (KIEAI_API_KEY unset)"; fi

if [ -n "${HEYGEN_API_KEY:-}" ]; then
  echo "HeyGen (avatar+voice): $(ok "$(code -H "X-Api-Key: $HEYGEN_API_KEY" https://api.heygen.com/v2/user/remaining_quota)")"
else echo "HeyGen (avatar+voice): SKIP (HEYGEN_API_KEY unset)"; fi

if [ -n "${XAI_API_KEY:-}" ]; then
  echo "Grok / xAI (alt LLM) : $(ok "$(code -H "Authorization: Bearer $XAI_API_KEY" https://api.x.ai/v1/models)")"
else echo "Grok / xAI (alt LLM) : SKIP (XAI_API_KEY unset)"; fi

echo "ffmpeg on floor2     : $(ssh -o ConnectTimeout=8 -o BatchMode=yes "${CLEMTOCK_FLOOR2_HOST:-floor2}" 'command -v ffmpeg >/dev/null && echo OK || echo MISSING' 2>/dev/null || echo UNREACHABLE)"
