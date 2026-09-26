#!/usr/bin/env bash
# build-ad-au2-liar.sh — the "Ran When Parked" AU2 spot.
#
# Second worked example, and it adds three things build-ad-au2.sh did not need:
#   * real SWOOSH transitions between segments (xfade slideleft), not hard cuts
#   * a screen recording of somebody actually using the site (capture-site-demo.mjs)
#   * a sound effect
#
#   bash scripts/build-ad-au2-liar.sh
#   bash scripts/build-ad-au2-liar.sh --capture   # re-record the website walkthrough
#
# Segments:
#   1  AU2 title card          1.5s   (the previous spot's card, half a second longer)
#   2  burning-Mustang still   2.6s   fade in + a cranking engine that never catches
#   3  Jimmer, the line        ~6.1s  HeyGen, his cloned voice
#   4  site walkthrough        5.5s   real browser, real cursor, real form
#   5  URL card                1.0s   then a slow fade to black
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORTRENDER="${PORTRENDER_DIR:-/app/portrender}"
WORK="${WORK:-$ROOT/out/ads/au2-liar}"
OUT="${OUT:-$ROOT/out/ads/au2-liar.mp4}"
FONT="${FONT:-/usr/share/fonts/truetype/liberation/LiberationSansNarrow-BoldItalic.ttf}"
HERO="${HERO:-/home/jimmer/Pictures/Burning Rustbucket Mustang in Dumpster.png}"
W=1080 H=1920 FPS=30 T=0.35          # T = swoosh length
LUFS="${LUFS:--14}"
CAPTURE=0; for a in "$@"; do [ "$a" = "--capture" ] && CAPTURE=1; done
mkdir -p "$WORK" "$(dirname "$OUT")"
say() { printf '\n== %s\n' "$1"; }
dur() { ffprobe -v error -show_entries format=duration -of csv=p=0 "$1"; }

# ------------------------------------------------------------ 1. title card (1.5s) --
say "1/5  AU2 title card"
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
# Same slide as before, held half a second longer. pad puts the art in the RIGHT half,
# so the crop window travels 0 -> W to reveal it.
ffmpeg -v error -y -loop 1 -t 1.5 -i "$WORK/title.png" \
  -f lavfi -t 1.5 -i anullsrc=channel_layout=stereo:sample_rate=48000 \
  -filter_complex "[0:v]scale=${W}:${H},format=yuv420p,pad=iw*2:ih:iw:0:color=#0c0c0d, \
     crop=${W}:${H}:'${W}*min(1\,t/0.35)':0,fps=${FPS}[v]" \
  -map "[v]" -map 1:a -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 128k -ar 48000 -ac 2 \
  -shortest "$WORK/01-title.mp4"

# ------------------------------------------------- 2. the dumpster fire + crank (2.6s) --
say "2/5  burning Mustang + engine that will not catch"
# Synthesised: a starter motor turning over in bursts and never firing. Three cranks,
# tremolo for the rur-rur-rur, then it gives up. A licensed SFX would be better — this
# is deliberately cheap and replaceable.
ffmpeg -v error -y -filter_complex "
 aevalsrc='0.55*sin(2*PI*82*t)+0.30*sin(2*PI*164*t)+0.16*sin(2*PI*246*t)':s=48000:d=2.6[eng];
 anoisesrc=d=2.6:c=brown:r=48000:a=0.35[nz];
 [eng][nz]amix=inputs=2:weights='1 0.6'[m];
 [m]tremolo=f=9.5:d=0.92,highpass=f=55,lowpass=f=2200,
    volume='if(lt(t,0.05),0,if(lt(t,0.85),1,if(lt(t,1.05),0,if(lt(t,1.85),1,if(lt(t,2.05),0,0.9)))))':eval=frame,
    afade=t=out:st=2.25:d=0.35[a]" -map "[a]" -c:a pcm_s16le "$WORK/crank.wav"

# The hero is 1536x1024 LANDSCAPE against a 1080x1920 portrait frame. Cropping it to
# fill would throw away most of the car, which is the entire joke — so it is fitted to
# the width and set on a blurred blow-up of itself. Standard vertical-video treatment,
# and it reads as deliberate rather than as a letterbox.
ffmpeg -v error -y -loop 1 -t 2.6 -i "$HERO" -i "$WORK/crank.wav" \
  -filter_complex "[0:v]split=2[bg][fg]; \
     [bg]scale=${W}:${H}:force_original_aspect_ratio=increase,crop=${W}:${H}, \
        gblur=sigma=42,eq=brightness=-0.12[bgb]; \
     [fg]scale=${W}:-1[fgs]; \
     [bgb][fgs]overlay=(W-w)/2:(H-h)/2, \
     zoompan=z='min(zoom+0.0009,1.10)':d=$((FPS*3)):s=${W}x${H}:fps=${FPS}, \
     fade=t=in:st=0:d=0.6,format=yuv420p[v]" \
  -map "[v]" -map 1:a -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 128k -ar 48000 -ac 2 \
  -shortest "$WORK/02-hero.mp4"

