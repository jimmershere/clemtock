#!/usr/bin/env bash
# build-ad-portwright.sh — the 12-second portwright.io corporate spot.
#
# Third worked example. Unlike the two AU2 spots this one is brand-exact: the palette,
# the wordmark lockup and the corner-bracket motif are all sampled from the live site
# (https://portwright.io, read 2026-10-07) rather than invented, because /app/CLAUDE.md
# P-1 says not to invent a Portwright definition.
#
#   bash scripts/build-ad-portwright.sh                 # assemble from the existing VO
#   bash scripts/build-ad-portwright.sh --render        # re-render the VO — COSTS MONEY
#   CALLOUT=0 bash scripts/build-ad-portwright.sh       # drop the on-screen stat callout
#
# Segments (12.00s exactly):
#   1  PORTWRIGHT wordmark card   1.30s   wipe-in, amber brackets            free
#   2  Jimmer, the whole script   9.02s   HeyGen talking photo + cloned voice ~$0.35
#   3  portwright.io end card     2.38s   then a slow fade                   free
#   joined with two 0.35s cross-dissolves
#
# The VO is one continuous take, so the arithmetic is fixed: 12s total minus a 9.02s
# read leaves 3.68s of card time once the two dissolves are paid for. Lengthening a
# card means shortening the other one, not the ad.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORTRENDER="${PORTRENDER_DIR:-/app/portrender}"
WORK="${WORK:-$ROOT/out/ads/portwright}"
OUT="${OUT:-$ROOT/out/ads/portwright-12s.mp4}"
VO="${VO:-$WORK/jimmer-vo.mp4}"
W=1080 H=1920 FPS=30 T=0.35
LUFS="${LUFS:--14}"
CALLOUT="${CALLOUT:-1}"
TOTAL_TARGET="${TOTAL_TARGET:-12.00}"
D1="${D1:-1.30}"                       # title card; end card is computed from it

# Brand, sampled from the live site — do not "tidy" these values.
INK='#0c1218'      # page background
PANEL='#141c26'    # section panel
AMBER='#e4a04a'    # CTA / the WRIGHT half of the wordmark
CREAM='#efe8dc'    # headline text
MUTED='#8a98a8'    # body text

FONT_H="${FONT_H:-/usr/share/fonts/opentype/fira/FiraSansCondensed-Heavy.otf}"
FONT_B="${FONT_B:-/usr/share/fonts/opentype/fira/FiraSansCondensed-Bold.otf}"
FONT_M="${FONT_M:-/usr/share/fonts/opentype/fira/FiraSansCondensed-Medium.otf}"

RENDER=0; for a in "$@"; do [ "$a" = "--render" ] && RENDER=1; done
mkdir -p "$WORK" "$(dirname "$OUT")"
say() { printf '\n== %s\n' "$1"; }
dur() { ffprobe -v error -show_entries format=duration -of csv=p=0 "$1"; }

SCRIPT_TEXT="From 13 million healthcare records to your entire digital storefront—we build the hard stuff, and we make it fast. Portwright.io. Built, Not Bought."

# ---------------------------------------------------------------- 0. the voice --
# clemtock owns the HeyGen key; portrender would delegate here anyway. The domain is
# passed as a real domain — speech.py rewrites it to "Portwright dot I O", which
# measured 0 internal pauses. Never hand TTS a bare URL.
if [ "$RENDER" = 1 ]; then
  say "rendering the VO (this bills ~\$0.35)"
  ( cd "$ROOT/backend"
    python3 -m clemtock avatar --provider heygen --brand portwright \
      --voice-id 2f919cd0f3a0485fbd68f4245ca4ea11 \
      --text "$SCRIPT_TEXT" --out "$VO" )
fi
[ -f "$VO" ] || { echo "no VO at $VO — run with --render" >&2; exit 1; }

D2=$(dur "$VO")
D3=$(awk "BEGIN{printf \"%.6f\", $TOTAL_TARGET - $D2 - $D1 + 2*$T}")
awk -v d="$D3" 'BEGIN{ if (d < 0.8) { print "end card would be " d "s — VO too long for a " ENVIRON["TOTAL_TARGET"] "s cut"; exit 1 } }'
printf '   VO %.2fs  ->  title %.2fs + end card %.2fs  (target %s)\n' "$D2" "$D1" "$D3" "$TOTAL_TARGET"

