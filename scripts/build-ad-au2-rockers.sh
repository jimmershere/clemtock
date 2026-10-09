#!/usr/bin/env bash
# build-ad-au2-rockers.sh — "Rockers" : the spring rust spot for Appearance Unlimited.
#
# Fourth worked example, and the first one built the way a real feed ad is built:
#   * ONE continuous VO take, with the VIDEO cutting underneath it (not a chain of
#     separately-rendered talking-head segments, which never match in energy)
#   * real shop photography as B-roll — AU2's own site assets, including a pickup with
#     the exact rot this script describes
#   * BURNED-IN CAPTIONS, because feed video autoplays muted
#
#   bash scripts/build-ad-au2-rockers.sh                # assemble from the existing VO
#   bash scripts/build-ad-au2-rockers.sh --render       # re-render the VO — COSTS ~$1.50
#   CAPTIONS=0 bash scripts/build-ad-au2-rockers.sh     # no burned-in captions
#
# ON LENGTH. The approved script is 102 spoken words and there is ZERO internal silence
# to tighten (silencedetect finds no gap over 0.10s at -20dB). So the runtime is set
# entirely by the VOICE's speaking rate, and the two differ far more than expected:
#
#   stock "Mysterious Michael"   39.82s   0.3904 s/word
#   Michael's clone              32.30s   0.3167 s/word   -- 19% faster
#
# Switching to the clone took the spot from 39.7s to 32.2s without touching a word.
# Reaching 30.0s now needs ~8 words out, not ~26. Still the client's call, not a flag.
# Everything downstream is word-proportional against the measured VO, so a voice change
# re-times the shots, the captions and the end card on its own.
# See the user-facing notes for the specific proposed trim.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${WORK:-$ROOT/out/ads/au2-rockers}"
OUT="${OUT:-$ROOT/out/ads/au2-rockers.mp4}"
VO="${VO:-$WORK/michael-vo.mp4}"
PHOTOS="${PHOTOS:-/app/appearance-unlimited-site/assets/img/photos}"
W=1080 H=1920 FPS=30
LUFS="${LUFS:--14}"
CAPTIONS="${CAPTIONS:-1}"
XF=0.30                                   # dissolve between shots

# AU2 brand — same values the previous two AU2 spots use.
RED='#b8121b'; RED_D='#7d0d13'; CHROME='#f4f4f6'; INK='#0c0c0d'; GREY='#b9bcc2'
FONT="${FONT:-/usr/share/fonts/truetype/liberation/LiberationSansNarrow-BoldItalic.ttf}"
FONT_CAP="${FONT_CAP:-LiberationSansNarrow-Bold}"   # family name, for libass

RENDER=0; for a in "$@"; do [ "$a" = "--render" ] && RENDER=1; done
mkdir -p "$WORK" "$(dirname "$OUT")"
say() { printf '\n== %s\n' "$1"; }
dur() { ffprobe -v error -show_entries format=duration -of csv=p=0 "$1"; }

SCRIPT_TEXT="Every spring I see the same thing. Salt, slush, and a rocker panel that looks fine... until you poke it. Rockers aren't just trim. They're what keeps the body from folding in the middle. Once they rot from the inside, Bondo won't save them. At Appearance Unlimited we cut out the bad metal, weld in new rockers, and finish it so you can't tell where the repair starts. Thirty years in Traverse City. Collision, paint, classics, and the truck you swore you'd fix this year. Stop driving a beater. Let's turn it back into a beauty. Appearance Unlimited. Link's in the bio."

# ---------------------------------------------------------------- 0. the voice --
# No --voice-id here on purpose: --brand resolves it from brands/michael/voice.json, so
# the character's voice is defined in one place instead of in every ad script. That gap
# is why a placeholder STOCK voice survived three finished ads.
if [ "$RENDER" = 1 ]; then
  say "rendering the VO (bills ~\$1.50)"
  ( cd "$ROOT/backend"
    python3 -m clemtock avatar --provider heygen --brand michael \
      --text "$SCRIPT_TEXT" --out "$VO" )
fi
[ -f "$VO" ] || { echo "no VO at $VO — run with --render" >&2; exit 1; }
D=$(dur "$VO")
printf '   VO %.2fs\n' "$D"

