#!/usr/bin/env python3
"""Burned-in captions for a feed ad, timed from the script rather than from audio.

Feed video autoplays muted, so an uncaptioned talking head is a silent stranger. This
writes an ASS file sized for a 1080x1920 frame.

**Why word-proportional and not a transcription.** We already know exactly what was
said — we wrote it — so the only unknown is *when*. HeyGen's read has no internal
pauses at all (silencedetect finds no gap over 0.10s at -20dB on the rockers VO,
2026-10-09), which means delivery is near-uniform and words-per-chunk is a good
predictor of elapsed time. A speech-recogniser would add a dependency and a second
failure mode to recover timings we can estimate to within a frame or two.

The limitation is honest: on a read WITH dramatic pauses this drifts, and the fix then
is real forced alignment, not a fudge factor here.

    python3 make-captions.py --duration 39.816 --out captions.ass
"""
from __future__ import annotations

import argparse
from pathlib import Path

# Chunked for reading, not for grammar: 2-9 words, breaking where a speaker breathes.
# Keep these in the same order as the spoken script and the arithmetic takes care of
# itself — the chunk's share of the words is its share of the running time.
CHUNKS = [
    "Every spring I see the same thing.",
    "Salt, slush, and a rocker panel",
    "that looks fine... until you poke it.",
    "Rockers aren't just trim.",
    "They're what keeps the body",
    "from folding in the middle.",
    "Once they rot from the inside,",
    "Bondo won't save them.",
    "At Appearance Unlimited we cut out the bad metal,",
    "weld in new rockers,",
    "and finish it so you can't tell",
    "where the repair starts.",
    "Thirty years in Traverse City.",
    "Collision, paint, classics,",
    "and the truck you swore you'd fix this year.",
    "Stop driving a beater.",
    "Let's turn it back into a beauty.",
    "Appearance Unlimited.",
    "Link's in the bio.",
]


def ts(t: float) -> str:
    """ASS timestamp: h:mm:ss.cc (centiseconds, and exactly two digits)."""
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build(duration: float, font: str, width: int, height: int) -> str:
    counts = [len(c.split()) for c in CHUNKS]
    total = sum(counts)
    per_word = duration / total

    # Bottom third, above where platform UI (captions, handles, buttons) sits. White on
    # a heavy outline rather than a box: it stays legible over both the dark shop photos
    # and the bright paint-booth ones without a slab covering the picture.
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Feed,{font},76,&H00FFFFFF,&H00141414,&H96000000,-1,0,1,6,3,2,90,90,330,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines, t = [], 0.0
    for chunk, n in zip(CHUNKS, counts):
        end = t + n * per_word
        # Trim a hair so consecutive chunks never collide on the same frame.
        lines.append(f"Dialogue: 0,{ts(t)},{ts(end - 0.03)},Feed,,0,0,0,,{chunk}")
        t = end
    return head + "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--font", default="LiberationSansNarrow-Bold")
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    a = ap.parse_args()
    Path(a.out).write_text(build(a.duration, a.font, a.width, a.height), encoding="utf-8")
    print(f"captions: {len(CHUNKS)} chunks over {a.duration:.2f}s -> {a.out}")


if __name__ == "__main__":
    main()