# ------------------------------------------------------------- 1. title card --
say "1/3  PORTWRIGHT wordmark"
# Two-tone lockup: PORT in cream, WRIGHT in amber, exactly as the site sets it.
# Render the halves separately and +append them. Placing both with -annotate offsets on
# one centred canvas is what produced "POWRIGHT" — the two strings overlapped, because
# the offset is from the centre of the CANVAS, not the end of the previous word.
convert -background none -fill "$CREAM" -font "$FONT_H" -pointsize 150 \
        -kerning 6 label:'PORT'   "$WORK/wm-a.png"
convert -background none -fill "$AMBER" -font "$FONT_H" -pointsize 150 \
        -kerning 6 label:'WRIGHT' "$WORK/wm-b.png"
convert "$WORK/wm-a.png" "$WORK/wm-b.png" +append -trim +repage \
        -bordercolor none -border 20x20 "$WORK/wordmark.png"
# The site frames its hero in thin amber L-brackets; reuse them so the card and the
# site read as one system.
convert -size ${W}x${H} "xc:$INK" \
  -fill none -stroke "$AMBER" -strokewidth 5 \
  -draw "path 'M 120,700 L 120,640 L 180,640'" \
  -draw "path 'M 960,1220 L 960,1280 L 900,1280'" \
  -gravity north \( "$WORK/wordmark.png" -geometry +0+760 \) -compose over -composite \
  -stroke none -font "$FONT_M" -pointsize 40 -gravity north -fill "$MUTED" \
  -annotate +0+1090 'WE BUILD SOFTWARE THAT HOLDS THE LINE' \
  "$WORK/title.png"
# Wipe in from the left: pad puts the art in the RIGHT half so the crop window
# travels 0 -> W to reveal it. Running that expression the other way slides the card
# OUT to black — the bug the first AU2 cut shipped with.
ffmpeg -v error -y -loop 1 -t "$D1" -i "$WORK/title.png" \
  -f lavfi -t "$D1" -i anullsrc=channel_layout=stereo:sample_rate=48000 \
  -filter_complex "[0:v]scale=${W}:${H},format=yuv420p,pad=iw*2:ih:iw:0:color=${INK}, \
     crop=${W}:${H}:'${W}*min(1\,t/0.40)':0,fps=${FPS}[v]" \
  -map "[v]" -map 1:a -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 128k \
  -ar 48000 -ac 2 -shortest "$WORK/01-title.mp4"

# ------------------------------------------------------------------ 2. Jimmer --
say "2/3  Jimmer"
# HeyGen frames the talking photo itself and holds that framing for the whole take,
# so nine seconds sit on one shot. A slow push-out keeps it breathing without ever
# looking like a camera move. Loudness is normalised here, not trusted: sources never
# agree, and a 10 dB step mid-ad reads as the second half being broken.
CALLOUT_VF=""
if [ "$CALLOUT" = 1 ]; then
  # One restrained stat, timed to the clause that says it. It sits over his shoulder and
  # the sunset behind it, so amber-on-nothing washes out — it needs its own ink plate to
  # stay legible rather than a bigger point size.
  CALLOUT_VF=",drawtext=fontfile=${FONT_B}:text='13 MILLION HEALTHCARE RECORDS':\
fontcolor=${AMBER}:fontsize=52:x=(w-text_w)/2:y=h-330:\
box=1:boxcolor=0x0c1218@0.82:boxborderw=24:\
alpha='if(lt(t,0.6),0,if(lt(t,1.0),(t-0.6)/0.4,if(lt(t,3.6),1,if(lt(t,4.0),(4.0-t)/0.4,0))))'"
fi
# fps=30 BEFORE zoompan, not inside it. HeyGen delivers 25 fps; zoompan with d=1 emits
# exactly one output frame per INPUT frame, and its own fps= only labels the timebase —
# it does not resample. Without this the 9.02s take became 225 frames stamped at 30 fps,
# i.e. a 7.5s video against 9.02s of audio, and the assemble silently truncated the ad.
ffmpeg -v error -y -i "$VO" \
  -filter_complex "[0:v]scale=${W}:${H}:force_original_aspect_ratio=increase, \
     crop=${W}:${H},fps=${FPS}, \
     zoompan=z='max(1.06-0.06*on/(${FPS}*${D2}),1.0)':d=1:s=${W}x${H}:fps=${FPS}, \
     format=yuv420p${CALLOUT_VF}[v]" \
  -af "loudnorm=I=${LUFS}:TP=-1.5:LRA=11" \
  -map "[v]" -map 0:a -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 128k \
  -ar 48000 -ac 2 "$WORK/02-jimmer.mp4"

