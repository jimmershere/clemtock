#!/usr/bin/env bash
# install-user-service.sh — run the clemtock studio as a systemd *user* service on quasimodo
# (survives logout when `sudo loginctl enable-linger $USER` has been run).
#   scripts/install-user-service.sh [--host 0.0.0.0] [--port 3053] | --remove
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="0.0.0.0"; PORT="3053"; REMOVE=0
while [ $# -gt 0 ]; do case "$1" in
  --host) HOST="$2"; shift 2 ;; --port) PORT="$2"; shift 2 ;; --remove) REMOVE=1; shift ;;
  *) echo "unknown arg $1" >&2; exit 2 ;; esac; done
UNIT_DIR="$HOME/.config/systemd/user"; UNIT="$UNIT_DIR/clemtock.service"
if [ "$REMOVE" = 1 ]; then
  systemctl --user disable --now clemtock.service 2>/dev/null || true
  rm -f "$UNIT"; systemctl --user daemon-reload; echo removed; exit 0
fi
mkdir -p "$UNIT_DIR"
sed -e "s|@ROOT@|$ROOT|g" -e "s|@HOST@|$HOST|g" -e "s|@PORT@|$PORT|g" -e "s|@PYTHON@|$(command -v python3)|g" \
    "$ROOT/systemd/clemtock.service" >"$UNIT"
systemctl --user daemon-reload && systemctl --user enable --now clemtock.service
sleep 2; systemctl --user --no-pager --lines=3 status clemtock.service || true
echo "→ http://$HOST:$PORT   (linger: $(loginctl show-user "$USER" -p Linger --value 2>/dev/null || echo unknown))"