# --------------------------------------------------------------- 3. Jimmer (~6.1s) --
say "3/5  Jimmer"
JIM="${JIM:-$(ls -1dt "$PORTRENDER"/data/renders/*au2-liar*/01.mp4 2>/dev/null | head -1)}"
[ -f "$JIM" ] || { echo "no Jimmer clip — render it first (see header)" >&2; exit 1; }
ffmpeg -v error -y -i "$JIM" \
  -vf "scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:color=#0c0c0d,fps=${FPS},format=yuv420p" \
  -af "loudnorm=I=${LUFS}:TP=-1.5:LRA=11" \
  -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 128k -ar 48000 -ac 2 "$WORK/03-jimmer.mp4"

# -------------------------------------------------------- 4. site walkthrough (5.5s) --
say "4/5  website walkthrough"
if [ "$CAPTURE" = 1 ] || [ ! -f "$WORK/site-demo.webm" ]; then
  node "$ROOT/scripts/capture-site-demo.mjs" --out "$WORK/site-demo.webm" \
       --url https://appearance-unlimited.com/
fi
# The capture runs ~11.7s; keep the part where things actually happen — the click
# through to the form, the card, and the typing.
ffmpeg -v error -y -ss 4.6 -t 5.5 -i "$WORK/site-demo.webm" \
  -f lavfi -t 5.5 -i anullsrc=channel_layout=stereo:sample_rate=48000 \
  -filter_complex "[0:v]scale=${W}:-1,crop=${W}:${H}:0:'max(0\,(ih-${H})/2)',fps=${FPS},format=yuv420p[v]" \
  -map "[v]" -map 1:a -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 128k -ar 48000 -ac 2 \
  -shortest "$WORK/04-site.mp4"

# ------------------------------------------------------------------ 5. URL card (1s) --
say "5/5  URL card"
convert -size ${W}x${H} gradient:'#1a1a1d-#0c0c0d' \
  -fill '#b8121b' -draw "polygon 0,930 ${W},850 ${W},1070 0,1150" \
  -font "$FONT" -pointsize 62 -gravity center -fill '#f4f4f6' \
  -annotate +0-10 'https://appearance-unlimited.com' \
  "$WORK/url.png"
ffmpeg -v error -y -loop 1 -t 1.0 -i "$WORK/url.png" \
  -f lavfi -t 1.0 -i anullsrc=channel_layout=stereo:sample_rate=48000 \
  -filter_complex "[0:v]scale=${W}:${H},fps=${FPS},format=yuv420p[v]" \
  -map "[v]" -map 1:a -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 128k -ar 48000 -ac 2 \
  -shortest "$WORK/05-url.mp4"

# ---------------------------------------------------------------------- assemble --
say "assembling with swoosh transitions"
D1=$(dur "$WORK/01-title.mp4"); D2=$(dur "$WORK/02-hero.mp4")
D3=$(dur "$WORK/03-jimmer.mp4"); D4=$(dur "$WORK/04-site.mp4"); D5=$(dur "$WORK/05-url.mp4")
# xfade offset = where the OUTGOING clip should start handing over. Each chained xfade
# shortens the running total by T, so offsets accumulate on the already-faded length.
O1=$(echo "$D1 - $T" | bc)
L2=$(echo "$D1 + $D2 - $T" | bc);            O2=$(echo "$L2 - $T" | bc)
L3=$(echo "$L2 + $D3 - $T" | bc);            O3=$(echo "$L3 - $T" | bc)
L4=$(echo "$L3 + $D4 - $T" | bc);            O4=$(echo "$L4 - $T" | bc)
TOTAL=$(echo "$L4 + $D5 - $T" | bc)
FADE=$(echo "$TOTAL - 0.9" | bc)
# Audio rides along by delaying each segment to its own start and mixing; that handles
# the overlaps without a second crossfade chain to keep in sync.
A2=$(echo "($O1)*1000/1" | bc); A3=$(echo "($O2)*1000/1" | bc)
A4=$(echo "($O3)*1000/1" | bc); A5=$(echo "($O4)*1000/1" | bc)

ffmpeg -v error -y \
  -i "$WORK/01-title.mp4" -i "$WORK/02-hero.mp4" -i "$WORK/03-jimmer.mp4" \
  -i "$WORK/04-site.mp4"  -i "$WORK/05-url.mp4" \
  -filter_complex "
   [0:v][1:v]xfade=transition=slideleft:duration=${T}:offset=${O1}[v1];
   [v1][2:v]xfade=transition=slideleft:duration=${T}:offset=${O2}[v2];
   [v2][3:v]xfade=transition=slideleft:duration=${T}:offset=${O3}[v3];
   [v3][4:v]xfade=transition=slideleft:duration=${T}:offset=${O4}[v4];
   [v4]fade=t=out:st=${FADE}:d=0.9[v];
   [0:a]adelay=0|0[a0];
   [1:a]adelay=${A2}|${A2}[a1];
   [2:a]adelay=${A3}|${A3}[a2];
   [3:a]adelay=${A4}|${A4}[a3];
   [4:a]adelay=${A5}|${A5}[a4];
   [a0][a1][a2][a3][a4]amix=inputs=5:normalize=0,
     afade=t=out:st=${FADE}:d=0.9,alimiter=limit=0.95[a]" \
  -map "[v]" -map "[a]" -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
  -c:a aac -b:a 128k "$OUT"

printf '\nwrote %s  (%.2fs)\n' "$OUT" "$(dur "$OUT")"
