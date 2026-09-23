#!/usr/bin/env bash
# Post-deploy: restart the clemtock studio server on quasimodo and smoke-check it.
# A non-zero exit here is logged as a warning by Local-81 (does not fail the deploy).
set -uo pipefail
echo "[clemtock post-deploy] run=${LOCAL81_RUN_ID:-?} rc=${LOCAL81_DEPLOY_RC:-?}"
ssh -o BatchMode=yes -o ConnectTimeout=8 "${CLEMTOCK_HOST_ALIAS:-quasimodo}" 'bash -s' <<'REMOTE'
cd /app/clemtock || exit 1
if systemctl --user is-enabled clemtock.service >/dev/null 2>&1; then
  systemctl --user restart clemtock.service && echo "[clemtock] restarted clemtock.service"
else
  scripts/serve.sh restart
fi
sleep 3
curl -s -o /dev/null -w "[clemtock] studio http=%{http_code}\n" http://127.0.0.1:3053/
REMOTE
echo "[clemtock post-deploy] done"
