#!/usr/bin/env bash
# load-env.sh — put the provider keys into the CURRENT shell without writing any secret to disk.
#
#   source scripts/load-env.sh
#
# Reads, in order and without overriding what is already exported:
#   /app/portrender/.env   (the OpenAI key jimmer keeps there — shared with portrender)
#   /app/clemtock/.env     (kie.ai / HeyGen / xAI / PostBridge keys, if you put them here)
#   /app/tee-empire/.env   (OpenRouter, Printify — when tee-empire is cloned on this host)
# Override the list with CLEMTOCK_ENV_FILES=a:b:c. The Python side (config.load_env_files)
# reads the same list, so `clemtock …` and the studio server work without sourcing this.
# Everything runs on this host; nothing is pulled over ssh.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  echo "load-env.sh must be sourced:  source scripts/load-env.sh" >&2
  exit 1
fi
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_files="${CLEMTOCK_ENV_FILES:-/app/portrender/.env:$_here/.env:/app/tee-empire/.env}"
IFS=: read -r -a _list <<<"$_files"
for f in "${_list[@]}"; do
  [ -f "$f" ] || continue
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue ;; esac
    line="${line#export }"
    k="${line%%=*}"; v="${line#*=}"; v="${v%%$'\r'}"
    case "$v" in \"*\") v="${v#\"}"; v="${v%\"}" ;; \'*\') v="${v#\'}"; v="${v%\'}" ;; *) v="${v%% #*}" ;; esac
    [ -z "$k" ] || [ -z "$v" ] && continue
    [ -n "${!k:-}" ] && continue
    export "$k=$v"
  done <"$f"
  echo "load-env: read $f"
done
# non-secret model defaults
export OPENROUTER_IMAGE_MODEL="${OPENROUTER_IMAGE_MODEL:-black-forest-labs/flux-schnell}"
export CLEMTOCK_SCRIPT_MODEL="${CLEMTOCK_SCRIPT_MODEL:-anthropic/claude-sonnet-4.5}"
export CLEMTOCK_IMAGE_MODEL="${CLEMTOCK_IMAGE_MODEL:-${PORTRENDER_MODEL:-gpt-image-2}}"
export KIEAI_MODEL="${KIEAI_MODEL:-flux-kontext-pro}"
for k in OPENAI_API_KEY OPENROUTER_API_KEY KIEAI_API_KEY HEYGEN_API_KEY XAI_API_KEY POST_BRIDGE_API_KEY; do
  [ -n "${!k:-}" ] && echo "load-env: $k present" || echo "load-env: $k missing" >&2
done
unset _here _files _list f line k v
echo "load-env: ready. Run scripts/probe-providers.sh to verify."