# ------------------------------------------------------------------- 1. shots --
# Cut points are word-proportional against the measured VO rather than guessed in
# seconds, so the edit still lines up if the read ever comes back a little different.
# Michael holds the open and the close (where sync matters most); B-roll carries the
# middle, where a cut landing a quarter-second early is invisible.
say "1/3  building shots"
shot_still() {   # <file> <start> <end> <zoom-from> <zoom-to> <out> [fill]
  # +XF is the transition HANDLE. Every xfade consumes XF from the running total, so a
  # chain of 10 shots cut to their nominal lengths comes out 9*XF short and -shortest
  # then truncates the tail off the VO. Each shot pays for its own outgoing dissolve.
  local src="$1" t0="$2" t1="$3" z0="$4" z1="$5" out="$6" fill="${7:-1.36}"
  local len; len=$(awk "BEGIN{printf \"%.3f\", $t1-$t0+$XF}")
  local frames; frames=$(awk "BEGIN{printf \"%d\", ($len)*$FPS}")
  local fw; fw=$(awk "BEGIN{printf \"%d\", int(${W}*${fill}/2)*2}")
  # Landscape shop photos into a 9:16 frame. Cropping to FILL the frame would throw away
  # the part that proves the point (a rotted rocker seam runs horizontally), but fitting
  # to the frame width leaves the picture as a thin band in a sea of blur. So: scale past
  # the frame width by `fill` and crop the sides back — more picture, less blur, subject
  # intact. Raise fill for centred subjects, lower it for wide ones.
  ffmpeg -v error -y -loop 1 -t "$len" -i "$src" \
    -filter_complex "[0:v]split=2[bg][fg]; \
       [bg]scale=${W}:${H}:force_original_aspect_ratio=increase,crop=${W}:${H}, \
          gblur=sigma=40,eq=brightness=-0.18[bgb]; \
       [fg]scale=${fw}:-2,crop=${W}:ih:(iw-${W})/2:0[fgs]; \
       [bgb][fgs]overlay=(W-w)/2:(H-h)/2,fps=${FPS}, \
       zoompan=z='${z0}+(${z1}-${z0})*on/${frames}':d=1:s=${W}x${H}:fps=${FPS}, \
       format=yuv420p[v]" -map "[v]" -an -c:v libx264 -preset medium -crf 20 "$out"
}
shot_vo() {      # <start> <end> <out>  — Michael, cut from the single take
  local t0="$1" t1="$2" out="$3"
  local len; len=$(awk "BEGIN{printf \"%.3f\", $t1-$t0+$XF}")
  ffmpeg -v error -y -ss "$t0" -t "$len" -i "$VO" \
    -vf "scale=${W}:${H}:force_original_aspect_ratio=increase,crop=${W}:${H},fps=${FPS},format=yuv420p" \
    -an -c:v libx264 -preset medium -crf 20 "$out"
}
pct() { awk "BEGIN{printf \"%.3f\", $D*$1}"; }

# Word-proportional boundaries: A 0-.196, B -.431, C -.833, D -1.0
T1=$(pct 0.150)   # hook on Michael
T2=$(pct 0.245)   # "...until you poke it"  -> the rot
T3=$(pct 0.340)   # tech into the seam
T4=$(pct 0.431)   # back to Michael: why it matters
T5=$(pct 0.540)   # "cut out the bad metal"
T6=$(pct 0.640)   # "weld in new rockers"
T7=$(pct 0.730)   # "finish it"
T8=$(pct 0.833)   # the finished truck
T9=$(pct 0.930)   # Michael: "stop driving a beater"

shot_vo    0     "$T1" "$WORK/s01.mp4"
shot_still "$PHOTOS/rocker-and-structural-repair-2048w.jpg"  "$T1" "$T2" 1.00 1.10 "$WORK/s02.mp4"
shot_still "$PHOTOS/structural-repair-on-the-lift-2048w.jpg" "$T2" "$T3" 1.10 1.00 "$WORK/s03.mp4"
shot_vo    "$T3" "$T4" "$WORK/s04.mp4"
# "cut out the bad metal" — a stripped quarter panel reads as metalwork; the
# collision-damage close-up that was here was too abstract to land the line.
shot_still "$PHOTOS/collision-panel-work-body-bay-2048w.jpg" "$T4" "$T5" 1.00 1.09 "$WORK/s05.mp4" 1.30
shot_still "$PHOTOS/technicians-on-the-shop-floor-2048w.jpg" "$T5" "$T6" 1.08 1.00 "$WORK/s06.mp4"
shot_still "$PHOTOS/fresh-finish-in-the-booth-2048w.jpg"     "$T6" "$T7" 1.00 1.08 "$WORK/s07.mp4"
shot_still "$PHOTOS/dodge-d150-restoration-after-2048w.jpg"  "$T7" "$T8" 1.10 1.00 "$WORK/s08.mp4"
shot_vo    "$T8" "$T9" "$WORK/s09.mp4"

