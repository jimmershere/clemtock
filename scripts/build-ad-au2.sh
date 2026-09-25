#!/usr/bin/env bash
# build-ad-au2.sh — assemble a complete social ad from the command line, end to end.
#
# This is the worked example behind docs/render-pipeline.md. Every step is a command you
# can run yourself; nothing here is magic and nothing is hidden in a UI. The phase-2 web
# UI will drive exactly these steps, which is why they are written out plainly.
#
#   bash scripts/build-ad-au2.sh            # assemble from existing renders
#   bash scripts/build-ad-au2.sh --render   # also (re)render the spoken parts — COSTS MONEY
#
# Structure:
#   1. AU2 title card      1.0s   ImageMagick still + a fast slide-in            free
#   2. Michael, cash-app   4.7s   HeyGen lip-sync to a recorded WAV              ~$0.09
#      (with 1.4s of cinematic phone-tap cut in over the hands-only frames)      ~$7 once
#   3. Michael, the CTA    4.9s   HeyGen lip-sync from text                      ~$0.09
#   4. Website card        1.0s   headless chromium screenshot + slow push-in    free
#   5. Fade to black
#
# Total ~11.6s. Note the arithmetic: the two spoken lines alone are 9.6s, so a 4-5s cut
# means dropping one of them. See --short.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORTRENDER="${PORTRENDER_DIR:-/app/portrender}"
WORK="${WORK:-$ROOT/out/ads/au2}"
OUT="${OUT:-$ROOT/out/ads/au2-social.mp4}"
FONT="${FONT:-/usr/share/fonts/truetype/liberation/LiberationSansNarrow-BoldItalic.ttf}"
W=1080 H=1920 FPS=30
SHORT=0; RENDER=0
for a in "$@"; do case "$a" in --short) SHORT=1 ;; --render) RENDER=1 ;; esac; done
mkdir -p "$WORK" "$(dirname "$OUT")"

say() { printf '\n== %s\n' "$1"; }

# --------------------------------------------------------------- 0. the voices --
# Spoken segments come from portrender, which delegates to clemtock -> HeyGen.
# --engine heygen is the paid, professional path (~$0.019/s).
if [ "$RENDER" = 1 ]; then
  say "rendering spoken segments (this bills)"
  ( cd "$PORTRENDER"
    python3 -m portrender video -c michael --engine heygen --label au2-cta \
      -t "Head to appearance unlimited dot com. Start your next repair or restore project." )
  echo "NOTE: the cash-app line is audio-driven (a recorded WAV, not TTS) — see docs."
fi

# Newest matching renders. portrender keeps each job in data/renders/<id>/01.mp4.
CASHAPP="${CASHAPP:-$ROOT/out/jobs/avatar-demo/michael-cashapp-gesture.mp4}"
CTA="${CTA:-$(ls -1dt "$PORTRENDER"/data/renders/*au2-cta*/01.mp4 2>/dev/null | head -1)}"
[ -f "$CASHAPP" ] || { echo "missing cash-app clip: $CASHAPP" >&2; exit 1; }
[ -f "$CTA" ]     || { echo "missing CTA clip (run with --render)" >&2; exit 1; }

# ------------------------------------------------------------ 1. the title card --
say "1/4  AU2 title card"
# The word on transparent, so a blurred copy of it becomes speed trails behind it.
convert -size ${W}x600 xc:none -font "$FONT" -pointsize 430 -gravity center \
        -fill '#f4f4f6' -annotate +0+0 'AU2' "$WORK/word.png"
convert "$WORK/word.png" -motion-blur 0x55+180 -fill '#b8121b' -colorize 60% "$WORK/trail.png"
convert -size ${W}x${H} gradient:'#1a1a1d-#0c0c0d' \
  -fill '#b8121b' -draw "polygon 0,900 ${W},780 ${W},1140 0,1260" \
  -fill '#7d0d13' -draw "polygon 0,960 ${W},860 ${W},1000 0,1100" \
  \( "$WORK/trail.png" -geometry +0+660 \) -compose over -composite \
  \( "$WORK/word.png"  -geometry +0+660 \) -compose over -composite \
  -font "$FONT" -pointsize 54 -gravity north -fill '#b9bcc2' \
  -annotate +0+1300 'APPEARANCE UNLIMITED' \
  -font "$FONT" -pointsize 34 -fill '#7d8087' -annotate +0+1380 'TRAVERSE CITY, MICHIGAN' \
  "$WORK/title.png"

