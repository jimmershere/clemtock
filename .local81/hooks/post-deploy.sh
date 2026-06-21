#!/usr/bin/env bash
# Post-deploy: restart the clemtock control server on floor2 and smoke-check it.
# A non-zero exit here is logged as a warning by Local-81 (does not fail the deploy).
set -uo pipefail
echo "[clemtock post-deploy] run=${LOCAL81_RUN_ID:-?} rc=${LOCAL81_DEPLOY_RC:-?}"
ssh -o BatchMode=yes -o ConnectTimeout=8 floor2 '
  cd /home/floor2/clemtock/backend
  pkill -f clemtock.server 2>/dev/null; sleep 1
  nohup setsid python3 -u -m clemtock.server --port 3053 >/home/floor2/clemtock/out/server.log 2>&1 </dev/null & disown
  sleep 3
  curl -s -o /dev/null -w "[clemtock] studio http=%{http_code}\n" http://127.0.0.1:3053/
'
echo "[clemtock post-deploy] done"
