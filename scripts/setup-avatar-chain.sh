#!/usr/bin/env bash
# setup-avatar-chain.sh — install the free, local cartoon-avatar chain.
#
#   Chatterbox (TTS, MIT)  +  Rhubarb (lip sync, MIT)  +  ffmpeg  =  talking mascot
#
# No GPU, no API key, no per-clip fee. See docs/render-pipeline.md.
#
#   bash scripts/setup-avatar-chain.sh            # install everything missing
#   bash scripts/setup-avatar-chain.sh --check    # report only, change nothing
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
CHECK=0; [ "${1:-}" = "--check" ] && CHECK=1

RHUBARB_VERSION="1.14.0"
VENV="$ROOT/.venv"
VENDOR="$ROOT/vendor"

say() { printf '%-22s %s\n' "$1" "$2"; }
have() { command -v "$1" >/dev/null 2>&1; }

echo "== cartoon avatar chain on $(hostname) =="

# ---------- ffmpeg (compositing + muxing) ----------
if have ffmpeg; then say "ffmpeg" "OK ($(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f3))"
elif [ "$CHECK" = 1 ]; then say "ffmpeg" "MISSING — sudo apt install ffmpeg"
else sudo -n apt-get install -y -qq ffmpeg </dev/null && say "ffmpeg" "installed"; fi

# ---------- ImageMagick (placeholder sprites; library thumbnails) ----------
if have convert; then say "imagemagick" "OK"
elif [ "$CHECK" = 1 ]; then say "imagemagick" "MISSING — sudo apt install imagemagick"
else sudo -n apt-get install -y -qq imagemagick </dev/null && say "imagemagick" "installed"; fi

# ---------- Rhubarb (audio -> mouth shapes) ----------
if [ -x "$VENDOR/rhubarb/rhubarb" ]; then
  say "rhubarb" "OK ($("$VENDOR/rhubarb/rhubarb" --version 2>&1 | grep -v "^$" | tail -1))"
elif [ "$CHECK" = 1 ]; then
  say "rhubarb" "MISSING — re-run without --check"
else
  echo "  fetching Rhubarb $RHUBARB_VERSION (~87 MB, MIT) …"
  mkdir -p "$VENDOR"
  tmp="$(mktemp -d)"
  url="https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v${RHUBARB_VERSION}/Rhubarb-Lip-Sync-${RHUBARB_VERSION}-Linux.zip"
  if curl -fL --retry 3 -o "$tmp/r.zip" "$url" && unzip -q -o "$tmp/r.zip" -d "$tmp"; then
    rm -rf "$VENDOR/rhubarb"
    mv "$tmp/Rhubarb-Lip-Sync-${RHUBARB_VERSION}-Linux" "$VENDOR/rhubarb"
    chmod +x "$VENDOR/rhubarb/rhubarb"
    say "rhubarb" "installed $("$VENDOR/rhubarb/rhubarb" --version 2>&1 | grep -v "^$" | tail -1)"
  else
    say "rhubarb" "DOWNLOAD FAILED — $url"
  fi
  rm -rf "$tmp"
fi

# ---------- Chatterbox (TTS + voice cloning) ----------
# Lives in a venv, not in clemtock's runtime: the app itself stays stdlib-only and
# still imports on a host with no venv. providers/chatterbox_voice.py shells out here.
if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c "import chatterbox" 2>/dev/null; then
  say "chatterbox" "OK ($("$VENV/bin/python" -c 'import torch;print("torch",torch.__version__)' 2>/dev/null))"
elif [ "$CHECK" = 1 ]; then
  say "chatterbox" "MISSING — re-run without --check (~3 GB)"
else
  if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV" || { say "chatterbox" "venv failed — sudo apt install python3.12-venv"; exit 1; }
  fi
  "$VENV/bin/pip" install --quiet --upgrade pip
  echo "  installing chatterbox-tts (~3 GB) …"
  "$VENV/bin/pip" install --quiet chatterbox-tts
  # chatterbox pins torch==2.6.0 and pip resolves that to the CUDA build by default.
  # Neither fleet host has an NVIDIA GPU, so that is ~2.7 GB of dead weight — force CPU.
  echo "  forcing CPU-only torch (no GPU on this fleet) …"
  "$VENV/bin/pip" install --quiet --force-reinstall \
      torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cpu
  "$VENV/bin/pip" uninstall -y -q $("$VENV/bin/pip" list 2>/dev/null | awk '/^nvidia-|^triton/{print $1}') 2>/dev/null || true
  say "chatterbox" "installed"
fi

# ---------- sprite sets ----------
if [ -d "$ROOT/assets/mouths" ]; then
  n=$(find "$ROOT/assets/mouths" -mindepth 1 -maxdepth 1 -type d | wc -l)
  say "mouth sprite sets" "$n found under assets/mouths/"
else
  say "mouth sprite sets" "none — see docs/render-pipeline.md (portrender mascot-sheet)"
fi

echo
echo "smoke test:"
echo "  python3 -m clemtock avatar --text \"howdy\" --sprites assets/mouths/_placeholder --out out/test.mp4"