# ----------------------------------------------------------------- 2. end card --
say "2/3  end card"
convert -size ${W}x600 xc:none -font "$FONT" -pointsize 300 -gravity center \
        -fill "$CHROME" -annotate +0+0 'AU2' "$WORK/word.png"
convert "$WORK/word.png" -motion-blur 0x45+180 -fill "$RED" -colorize 60% "$WORK/trail.png"
convert -size ${W}x${H} "gradient:#1a1a1d-${INK}" \
  -fill "$RED"   -draw "polygon 0,840 ${W},740 ${W},1080 0,1180" \
  -fill "$RED_D" -draw "polygon 0,900 ${W},810 ${W},950 0,1040" \
  -gravity north \( "$WORK/trail.png" -geometry +0+620 \) -compose over -composite \
  -gravity north \( "$WORK/word.png"  -geometry +0+620 \) -compose over -composite \
  -stroke none -font "$FONT" -pointsize 52 -gravity north -fill "$CHROME" \
  -annotate +0+1230 'APPEARANCE UNLIMITED' \
  -font "$FONT" -pointsize 36 -fill "$GREY" -annotate +0+1310 'TRAVERSE CITY, MICHIGAN' \
  "$WORK/end.png"
ELEN=$(awk "BEGIN{printf \"%.3f\", $D-$T9}")   # last shot — no outgoing xfade, no handle
ffmpeg -v error -y -loop 1 -t "$ELEN" -i "$WORK/end.png" \
  -filter_complex "[0:v]scale=${W}:${H},fps=${FPS},zoompan=z='1.00+0.04*on/($(awk "BEGIN{printf \"%d\", $ELEN*$FPS}"))':d=1:s=${W}x${H}:fps=${FPS},format=yuv420p[v]" \
  -map "[v]" -an -c:v libx264 -preset medium -crf 20 "$WORK/s10.mp4"

# ------------------------------------------------------------------ 3. assemble --
say "3/3  assemble"
# Video first, as a dissolve chain; the VO is laid under the finished picture in one
# piece, so nothing can drift out of sync.
IN=(); for i in 01 02 03 04 05 06 07 08 09 10; do IN+=(-i "$WORK/s$i.mp4"); done
FC=""; PREV="[0:v]"; ACC=$(dur "$WORK/s01.mp4")
for i in $(seq 1 9); do
  n=$(printf '%02d' $((i+1)))
  off=$(awk "BEGIN{printf \"%.3f\", $ACC-$XF}")
  FC+="${PREV}[${i}:v]xfade=transition=fade:duration=${XF}:offset=${off}[v${i}];"
  PREV="[v${i}]"
  ACC=$(awk "BEGIN{printf \"%.3f\", $ACC+$(dur "$WORK/s$n.mp4")-$XF}")
done
TOTAL="$ACC"
FADE=$(awk "BEGIN{printf \"%.3f\", $TOTAL-0.6}")
FC+="${PREV}fade=t=out:st=${FADE}:d=0.6[vout]"

ffmpeg -v error -y "${IN[@]}" -filter_complex "$FC" -map "[vout]" \
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -an "$WORK/picture.mp4"

# Captions, burned in: feed video autoplays muted, so an un-captioned talking head is
# a silent stranger. Chunk timings are word-proportional against the same measured VO.
SUBS=()
if [ "$CAPTIONS" = 1 ]; then
  python3 "$ROOT/scripts/make-captions.py" --duration "$D" --out "$WORK/captions.ass" \
          --font "$FONT_CAP" --width "$W" --height "$H"
  SUBS=(-vf "subtitles=$WORK/captions.ass")
fi

ffmpeg -v error -y -i "$WORK/picture.mp4" -i "$VO" "${SUBS[@]}" \
  -map 0:v -map 1:a -af "loudnorm=I=${LUFS}:TP=-1.5:LRA=11,afade=t=out:st=${FADE}:d=0.6" \
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
  -c:a aac -b:a 128k -ar 48000 -ac 2 -shortest "$OUT"

printf '\nwrote %s  (%.2fs)\n' "$OUT" "$(dur "$OUT")"
