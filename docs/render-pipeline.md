# Cartoon avatar ad pipeline — architecture

Decided 2026-09-23. Supersedes the HeyGen/kie.ai assumption baked into
`providers/heygen.py` and `providers/kie_video.py`.

**Direction, from jimmer:** the product is **cartoon / mascot avatars, not
photoreal humans.** That single decision changes the whole cost structure — see
"Why this is cheap" below.

**Voice consent:** jimmer confirms every voice to be cloned has given express
permission (*user-reported, 2026-09-23*). Chatterbox clones from ~5 s of
reference audio; keep the permission on record per voice, alongside the
reference clip, in `assets/voices/<name>/CONSENT.md`.

## The key insight: cartoon avatars don't need a GPU

A photoreal talking head needs a diffusion model to hallucinate a face moving —
that is why HeyGen charges and why SadTalker wants a GPU. A **cartoon** mascot
does not. Its mouth is a finite set of drawn shapes, and lip-sync is choosing
which shape to show on which frame. That is a solved, deterministic, CPU-instant
problem:

**[Rhubarb Lip Sync](https://github.com/DanielSWolf/rhubarb-lip-sync) (MIT)**
reads a WAV and emits a timeline of Preston Blair mouth shapes (A–H). Feed it
the Chatterbox voice-over, composite the matching mouth sprite onto the mascot
per frame with ffmpeg, and the talking avatar is done — **no GPU, no per-clip
fee, no licence risk.**

portrender already has the art half: the `mascot-sheet` template
("Character / mascot model sheet") is exactly the tool for drawing a character
plus its A–H mouth set as a consistent sheet.

## Two planes

| | Control plane — **pop-os** | Render plane — **vast.ai, ephemeral** |
|---|---|---|
| Runs | always (it is a laptop, but it is the queue) | only while a batch is draining |
| Cost | $0 marginal | ~$0.40/hr, billed until destroyed |
| Does | script, voice, lip-sync, compositing, mux, gate | Wan 2.2 b-roll, heavy diffusion |
| State | owns everything | owns nothing; treat as disposable |

Everything that *can* run on CPU *does*, because CPU here is free and the GPU is
metered. The rented box is reserved for the one job it is uniquely needed for:
cinematic motion shots.

### Per-ad flow

```
brief ──► ollama (pop-os, free) ──────────────► ad-script.json
                                                   │
          ┌────────────────────────────────────────┤
          ▼                                        ▼
  Chatterbox TTS (CPU)                    scene assets
          │                          ┌──────────────┴───────────────┐
          ▼                          ▼                              ▼
   voice.wav ──► Rhubarb (CPU)   mascot art                   b-roll motion
          │           │          (portrender /               (Wan 2.2 — the
          │           ▼           local diffusion, CPU)        ONLY GPU step)
          │     mouth timeline            │                          │
          └───────────┴───────────────────┴──────────────────────────┘
                                          ▼
                            ffmpeg composite + mux (CPU)
                                          ▼
                              HUMAN GATE (fleet rule 5)
                                          ▼
                            PostBridge / Etsy / Printify
```

Note that the GPU appears **once**, and only for b-roll. An ad that is pure
mascot-on-a-background never rents anything — but per PR-11 the b-roll path is
*in* for v1, so expect most ads to touch the rented 4090 at least briefly. That
makes the batching rule below load-bearing rather than theoretical.

## The cost rule: batch, never per-job

An idle GPU bills identically to a busy one, so renting one per ad is the single
easiest way to burn the $100 credit for nothing. The queue must work like this:

1. Jobs accumulate in a pending queue on pop-os. CPU stages (script, voice,
   lip-sync, composite) run immediately — they are free.
2. Only jobs that actually need b-roll get a `gpu_pending` flag.
3. When the flag count crosses a threshold (or a human says go), rent **one**
   instance, drain **every** queued GPU job, then `destroy()`.
4. `destroy()` is in a `finally`. A crashed render must not leave a meter running.

`VastGPU.destroy_all(live=True)` is the panic button. `running_cost()` reports
the current burn across the account; wire it into the studio UI so an orphaned
instance is visible rather than discovered on the invoice.

At ~$0.40/hr, 250 GPU-hours of credit, and a few minutes of GPU per b-roll clip,
the marginal cost of a cartoon ad is **cents** — and zero if it needs no b-roll.

**The binding constraint is throughput, not money.** Chatterbox at 8-15x realtime on
pop-os caps one laptop at roughly 380 fifteen-second ads/day, 190 at thirty seconds,
96 at sixty — halve those for a machine also doing other work, with 1-2 concurrent
slots. That is ample for dozens of retainer clients and nowhere near enough for an
open self-serve API, which is the single strongest argument for the retainer model in
issue #8. Whether a rented GPU lifts TTS throughput materially is **untested** —
measure before promising anyone a turnaround time.

## Business model — DECIDED 2026-09-23

**Customer: local businesses. Model: Option A, mascot-as-a-service retainer.**
(jimmer, answering [issue #8](https://github.com/jimmershere/portrender/issues/8).)

- **One-time build fee $500–1,500** — character design, the nine mouth shapes, a cloned
  voice, the brand theme. This is the only genuinely manual work, and it is also what
  makes the client stay: their mascot lives here.
- **Then $299–799/mo** for an agreed number of videos.

Anchored against the two market poles: a custom 2D mascot build plus three videos runs
**$20–28k** at an agency (median 60 s explainer quote: **$9,680**), while small-business
social retainers run **$1–5k/mo**. We are ~5% of the former and the cheap end of the
latter, at a marginal cost of approximately zero.

Deliberately **not** priced against HeyGen/Creatify at $19–29/mo. That would frame this as
a cheaper talking-head tool, which is the one thing it is not — those sell a stranger's
face reading your script; we sell *their own character*, consistently, forever.

What this decision rules out for now: no self-serve credits, no public API, no auth, no
billing system. Fleet rule 2 stands, and the retainer model does not need any of them.

## The jimmer character

Source art: `portrender/brands/jimmer/character.png` (1024x1536, transparent background),
from Drive → Pictures → ice-stone. Mouth sprites derived from it, both gitignored (PR-5).

Regenerate after a new export of the same character — the coordinates are fractions, so
they survive a resize:

```bash
python3 scripts/sprites-from-character.py \
  --image /app/portrender/brands/jimmer/character.png \
  --out   /app/portrender/brands/jimmer/mouths \
  --mouth-x 0.500 --mouth-y 0.144 --mouth-w 0.044 --cover-scale 1.45 --feather 0.02
```

Then `clemtock avatar --brand jimmer --text "…"`.

**Honest quality note.** `sprites-from-character.py` paints mouth shapes over a patch of
sampled skin. The shapes animate correctly and read as speech at normal playback, but the
cover patch flattens the moustache and lip line, and a viewer looking closely will see it.
This is a same-day stopgap so a client's character works immediately — **not** the
finished article. Proper mouth variants are drawn (or generated from the source art with
portrender's `edit-refine` template once there is OpenAI credit), and that work is exactly
what the Option A build fee pays for.

## Two avatar paths, and when to use which

Measured 2026-09-23 on the jimmer character.

| | **HeyGen talking photo** | **Local sprite chain** |
|---|---|---|
| Quality | professional — real lip shapes, teeth, jaw and beard moving with speech | crude; a mouth shape swapped on a patch of skin |
| Cost | **~$0.019 per second** ($0.10 for 5.3 s, observed on the wallet) | $0.00 |
| Speed | ~63 s per clip, on their GPUs | 8-15x realtime on pop-os CPU |
| Needs | HeyGen key + credit | nothing |
| Command | `clemtock avatar --provider heygen --brand <slug>` | `clemtock avatar --brand <slug>` |

**For paying client work, HeyGen is the default.** At $0.019/s a 30-second ad costs about
$0.57. Against a $299-799/mo retainer that is a rounding error — twelve 30-second videos a
month is under $7 of cost, a ~97% margin. The earlier "keep HeyGen for the occasional
premium spot" position was written before the price was measured, and the measurement
overturns it.

The local chain keeps its place: bulk drafts, offline work, and anything where a client is
iterating on wording and does not need finished quality yet.

### Why we are NOT building GPU lip-sync on the rented 4090 (yet)

LatentSync (Apache-2.0) and MuseTalk (MIT) would run on the vast.ai 4090 and cost ~$0.02
per clip instead of HeyGen's ~$0.57 for 30 s. That is a real saving *per unit* and an
unreal one in total: at plausible retainer volumes it saves single-digit dollars a month,
against building and maintaining a ComfyUI/model pipeline on a rented box. That is exactly
the premature optimisation fleet rule 2 exists to prevent.

Revisit when any of these is true:
- monthly HeyGen spend passes roughly $50 (~85 thirty-second videos)
- a client needs offline or on-premise rendering
- the v2 sunset below forces a rewrite anyway

### The 3-character limit is a PLAN limit, not a product one

Hit on 2026-09-24: `You have exceeded your limit of 3 photo avatars`. It looks like a
hard ceiling on how many customers this model can serve. It is not.

- **Free / wallet-only: 3 photo avatars.** *(web)*
- **Creator ($29/mo), Team, Enterprise: unlimited photo avatars.** *(web)*

The account reports `billing_type: wallet` — pay-as-you-go API credits with **no
subscription** — so free-tier feature caps apply despite a $98 balance. Credit and plan
are separate things on HeyGen and buying more credit does not lift this.

**So the fix is a $29/mo subscription**, against retainers of $299-799/mo per client.
It is noise, and it removes the ceiling entirely. Do that before onboarding a third
character.

Two things worth keeping straight:

- The quota counts avatar **groups**, not characters and not talking photos. Deleting a
  talking photo returns 200 and leaves its group behind still consuming a slot — which is
  why clearing photos appeared to do nothing. `heygen_character.delete_group()` is the
  one that actually frees capacity.
- "Unlimited photo avatars" is not "unlimited instant avatars". *Instant avatars* /
  digital twins (built from video) stay capped — 5 on Business, 10+ on Enterprise *(web)*.
  We use **photo avatars** (a still driven by speech), which is the unlimited one.

**Fallback if a subscription is unwanted: rotate.** Uploading is free and takes seconds,
so the pipeline can delete-then-upload per render, turning 3 into a *concurrency* limit
rather than a *customer* limit. The primitive is implemented and verified
(`talking_photo_id(..., refresh=True)` released a group and uploaded a replacement with
the count unchanged). It is strictly worse than paying $29 — it adds seconds per render
and a crashed render leaks a slot — so treat it as a fallback, not the plan.

### Deadline: the HeyGen endpoints we use retire 2026-10-31

`/v2/video/generate` returns a Legacy warning naming **2026-10-31**, and points at the v3
API (`POST /v3/videos`). `/v1/video_status.get` is the same generation. This is ~5 weeks
out and it is not optional — migrate `providers/heygen.py` to v3 before then.

## Character asset gotchas (both hit the jimmer file)

1. **A baked-in transparency checkerboard.** `jimmer-standing.png` arrived with *no alpha
   channel* and the grey/white checker painted into the pixels — an export that captured
   the editor's transparency grid. It is invisible until you composite, then it is in every
   frame. Fix, keeping the character's own whites intact by flooding only from the border:

   ```bash
   convert in.png -alpha set -channel rgba -fuzz 20% -fill none \
     -draw "matte 1,1 floodfill"    -draw "matte 1022,1 floodfill" \
     -draw "matte 1,1534 floodfill" -draw "matte 1022,1534 floodfill" \
     +channel out.png
   ```
   Check the result with `-alpha extract`: the opaque fraction should look like a figure
   (~38% here), not ~100%.

2. **A typo in the artwork.** The shirt read "APPEARNCE". Patched by cloning the 'A' glyph
   from earlier in the same wordmark and shifting "NCE" right. It reads correctly now but
   leaves a faint seam at the join — a gradient logotype cannot be repaired convincingly in
   raster. **Fix it in the source vector file.**

## Renting this out as an API — staged, not now

jimmer wants to resell this as an API for others to generate cartoon/avatar ads.
That is a real product and the economics above are why it works. But it collides
head-on with **fleet rule 2**: *no auth, no login, no multi-user schemas until
the thing works on localhost and jimmer has used it.*

That rule is right and this plan does not break it. Instead, build the seams now
and the multi-tenancy later:

**Stage 1 — single tenant (now).** One operator, localhost, no auth. What exists.
The only concession to the future: **every job is already a self-contained
directory** (`out/jobs/<job_id>/` holding script, voice, assets, frames, result,
and a `cost.json`). No global mutable state, no shared scratch. A job that is
self-contained is trivially a tenant's job later; one that writes to a shared
`out/` never will be.

**Stage 2 — cost truth.** Record actual GPU seconds and $ per job in
`cost.json`. You cannot price a product you cannot cost, and the number is only
obtainable by instrumenting now, while it is one tenant.

**Stage 3 — one real customer, manually.** Run somebody else's ad through the
same CLI by hand. This is where the real requirements surface (asset upload,
revisions, brand voice, turnaround, what they actually complain about).

**Stage 4 — API, only if 3 worked.** *Then* add auth, tenancy, quota and billing
— against real requirements instead of imagined ones.

Things that would be wrong to build before stage 3: user accounts, a billing
integration, a public gateway, k8s, or an auto-scaler.

### What an API changes, structurally

Worth knowing now even though it is not being built:

- **Isolation becomes a security property, not tidiness.** A rented GPU running
  another customer's prompt must not see your keys. The `onstart` script and
  `env` passed to `VastGPU.rent()` are the boundary — never put `OPENAI_API_KEY`,
  Printify or Etsy credentials on a render box. The render plane should receive
  *assets and a prompt*, nothing else.
- **The human gate cannot survive as-is.** Fleet rule 5 assumes one operator
  approving their own work. For customers, the gate becomes *their* approval of
  *their* ad, which is a product surface, not a CLI prompt.
- **Abuse.** The moment strangers can drive image and voice generation, you own a
  moderation problem — including voice cloning, where "express permission" stops
  being something you can vouch for personally.

## Open questions — ask, don't guess

| # | Question |
|---|---|
| ~~PR-9~~ | **ANSWERED 2026-09-23.** `vastai/comfy` publishes **no `latest` tag** (Docker Hub 404s), nor does `vastai/base-image` — the placeholder would have rented a box that could never start, and a box that cannot start still bills. Pinned to `vastai/comfy:v0.37.0-cuda-12.9-py312` (9.76 GB); `PROBE_IMAGE` is `vastai/base-image:cuda-12.9.2-auto` (7.65 GB) for lifecycle checks. |
| PR-13 | **HeyGen auto-reload is ON** — `$75` recharged whenever the wallet drops below `$5`. The budget is not the $98.78 showing; it is uncapped until that is switched off. Turn it off, or decide the ceiling deliberately. |
| PR-14 | HeyGen has **zero cartoon avatars** in its 1,264-avatar stock library — all photoreal presenters. Cartoon requires the talking-photo upload path (a payload branch `heygen.py` does not have). Is HeyGen worth it for a cartoon product at all? |
| PR-10 | Where does the mascot mouth-sprite set live — portrender `brands/<slug>/` (and is that OK for a public repo, cf. PR-5) or clemtock `assets/`? |
| ~~PR-11~~ | **ANSWERED 2026-09-23 — keep it.** "we still want the cinematic b-roll via Wan 2.2 on a rented 4090 included in this version." So the rented GPU is part of v1, not a later option, and `comfy_video.py` is in scope. Ken-Burns over stills stays available as the cheap fallback, not the plan. |
| PR-12 | **Researched 2026-09-23** → [issue #8](https://github.com/jimmershere/portrender/issues/8). The market has two anchors ~100x apart: commodity AI video SaaS ($19-149/mo, generic photoreal heads) and custom mascot animation ($5-25k **per minute**; median 60s explainer **$9,680**; mascot build + 3 videos year one **$20-28k**). We sit in the unoccupied middle — *your* character, in minutes. Recommendation: **mascot-as-a-service retainer** (build fee $500-1.5k, then $299-799/mo), because it is the only option compatible with fleet rule 2 today and the one the data supports. Still open: are we selling to local businesses or to other builders? |

## Rented-GPU lifecycle — verified live 2026-09-23

Two paid runs against the real account, total spend **$0.0002**:

| | |
|---|---|
| search → rent → wait → verify → destroy | works; contracts 52267396 and 52267539 |
| provisioning | **~3 min** before the container is up (7.65 GB image pull), all billed |
| teardown | `destroy()` in a `finally`; account confirmed back to 0 instances, $0.000/hr |
| observed rate | $0.402–0.472/hr for a 24 GB 4090 |

Two bugs the live runs exposed, both now fixed:

- **`wait_running` returned too early.** vast reports `cur_state` (the contract — "running"
  the moment the box is yours) and `actual_status` (the container — "loading" while it
  pulls the image). The first run reported RUNNING at `actual_status: None`; a render job
  would have talked to a box with nothing on it. Now requires `actual_status == "running"`,
  and the second run correctly showed `running (container not up yet)` → `loading` →
  `running`.
- **Offer ids go stale in minutes.** Offer 49259401 rented fine, then answered
  `no_such_ask … is not available` on the very next attempt — somebody else took the
  machine. `rent_first_available()` now falls through the offer list; the second run
  skipped the dead offer automatically and rented the next one.

That ~3 min of paid provisioning per rent is the whole argument for batching: it is
~$0.02 of pure overhead every time you rent, regardless of how much work you then do.

## Cartoon avatar chain — built and verified 2026-09-23

`python3 -m clemtock avatar --text "…" --sprites assets/mouths/<set> --out out/x.mp4`

Chatterbox (MIT) → Rhubarb (MIT) → ffmpeg. No GPU, no API key, no per-clip cost.
Output verified: **1080×1920 h264 + aac**, audio length exactly matching the video,
34 mouth cues across 8 distinct shapes on a 5.2 s line — real lip-sync, not a
stuck mouth.

**Measured speed, which corrects the research note.** `local-ai-options.md` cited
"Chatterbox-Nano ~3× faster than realtime on 8 cores". That is the **Nano**
variant; the default model on pop-os is **8–15× SLOWER than realtime**:

| line | chars | audio | synthesis |
|---|---|---|---|
| short | 30 | 1.64 s | 25 s (15× realtime) |
| long | 124 | 5.56 s | 44 s (8× realtime) |

So a 30-second voice-over costs roughly **4–8 minutes of CPU**. Fine for batch and
overnight work, wrong for interactive iteration. Chatterbox-Nano is the upgrade
path if that becomes the bottleneck. Rhubarb and ffmpeg are negligible by
comparison — the whole rest of the chain is seconds.

Char rate held steady between the short and long lines (18.3 vs 22.3 char/s),
which rules out silent truncation of long text.

**Packaging.** Chatterbox lives in `.venv` and is driven out-of-process
(`_chatterbox_worker.py`), so clemtock's runtime stays stdlib-only and still
imports on a host with no venv. Note `chatterbox-tts` pins `torch==2.6.0` and pip
resolves that to the **CUDA** build by default — 6.2 GB of venv on a machine with
no NVIDIA GPU. `setup-avatar-chain.sh` force-reinstalls the CPU wheels and purges
the orphaned `nvidia-*`/`triton` packages: **6.2 GB → 1.8 GB**.

**Sprite sets** live in `assets/mouths/<name>/` as `A.png … F.png` (G/H/X
optional). `_placeholder/` is a generated test set, not art. Six images is a
complete mouth — `sprite_for()` degrades missing shapes along a documented
fallback chain, all the way to `A` if need be, so a partial set still renders.

## Status

Built and verified 2026-09-23:

- `providers/ollama_script.py` — local ScriptProvider, same system prompt as
  OpenRouter so scripts cannot drift. Selected by `_pick_script_provider()`.
- `providers/vast_gpu.py` — offer search, credit, instance list, rent, destroy,
  `destroy_all` panic button. **Read paths verified live**; `rent`/`destroy`
  are dry-run by default and have **not** been exercised against real billing.

Verified live on pop-os: ollama v0.34.3 + `qwen3:8b` generating a full 15s ad
script in ~60-85s with no API key and no cost. `think: False` is essential —
without it qwen3 spends its whole budget reasoning and never finishes on CPU.

Not built yet: Chatterbox TTS provider, Rhubarb integration, the compositor, the
job queue. **No longer blocked** — `python3.12-venv` and `imagemagick` are
installed and `ensurepip` works, so a venv for Chatterbox can be built. The next
concrete step is `providers/chatterbox_voice.py` + a Rhubarb wrapper, then the
ffmpeg compositor against the 15 mascot assets already in `assets/`.