# Slide in hard from the right and settle by 0.35s — the "moving fast" part.
# pad=iw*2 puts the artwork in the RIGHT half, so the crop window travels 0 -> W to
# reveal it. Running that expression the other way slides the card OUT to black, which
# is exactly the bug the first cut shipped with. Silent
# audio is attached so every segment has both streams and concat stays happy.
ffmpeg -v error -y -loop 1 -t 1.0 -i "$WORK/title.png" \
  -f lavfi -t 1.0 -i anullsrc=channel_layout=stereo:sample_rate=48000 \
  -filter_complex "[0:v]scale=${W}:${H},format=yuv420p, \
     pad=iw*2:ih:iw:0:color=#0c0c0d, \
     crop=${W}:${H}:'${W}*min(1\,t/0.35)':0,fps=${FPS}[v]" \
  -map "[v]" -map 1:a -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 128k \
  -shortest "$WORK/01-title.mp4"

# ------------------------------------------------------- 2+3. the spoken pieces --
say "2/4  spoken segments"
# Force identical codec/params so concat never re-encodes badly, AND match loudness.
#
# Loudness matters more than it sounds. Measured on the first draft: the recorded WAV
# line sat at -11.9 LUFS and the HeyGen TTS line at -22.1 LUFS — a 10 dB drop halfway
# through the ad, which reads as the second half being broken. Sources will always
# differ (a phone recording, a TTS engine, a cloned voice), so every spoken segment is
# normalised to one target instead of trusting them to agree.
LUFS="${LUFS:--14}"     # punchy social target; platforms re-normalise near here anyway
norm() {
  ffmpeg -v error -y -i "$1" \
    -vf "scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:color=#0c0c0d,fps=${FPS},format=yuv420p" \
    -af "loudnorm=I=${LUFS}:TP=-1.5:LRA=11" \
    -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 128k -ar 48000 -ac 2 "$2"
}
norm "$CASHAPP" "$WORK/02-cashapp.mp4"
norm "$CTA"     "$WORK/03-cta.mp4"

# ----------------------------------------------------------- 4. the website card --
say "3/4  website screenshot"
CHROME="${CLEMTOCK_CHROMIUM:-$(command -v chromium || command -v google-chrome || true)}"
if [ -n "$CHROME" ] && [ ! -f "$WORK/site.png" ]; then
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-sandbox \
    --window-size=810,1440 --virtual-time-budget=9000 \
    --screenshot="$WORK/site.png" https://appearance-unlimited.com/ >/dev/null 2>&1 || true
fi
[ -f "$WORK/site.png" ] || { echo "no site screenshot — set CLEMTOCK_CHROMIUM" >&2; exit 1; }
# Slow push-in, so a static grab still feels alive.
ffmpeg -v error -y -loop 1 -t 1.0 -i "$WORK/site.png" \
  -f lavfi -t 1.0 -i anullsrc=channel_layout=stereo:sample_rate=48000 \
  -filter_complex "[0:v]scale=${W}:-1,crop=${W}:${H}:0:0, \
     zoompan=z='min(zoom+0.0015,1.08)':d=${FPS}:s=${W}x${H}:fps=${FPS},format=yuv420p[v]" \
  -map "[v]" -map 1:a -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 128k \
  -shortest "$WORK/04-site.mp4"

# ------------------------------------------------------------------- 5. assemble --
say "4/4  assemble + fade"
LIST="$WORK/concat.txt"; : > "$LIST"
printf "file '%s'\n" "$WORK/01-title.mp4" >> "$LIST"
printf "file '%s'\n" "$WORK/02-cashapp.mp4" >> "$LIST"
[ "$SHORT" = 1 ] || printf "file '%s'\n" "$WORK/03-cta.mp4" >> "$LIST"
printf "file '%s'\n" "$WORK/04-site.mp4" >> "$LIST"

TOTAL=$(awk '{print $2}' "$LIST" | tr -d "'" | while read -r f; do
          ffprobe -v error -show_entries format=duration -of csv=p=0 "$f"; done \
        | paste -sd+ - | bc)
FADE=$(echo "$TOTAL - 0.6" | bc)

ffmpeg -v error -y -f concat -safe 0 -i "$LIST" \
  -vf "fade=t=out:st=${FADE}:d=0.6" -af "afade=t=out:st=${FADE}:d=0.6" \
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -c:a aac -b:a 128k "$OUT"

printf '\nwrote %s  (%.2fs)\n' "$OUT" "$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT")"
echo "segments in $WORK/"
