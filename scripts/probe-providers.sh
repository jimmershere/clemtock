#!/usr/bin/env bash
# probe-providers.sh — auth-only health check for every clemtock provider.
# Prints HTTP status codes only; never spends generation credits, never prints a key.
# Run AFTER `source scripts/load-env.sh`.

code() { curl -s -m 12 -o /dev/null -w "%{http_code}" "$@" 2>/dev/null || echo ERR; }
ok()   { case "$1" in 200|201) echo "OK  ($1)";; 000|ERR) echo "UNREACHABLE ($1)";; *) echo "FAIL ($1)";; esac; }

echo "== clemtock provider probe =="

if [ -n "${OPENAI_API_KEY:-}" ]; then
  echo "OpenAI Images        : $(ok "$(code -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models)")"
else echo "OpenAI Images        : SKIP (OPENAI_API_KEY unset)"; fi

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

# local script brain — no key, just a daemon on this host
_OLL="${OLLAMA_HOST:-http://127.0.0.1:11434}"; case "$_OLL" in http*) ;; *) _OLL="http://$_OLL";; esac
if curl -s -m 5 -o /dev/null "$_OLL/api/tags" 2>/dev/null; then
  echo "ollama (script)      : OK  ($(curl -s -m 5 "$_OLL/api/tags" | python3 -c 'import sys,json; m=[x["name"] for x in json.load(sys.stdin).get("models",[])]; print(", ".join(m) if m else "NO MODELS PULLED")' 2>/dev/null))"
else echo "ollama (script)      : DOWN ($_OLL) — systemctl --user start ollama"; fi

# rented GPU render farm — read-only probe, never rents
if [ -n "${VAST_API_KEY:-}" ]; then
  echo "vast.ai (gpu)        : $(curl -s -m 12 -H "Authorization: Bearer $VAST_API_KEY" \
    https://console.vast.ai/api/v0/users/current/ 2>/dev/null \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print("OK  credit $%.2f" % (float(d.get("credit") or 0)+float(d.get("balance") or 0)))' 2>/dev/null || echo FAIL)"
  echo "vast.ai instances    : $(curl -s -m 12 -H "Authorization: Bearer $VAST_API_KEY" \
    https://console.vast.ai/api/v1/instances/ 2>/dev/null \
    | python3 -c 'import sys,json; i=json.load(sys.stdin).get("instances") or []; print("%d running, $%.3f/hr burning" % (len(i), sum(float(x.get("dph_total") or 0) for x in i)))' 2>/dev/null || echo FAIL)"
else echo "vast.ai (gpu)        : SKIP (VAST_API_KEY unset)"; fi

# local toolchain (everything renders on this host)
echo "ffmpeg (local)       : $(command -v ffmpeg >/dev/null && ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f1-3 || echo MISSING — sudo apt install ffmpeg)"
# CLEMTOCK_CHROMIUM (set in .env.local) wins: a playwright-managed chromium is a
# real browser even when no system package is installed, so check it before apt.
echo "chromium (local)     : $([ -x "${CLEMTOCK_CHROMIUM:-}" ] && echo "OK (\$CLEMTOCK_CHROMIUM)" || for c in chromium chromium-browser google-chrome /snap/bin/chromium; do command -v $c >/dev/null 2>&1 && { echo "OK ($c)"; break; }; done || echo "MISSING — sudo apt install chromium, or set CLEMTOCK_CHROMIUM")"
echo "node (local)         : $(command -v node >/dev/null && node -v || echo MISSING)"
echo "playwright-core      : $([ -d "$(dirname "$0")/../node_modules/playwright-core" ] && echo OK || echo "MISSING — npm install in /app/clemtock")"
echo "python cryptography  : $(python3 -c 'import cryptography; print("OK", cryptography.__version__)' 2>/dev/null || echo "MISSING (vault disabled; .env files still work) — sudo apt install python3-cryptography")"
