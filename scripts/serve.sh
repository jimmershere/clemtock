#!/usr/bin/env bash
# serve.sh — start/stop/status the clemtock studio server (0.0.0.0:3053) as a detached process.
#   scripts/serve.sh start [--host 0.0.0.0] [--port 3053] | stop | restart | status | logs
# Boot-persistent alternative: scripts/install-user-service.sh (systemd user unit + linger).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID="$ROOT/out/clemtock.pid"; LOG="$ROOT/out/server.log"
PY="${CLEMTOCK_PYTHON:-$(command -v python3)}"
cmd="${1:-status}"; shift || true
# setsid forks, so the pid observable at launch is not always the pid the server
# settles on. Trust the pidfile when live, else re-resolve and heal it — without
# this, stop/status/restart say "not running" while the studio is serving.
srv_pid() { pgrep -f "\-m clemtock.server" | head -n1; }
running() {
  if [[ -f "$PID" ]] && kill -0 "$(cat "$PID")" 2>/dev/null; then return 0; fi
  local srv; srv="$(srv_pid || true)"
  [[ -n "$srv" ]] && { echo "$srv" >"$PID"; return 0; }
  return 1
}
case "$cmd" in
  start)
    if running; then echo "already running (pid $(cat "$PID"))"; exit 0; fi
    mkdir -p "$ROOT/out"; cd "$ROOT/backend"
    nohup setsid "$PY" -u -m clemtock.server "$@" >>"$LOG" 2>&1 </dev/null &
    disown || true; sleep 2
    rm -f "$PID"            # running() re-resolves and writes the real pid
    if running; then tail -n 3 "$LOG"; else echo "failed to start — see $LOG"; exit 1; fi ;;
  stop) if running; then kill "$(cat "$PID")" && rm -f "$PID" && echo stopped; else echo "not running"; rm -f "$PID"; fi ;;
  restart) "$0" stop; "$0" start "$@" ;;
  status) if running; then echo "running (pid $(cat "$PID"))"; tail -n 1 "$LOG"; else echo "not running"; exit 1; fi ;;
  logs) tail -n 50 -f "$LOG" ;;
  *) echo "usage: $0 start|stop|restart|status|logs [--host H --port P]" >&2; exit 2 ;;
esac