# ---------------------------------------------------------------- 3. end card --
say "3/3  portwright.io"
convert -size ${W}x${H} "xc:$INK" \
  -fill "$PANEL" -draw "rectangle 0,840 ${W},1180" \
  -fill none -stroke "$AMBER" -strokewidth 5 \
  -draw "path 'M 120,800 L 120,740 L 180,740'" \
  -draw "path 'M 960,1220 L 960,1280 L 900,1280'" \
  -stroke none -font "$FONT_H" -pointsize 104 -gravity north -fill "$CREAM" \
  -annotate +0+900 'portwright.io' \
  -font "$FONT_H" -pointsize 62 -fill "$AMBER" -annotate +0+1045 'BUILT, NOT BOUGHT.' \
  "$WORK/end.png"
ffmpeg -v error -y -loop 1 -t "$D3" -i "$WORK/end.png" \
  -f lavfi -t "$D3" -i anullsrc=channel_layout=stereo:sample_rate=48000 \
  -filter_complex "[0:v]scale=${W}:${H},fps=${FPS},format=yuv420p[v]" \
  -map "[v]" -map 1:a -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 128k \
  -ar 48000 -ac 2 -shortest "$WORK/03-end.mp4"

# ----------------------------------------------------------------- assemble --
say "assembling"
A1=$(dur "$WORK/01-title.mp4"); A2=$(dur "$WORK/02-jimmer.mp4"); A3=$(dur "$WORK/03-end.mp4")
# awk, not bc: bc prints ".95" with no leading zero and ffmpeg refuses that as a duration.
calc() { awk "BEGIN{printf \"%.6f\", $1}"; }
ms()   { awk "BEGIN{printf \"%d\", ($1)*1000}"; }
O1=$(calc "$A1 - $T")
L2=$(calc "$A1 + $A2 - $T"); O2=$(calc "$L2 - $T")
# Segment lengths round up to frame boundaries, so the chain lands a few frames long.
# Fade against the TARGET and hard-trim to it: the trim removes only the tail of a
# fade that is already at black, so the cut is invisible and the spot is exactly 12.00s.
TOTAL="$TOTAL_TARGET"
FADE=$(calc "$TOTAL_TARGET - 0.7")
# Audio rides along by delaying each segment to its own start and mixing — one timeline
# to keep in sync instead of a second crossfade chain.
M2=$(ms "$O1"); M3=$(ms "$O2")

ffmpeg -v error -y \
  -i "$WORK/01-title.mp4" -i "$WORK/02-jimmer.mp4" -i "$WORK/03-end.mp4" \
  -filter_complex "
   [0:v][1:v]xfade=transition=fade:duration=${T}:offset=${O1}[v1];
   [v1][2:v]xfade=transition=fade:duration=${T}:offset=${O2}[v2];
   [v2]fade=t=out:st=${FADE}:d=0.7[v];
   [0:a]adelay=0|0[a0];
   [1:a]adelay=${M2}|${M2}[a1];
   [2:a]adelay=${M3}|${M3}[a2];
   [a0][a1][a2]amix=inputs=3:normalize=0,
     afade=t=out:st=${FADE}:d=0.7,alimiter=limit=0.95[a]" \
  -map "[v]" -map "[a]" -t "$TOTAL_TARGET" \
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
  -c:a aac -b:a 128k "$OUT"

printf '\nwrote %s  (%.2fs)\n' "$OUT" "$(dur "$OUT")"
