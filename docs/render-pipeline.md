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
| PR-12 | Resale pricing — unanswerable until `cost.json` has real numbers (stage 2). |

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
