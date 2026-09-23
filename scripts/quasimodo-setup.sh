#!/usr/bin/env bash
# quasimodo-setup.sh — one-shot: install what clemtock needs on THIS host and verify.
# Run on quasimodo as jimbro (has sudo):   cd /app/clemtock && bash scripts/quasimodo-setup.sh
# Detects the package manager; prints what it would do first, then asks.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
PKGS_APT="ffmpeg chromium python3 python3-cryptography nodejs npm curl"
echo "== clemtock on $(hostname) =="
for t in python3 ffmpeg chromium chromium-browser node npm curl; do printf '%-16s %s\n' "$t" "$(command -v $t 2>/dev/null || echo MISSING)"; done
python3 -c 'import cryptography' 2>/dev/null && echo "python-cryptography  present" || echo "python-cryptography  MISSING (vault optional)"
if command -v apt-get >/dev/null; then
  read -r -p "sudo apt-get install -y $PKGS_APT ? [y/N] " a
  if [ "${a,,}" = y ]; then sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq $PKGS_APT; fi
else
  echo "no apt-get here — install ffmpeg, chromium, node/npm, python3-cryptography with your package manager" >&2
fi
[ -d node_modules/playwright-core ] || { command -v npm >/dev/null && npm install --no-audit --no-fund; }
mkdir -p out uploads
echo; echo "== env =="; source scripts/load-env.sh; echo; bash scripts/probe-providers.sh
echo; echo "next: scripts/serve.sh start   (or scripts/install-user-service.sh)   → http://$(hostname -I 2>/dev/null | awk '{print $1}'):3053"
