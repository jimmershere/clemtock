# clemtock

Makes short vertical videos: **talking cartoon characters** and **social ads**.

New here? Read [`/app/START-HERE.md`](../START-HERE.md) first — it covers all four tools
and tells you which one you want.

---

## The 60-second version

```bash
cd /app/clemtock/backend
python3 -m clemtock avatar --brand earl_biggers --text "Well howdy. Gone fishin, dammit." --out ../out/earl.mp4
```

That makes a 1080×1920 video of a cartoon character speaking that line. **It costs
nothing**, needs no API key, and works with the internet unplugged.

It is slow — about 8–15× the length of the audio, so a 10-second line takes 1–3 minutes.
That is expected, not a hang.

---

## What it can do

| | Command | Cost | Needs |
|---|---|---|---|
| Talking cartoon character | `avatar --brand <slug>` | **free** | nothing (all local) |
| Talking photoreal human | `avatar --provider heygen` | ~$0.50+/video | HeyGen key |
| Write an ad script | `script --prompt "…"` | **free** | nothing (local model) |
| Check what's working | `probe` | free | nothing |
| Render an ad to MP4 | `export --script …` | free | node + chromium |

---

## Talking cartoon characters

### How it works

Three free tools in a row. Nothing here needs a graphics card:

```
your text ─► Chatterbox ─► speech.wav ─► Rhubarb ─► which mouth, when ─► ffmpeg ─► video
              (voice)                    (lip sync)                      (assembly)
```

A cartoon mouth is just a handful of drawings. Lip-sync means picking which drawing is on
screen at each moment — a solved problem, instant on a CPU. That is why this is free while
services like HeyGen charge per video.

### Setting up a character

Each brand needs its mouth drawings in `/app/portrender/brands/<brand>/mouths/`:

| File | Mouth shape | Used for |
|---|---|---|
| `A.png` | closed | M, B, P |
| `B.png` | barely open | most consonants |
| `C.png` | open | E |
| `D.png` | wide open | "aa", AI |
| `E.png` | small round | O |
| `F.png` | puckered | U, W |
| `G.png` *(optional)* | teeth on lip | F, V |
| `H.png` *(optional)* | tongue up | L |
| `X.png` *(optional)* | resting | silence |

**Six files (A–F) is enough.** Missing shapes fall back to the nearest one automatically.

To get a working placeholder set in one command:

```bash
python3 /app/clemtock/scripts/make-sprite-set.py --out /app/portrender/brands/<brand>/mouths
```

That draws a bearded smiley so you can watch the pipeline work. Then replace the files one
at a time with real art — same names, any size. Nothing else needs changing.

Real art comes from portrender's `mascot-sheet` template. Keep every mouth identical
except the mouth itself, or the character will appear to twitch.

> Mouth art lives in portrender's brand folder because it belongs with the prompts that
> drew it. Those folders are **gitignored** — brand art is private, and portrender's repo
> is public.

### Cloning a voice

```bash
python3 -m clemtock avatar --brand earl_biggers --text "..." --voice-ref path/to/sample.wav
```

Five seconds of clean speech is enough. **Only clone a voice with that person's explicit
permission**, and keep the permission on file next to the sample — a WAV does not carry
consent with it.

### Useful options

```
--background FILE   a backdrop image behind the character
--bg-color '#123'   fill colour when there is no backdrop
--width / --height  default 1080×1920 (vertical). Use 1920 1080 for landscape.
--fps               default 30
--keep-workdir      keep the generated speech.wav and the mouth timings, to inspect
--sprites DIR       use a specific folder instead of --brand
```

---

## Writing ad scripts

```bash
python3 -m clemtock script --prompt "15 second vertical ad for a fishing tee" \
  --duration 15 --out ../out/ad-script.json
```

Produces a structured scene list (timings, on-screen copy, colours, which images go where).

By default this runs a language model **on this laptop** — free, private, offline. It is
noticeably weaker at copywriting than Claude. For anything you will actually publish, have
Claude write the script; use the local one for bulk and unattended runs.

```bash
CLEMTOCK_SCRIPT_PROVIDER=ollama     python3 -m clemtock script ...   # force local
CLEMTOCK_SCRIPT_PROVIDER=openrouter python3 -m clemtock script ...   # force the paid API
```

---

## Setup

Most of this is already installed. To do it on a fresh machine:

```bash
bash scripts/setup-avatar-chain.sh --check   # what is missing
bash scripts/setup-avatar-chain.sh           # install it (~3 GB, mostly one-time)
```

Then confirm:

```bash
bash scripts/probe-providers.sh
```

`OK` is good. `SKIP` means that key is absent and that one feature is unavailable —
everything else still works.

### Keys

Read automatically, in order, from `/app/portrender/.env` → `./.env` →
`/app/tee-empire/.env`. Never written back. One key on the machine serves every tool.

| Key | Unlocks | Needed for cartoons? |
|---|---|---|
| `OPENAI_API_KEY` | AI still images | no |
| `OPENROUTER_API_KEY` | cloud ad-script writer | no — local model covers it |
| `HEYGEN_API_KEY` | photoreal presenters | no |
| `KIEAI_API_KEY` | AI video clips | no |
| `POST_BRIDGE_API_KEY` | posting to social | no |
| `VAST_API_KEY` | rented GPU for b-roll | no |

**The whole cartoon avatar pipeline needs none of them.**

---

## Running the studio UI

```bash
bash scripts/serve.sh start      # http://127.0.0.1:3053
bash scripts/serve.sh status     # is it up?
bash scripts/serve.sh stop
```

---

## Layout

```
backend/clemtock/providers/   one file per external service; all swappable
  cartoon_avatar.py           the free talking-character pipeline
  chatterbox_voice.py         text -> speech (+ voice cloning)
  rhubarb_lipsync.py          speech -> mouth timings
  heygen.py                   paid photoreal presenter
  ollama_script.py            local ad-script writer
  vast_gpu.py                 rents a GPU by the hour, gives it back
assets/                       character art and backdrops
themes/                       per-brand look for ads
scripts/                      setup, health checks, start/stop
tests/                        run: python3 -m unittest discover -s tests -t .
vendor/                       downloaded tools (not in git)
```

## More detail

- [`docs/render-pipeline.md`](docs/render-pipeline.md) — architecture, real measured speeds
  and costs, and the staged plan for reselling this as an API
- [`DESIGN.md`](DESIGN.md) — original design notes
- [`/app/START-HERE.md`](../START-HERE.md) — all four tools in one page
