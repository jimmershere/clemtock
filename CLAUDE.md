# CLAUDE.md — clemtock (`/app/clemtock`)

**Humans: read [`README.md`](README.md), or [`/app/START-HERE.md`](../START-HERE.md) if you
do not yet know which tool you want.** This file is the agent brief — hazards and rules,
not a usage guide. Fleet context: [`../CLAUDE.md`](../CLAUDE.md).

## What this is

Makes short vertical (1080×1920) videos: talking characters and assembled social ads.
It is the tool that **owns every video provider credential** on this fleet.

| Path | |
|---|---|
| Remote | `github.com/jimmershere/clemtock` — **public** |
| Lives on | pop-os (source of truth); mirrored to quasimodo by `portrender/local81/portrender-deploy.yml` |
| Entry point | `cd backend && python3 -m clemtock …` |
| Tests | `python3 -m unittest discover -s tests -t .` (26, no network) |
| Providers | `backend/clemtock/providers/` — one file per external service |

## ⚠️ Money hazards — read before touching a provider

**HeyGen cinematic renders cost $0.74/second. Talking-photo renders cost $0.019/second —
about 39× cheaper.** Talking-photo is the default for a reason; cinematic is a garnish,
not a default (confirmed by jimmer, 2026-09-26).

**Never probe `POST /v3/videos` to discover its schema.** A 400 is free, but the moment
the body becomes valid the call returns 200 and a real render is **queued and billed**.
Deleting the video afterwards does **not** refund it. Two such probes cost $14.60 on
2026-09-25. This is why `cinematic()` in
[`providers/heygen.py`](backend/clemtock/providers/heygen.py) is gated behind
`confirm=True` and why `check_budget()` exists. Do not remove either.

**HeyGen's avatar quota counts avatar GROUPS, not talking photos.** Deleting individual
photos returns 200 and frees nothing. `heygen_character.py` calls `delete_group()` before
re-upload for exactly this reason.

Gate conventions across the fleet, all opt-in and all dry/safe by default:
`local81 --apply`, tee-empire `--live`, clemtock cinematic `confirm=True`.

## Rules

1. **clemtock holds the keys; portrender does not.** portrender's LAN web UI has no auth,
   so it must never hold a HeyGen, OpenAI or social credential. It shells out to
   `python3 -m clemtock avatar …` instead. Keep provider code here, in one place, so a
   v3 migration or an engine swap happens once. See
   [`../portrender/portrender/video.py`](../portrender/portrender/video.py).
2. **Nothing publishes as a side effect.** Anything that leaves the machine — a post, an
   upload to a live account — is a gated action a human triggers, never a consequence of
   a render. Fleet constraint #5.
3. **No embedded agent.** No LLM API calls in application logic, no langchain/crewai, no
   custom tool-calling loop. Automation lives in Claude Code skills. Fleet constraint #1.
   `providers/ollama_script.py` calling a local model for *copy* is generation, not an
   agent loop — keep it that way.
4. **Measure, do not guess.** Costs, loudness, silence gaps and throughput in
   [`docs/render-pipeline.md`](docs/render-pipeline.md) are measured numbers with dates.
   If you change a claim, re-measure it and date it.

## Two results that are counter-intuitive — do not "fix" them

**Spoken domains.** [`speech.py`](backend/clemtock/speech.py) rewrites URLs before TTS.
`appearance-unlimited.com` → `AppearanceUnlimited dot com`, which measured **0 internal
pauses**. Saying "dash" out loud is the obvious fix and it measured *no better* than plain
spaces while adding 0.84 s of runtime. Lower-casing the join is worse than CamelCase, so
the capitals do real work. The full measurement table is in that module's docstring.
`speakable()` is applied inside **both** TTS paths; keep it that way.

**Loudness must be normalised per segment.** Sources never agree — a phone recording
measured -11.9 LUFS against HeyGen TTS at -22.1 LUFS, a 10 dB drop mid-ad that reads as
the second half being broken. Every spoken segment goes through
`loudnorm=I=-14:TP=-1.5:LRA=11`.

## Fragile bits, with the reason

- **Sprite lip-sync is structurally limited.** The local cartoon path (Rhubarb + mouth
  sprites) is free and offline, but it will not reach professional quality — that
  conclusion is why HeyGen talking-photo became the default. Do not re-litigate it by
  hand-tuning sprites.
- **chatterbox pins numpy < 2.0.** Installing opencv drags numpy 2.x in and breaks it.
  torch is pinned to CPU wheels deliberately: the default pull is a CUDA build, 6.2 GB
  against 1.8 GB, and neither laptop has a discrete GPU.
- **`scripts/serve.sh`** self-heals a stale pidfile by looking for the real process,
  because `setsid` forks mean the recorded pid is often not the server's.
- **Playwright captures no pointer in video frames.** `capture-site-demo.mjs` injects its
  own DOM cursor and moves it in steps; that stepping is what makes a recording read as a
  person rather than a script hitting selectors.

## Worked examples

`scripts/build-ad-au2.sh` and `scripts/build-ad-au2-liar.sh` assemble complete ads from
the command line, commented step by step. They are the specification for the phase-2 web
UI — **which is paused** at jimmer's request until the small issues are worked out. Do not
start building it.

## Open questions — do not guess

- **`michael` and `north-hero` carry PLACEHOLDER stock voices, not clones** (see each
  `voice.json` note). Confirm or replace before any client work.
- Whether the synthesised engine-crank SFX in the "Ran When Parked" spot gets replaced
  with a licensed effect. It is the weakest element in that ad and it is a one-line swap.
