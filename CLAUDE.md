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

**A photo-avatar upload costs ~79 credits / ~$1.32. Uploads are NOT free.** This was
believed to be free and written down as free, and on 2026-10-09 an 8-upload probe to test
the slot limit cost **$10.53** on that false premise. Derived twice and the two agree
exactly: 8 uploads burned 4404→3772 credits ($73.40→$62.87), i.e. 79 credits each; and the
single `portwright` upload on 2026-10-07 took 100 credits with the render, of which the
render was 21. **Deletes are free** — the 8 deletes in that probe added nothing.

Practical consequences: onboarding a character costs ~$1.32, and so does every re-upload
when its art changes. Never loop uploads to probe a limit. And the old "delete-then-upload
per render" fallback — floated when slots were capped at 3 — would have cost $1.32 *per
render*; it is a bad idea on cost grounds alone, independent of the slot question.

**Photo avatars are UNLIMITED on this account — slots are not a constraint.** Settled
2026-10-09 three ways: HeyGen's help article ("Free users can create up to 3 unique photo
avatars, while Creator, Team and Enterprise users have Unlimited photo avatar slots"), the
pricing page (Free "Up to 3", Creator $29/mo "Unlimited"), and empirically — twelve groups
created back to back, no refusal, then cleaned up. The $29/mo Creator subscription is live
and doing its job.

What is **not** unlimited: **Custom Video Avatars** (digital twins built from video) — 1 on
Free/Creator, 5+ on Business, 10+ on Enterprise. This pipeline uses photo avatars, so that
cap does not apply. Don't be put off by digital-twin numbers in the pricing table.

Historical, because it still shapes the code: on the free tier the quota counted avatar
**GROUPS**, not talking photos, and deleting a photo returned 200 while leaving its group
behind — which is why cleanup targets the group. `talking_photo_id()` now uploads **first**
and deletes the old group **after**; the old delete-first order existed only to free a slot
and would destroy a working avatar if the upload then failed.

The API does not report the cap. Any "N/3" you see in older notes was an assumed
denominator written in the shape of a measurement, not something HeyGen returned.

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
- **HeyGen returns 25 fps, and `zoompan` does not resample.** `zoompan` with `d=1` emits
  one output frame per *input* frame; its own `fps=` only labels the timebase. Put an
  explicit `fps=30` **before** zoompan or a 9.02 s take becomes 225 frames stamped at
  30 fps — a 7.5 s video against 9.02 s of audio, which the assemble then truncates
  silently. Cost an hour on 2026-10-07; the container duration still reads correct, so
  check the **video stream** duration, not `format=duration`.
- **ImageMagick `-stroke` persists.** After drawing the amber brackets, every later
  `-annotate` inherits a 5 px stroke that swamps the fill at small point sizes. Reset with
  `-stroke none`. Likewise, two `-annotate` offsets on one centred canvas overlap rather
  than flow — render words separately and `+append` them (this is what produced
  "POWRIGHT").

## Worked examples

`scripts/build-ad-au2.sh`, `scripts/build-ad-au2-liar.sh` and
`scripts/build-ad-portwright.sh` assemble complete ads from the command line, commented
step by step. The portwright one is the brand-exact example: its palette and wordmark are
sampled from the live site rather than invented. They are the specification for the phase-2 web
UI — **which is paused** at jimmer's request until the small issues are worked out. Do not
start building it.

## Open questions — do not guess

- **`michael` and `north-hero` carry PLACEHOLDER stock voices, not clones** (see each
  `voice.json` note). Confirm or replace before any client work.
- Whether the synthesised engine-crank SFX in the "Ran When Parked" spot gets replaced
  with a licensed effect. It is the weakest element in that ad and it is a one-line swap.
