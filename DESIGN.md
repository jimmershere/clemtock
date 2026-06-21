# clemtock — design

**clemtock** is a prompt-driven social-media **ad generator**. You give it some media
(images, a short video, image "snips") and a prompt; it writes an ad script, generates
any missing visuals/footage with AI, animates everything into a vertical (9:16) spot,
and exports an MP4 — optionally publishing it.

It is the generalized form of the hand-authored `clanimator` "Local 81 Promo": that promo
was a single timeline of hard-coded scenes; clemtock turns the **scene list, copy, asset
references, and motion into data** (`ad-script.json`) that a reusable renderer interprets.

## Principles (inherited from Local-81)

- **Honesty over magic.** The output labels what is AI-generated vs. user-supplied vs.
  motion-graphics. Stubs and unimplemented providers are labeled, never faked.
- **Secrets never at rest** in anything clemtock writes. Keys stay in the *existing*
  env files (`/app/tee-empire/.env`, `floor2:/home/floor2/content-machine/.env.agents`).
  clemtock reads them into process env at runtime; it never copies a secret into this repo.
- **Operator-readable artifacts.** `ad-script.json` is human-greppable and hand-editable.

## Provider matrix (validated 2026-06-19, auth-only probes)

| Modality | Provider | Status | Key source |
|---|---|---|---|
| Script brain (brief → `ad-script.json`) | OpenRouter (→ Claude / GPT) | ✅ | tee-empire `.env`, floor2 `.env.agents` |
| Stills (hero / background) | OpenAI `gpt-image-1` | ✅ | tee-empire `.env` (`OPENAI_API_KEY`) |
| Stills (fast / cheap) | OpenRouter `black-forest-labs/flux-schnell` | ✅ | tee-empire `.env` |
| Video clips (img/text → video) | kie.ai `flux-kontext-pro` | ✅ | floor2 `.env.agents` (`KIEAI_API_KEY`) |
| Spokesperson + voice-over | HeyGen avatar + cloned voice | ✅ | floor2 `.env.agents` |
| Alt LLM | Grok / xAI | ✅ | floor2 `.env.agents` |
| Compose / encode | ffmpeg 6.1.1 (CPU, 40 cores) | ✅ | floor2 binary |
| Local image/video gen | ComfyUI | ⚠️ unreachable | floor2 `COMFYUI_URL` |
| Publish | post-bridge / YouTube | ◻️ key set, untested | floor2 `.env.agents` |

floor2's own `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` are **401 (expired)** — clemtock uses
OpenRouter for Claude/GPT and tee-empire's OpenAI key for `gpt-image-1`. floor2's GPU
(TITAN X) is currently faulted, so treat ffmpeg as CPU-only.

## Pipeline

```
 prompt + uploads
       │
       ▼
 [1] brief  ── ScriptProvider (OpenRouter) ─────────▶ ad-script.json
       │                                                   │
 [2] assets ── ffmpeg on floor2: keyframe / trim ──▶ assets/*  (from uploads)
       │       AI gen for gaps:                            │
       │        ImageProvider (gpt-image-1 / flux)         │
       │        VideoProvider (kie.ai)                     │
       │        AvatarProvider (HeyGen)                    │
       ▼                                                   ▼
 [3] render ── data-driven DC renderer plays ad-script.json @ 1080×1920
       │
 [4] export ── client WebCodecs+mp4-muxer  |  floor2 ffmpeg mux (video clips + audio)
       │
 [5] publish (optional) ── post-bridge / YouTube
```

## `ad-script.json` (the contract)

See [`schema/ad-script.schema.json`](schema/ad-script.schema.json). Shape:

```jsonc
{
  "version": 1,
  "canvas": { "width": 1080, "height": 1920 }, "fps": 30, "duration": 15,
  "palette": { "ink": "#0B1018", "lime": "#A6E84A", "orange": "#EF6A28" },
  "assets": {
    "hero":  { "kind": "image", "source": "gen",    "provider": "gpt-image-1",
               "prompt": "..." , "src": "assets/hero.png" },
    "clip1": { "kind": "video", "source": "upload",  "src": "uploads/clip1.mp4" }
  },
  "scenes": [
    { "id": "open", "start": 0, "end": 2.6, "template": "title",
      "copy": { "kicker": "...", "headline": "...", "sub": "..." },
      "motion": { "type": "stamp" } },
    { "id": "hero", "start": 2.6, "end": 6.0, "template": "photo",
      "assets": ["hero"], "motion": { "type": "kenburns", "from": 1.0, "to": 1.12 } }
  ]
}
```

A **template** is a pure function `(t, scene, ctx) → React nodes`, mirroring the original
promo's scene functions. The renderer ships a small template library (`title`, `photo`,
`video`, `terminal`, `split`, `cta`) and resolves each scene by `template` name. Adding a
template never requires touching existing scenes.

## Backend & where it runs

clemtock's backend is a stdlib-first Python package (`backend/clemtock`). Provider calls
use `urllib` — no third-party HTTP dep — so it runs anywhere Python 3.12 is present.

Because the video/avatar keys live only on floor2, the runtime environment is **assembled
ephemerally** by [`scripts/load-env.sh`](scripts/load-env.sh): it sources tee-empire's
`.env` for OpenAI/OpenRouter and pulls floor2-only keys over `ssh` into the current shell.
Nothing is written to disk. ffmpeg-heavy steps (`assets`, `export`) shell out to floor2 via
`ssh` + `rsync` — the same push model Local-81 uses.

## Studio — web control panel + job API (floor2)

`backend/clemtock/server.py` (stdlib `ThreadingHTTPServer`) serves the **studio** UI and a
small job API on floor2:3053, so humans drive clemtock with buttons and AI/CLI users hit the
same endpoints. Vault keys are loaded into the server env at startup, so jobs authenticate.

- **UI** [`web/studio.html`](web/studio.html): pick a **format** (recipe), cast a **hero**
  (mascot), **character** (persona) and **model** (HeyGen avatar) from the asset library,
  write a brief, hit **Build ad**. Live job log streams in; the finished MP4 plays inline; a
  CLI-equivalent line updates as you choose (human ↔ AI parity). An *Advanced* drawer runs any
  allowlisted `clemtock` command.
- **API**: `GET /api/library` · `/api/recipes` · `/api/outputs` · `/api/jobs[/<id>]`;
  `POST /api/run {command,args}` (allowlist: script/assets/video/avatar/compose/run/export/probe)
  and `POST /api/build {recipe,prompt,hero,character,model,duration}` (recipe-driven `run`:
  stages chosen library images into `web/assets/`, augments the brief, launches `clemtock run`).
- Jobs are `subprocess.Popen` (argv list — no shell), logged to `out/jobs/<id>.log`, polled by id.

### Asset library & recipes

`assets/` is the **source library**, organized into `logos/ mascots/ characters/ creatures/`
with `.thumbs/` and a manifest [`assets/library.json`](assets/library.json) (id, file, thumb,
category, **roles**, tags, dims) + HeyGen **models**. Roles: `hero`=mascot/focal,
`character`=persona, `model`=talking avatar, `logo`=brand mark. Rebuild with
`scripts/build-library.py`. Ad **formats** live in [`web/recipes.json`](web/recipes.json):
`snip-music` (≈12 s, stills/snips + Ken-Burns + music, no voice) and `motion-tutorial`
(≈40 s, avatar/voice narration + real clips + captions).

## Deployment (floor2)

clemtock runs on **floor2** (40 cores; this laptop is the weaker control node). Canonical
copy at `floor2:/home/floor2/clemtock`; the laptop pushes with
`rsync -a --delete` (excludes `out/`, `.vault/`, `node_modules/`, `__pycache__/`) — the same
push model as Local-81. Headless render there uses snap chromium (`/snap/bin/chromium`,
auto-detected) via `playwright-core` + system `ffmpeg`.

**Web host:** `python3 -m http.server 3053 --bind 0.0.0.0` in `web/`, viewed at
**http://192.168.1.206:3053**. Port 3053 is ufw-allowed-from-Anywhere; 8910 is not (ufw
default-deny, and floor2 is a k8s node — its firewall is off-limits). The floor2 user has
`Linger=yes`, so the detached server survives ssh disconnect without a systemd unit. The
in-repo `web/out -> ../out` symlink exposes rendered MP4s at `/out/`.

## Secret vault

`backend/clemtock/vault.py` is an encrypted-at-rest store (idea from
[TheClawFirm/lockbox](https://github.com/TheClawFirm/lockbox)): **scrypt** KDF + **ChaCha20-
Poly1305** AEAD (scrypt over Argon2id because the laptop's `cryptography` 41.x lacks the
Argon2 KDF). The vault file holds only `salt`/`nonce`/`ciphertext` (0600); the plaintext
name→secret map never lands on disk. Passphrase comes from `CLEMTOCK_VAULT_PASSPHRASE` or a
0600 keyfile (`~/.clemtock/passphrase`), so a headless floor2 run self-unlocks while disk/git
exposure stays useless.

```bash
clemtock vault init                       # mint passphrase + empty vault
printf '%s' "$KEY" | clemtock vault set OPENAI_API_KEY   # value via stdin only
clemtock vault import-env path/to/.env    # bulk import KEY=VALUE
clemtock vault list                       # names only
```

`main()` auto-loads the vault into process env for every non-vault command, so `script` /
`assets` / `probe` transparently use vault-stored keys (and the bash `probe` inherits them).
On floor2 the vault holds all `content-machine/.env.agents` keys **plus** the working
gpt-image-1 key copied from the laptop — `clemtock probe` authenticates all five providers
reading purely from the vault.

## Phases

| Phase | Scope | State |
|---|---|---|
| 0 | Scaffold: docs, schema, env wiring, provider interfaces, probe, data-driven renderer | ✅ done |
| 1 | `script`: brief → `ad-script.json` via OpenRouter (real) | ✅ done — `OpenRouterScriptProvider`, `clemtock script` |
| 2 | `assets`: AI image-gen (gpt-image-1) + ffmpeg video posters | ✅ done — `clemtock assets`, verified with a real generation |
| 3 | Template library: title / photo / video / terminal / split / cta | ✅ done — six templates in `web/templates.js` |
| 4 | `export`: headless render → MP4 on disk (`out/`) | ✅ done — `clemtock export` via `web/render-headless.mjs` (chromium+ffmpeg) |
| 5 | kie.ai video + HeyGen avatar providers (true motion-gen) | **✅ both verified.** `clemtock avatar` → HeyGen talking-head + cloned voice (720×1280 H.264+AAC). `clemtock video` → kie kling-2.6 image-to-video (5s 1920×1080) — createTask→poll→download all working. **Caveat:** kie's *file-upload* subdomain (`kieai.redpandaai.co`) rejects floor2's IP even when `api.kie.ai` accepts it, so **local-image seeding is blocked**; pass a **public image URL** to `--image` (supported) until that upload host is whitelisted. Two kie gotchas baked into the provider: force **IPv4** (api.kie.ai has AAAA → IPv6 egress isn't whitelisted) and a **browser User-Agent** (Cloudflare bot-blocks `Python-urllib` with error 1010). |
| 6 | ffmpeg compositor: real clips + audio under the graphics layer | **✅ verified.** `clemtock compose` — renders the graphics with alpha (`render-headless --alpha` → qtrle overlay), lays clips on an ink base at their scene windows, overlays graphics, muxes per-clip audio (delayed to scene start). Falls back to plain export when an ad-script has no clips. `clemtock run` ties script→assets→compose into one command. |
| 7 | Publish to socials (Post Bridge) | **✅ done.** `clemtock accounts` lists connected socials; `clemtock publish --video <mp4> --to youtube,twitter --caption "…"` is **dry-run by default**, posts only with `--execute` (irreversible). Flow: create-upload-url → PUT bytes → POST /v1/posts. Studio has a per-output ⤴ publish panel with dry-run + a confirm-gated live post. |

## Asset uploads & auto-scan

The studio accepts up to **3 reference image uploads** (`POST /api/upload`, base64 → `assets/uploads/`).
The library **auto-discovers** any new/dropped-in file (`clemtock.library.rebuild`, role inferred from
its folder), and the server **rescans every 15 minutes**, **before every plan/execute** (`/api/build`,
`/api/run`), and on demand via the **rescan** button (`POST /api/rescan`).

## Deploy via local81

clemtock ships through **local81** (the deploy control-plane it lives alongside):
`.local81/config.ini` defines a `clemtock` scope (source `.` → `floor2:/home/floor2/clemtock`,
rsync with excludes) and `.local81/hooks/post-deploy.sh` restarts the control server + smoke-checks it.

```bash
local81 plan --scope clemtock
local81 deploy --latest --scope clemtock --allow-drift   # --check for dry-run
```

> Note: local81 sync + hooks run cleanly (verified, with a run record). The post-deploy hook's
> *server restart* over nested ssh is unreliable on this host (systemd-logind detach quirk); a
> direct `nohup setsid … & disown` persists. For production, run the control server as a
> systemd **user** service (linger is already enabled) rather than via the hook.

### Full workflow (`clemtock run`)

```
clemtock run --prompt "<brief>" --assets uploads/ --out out/clemtock-final.mp4
  ├─ script   brief ─OpenRouter→ ad-script.json        (skipped if --prompt omitted)
  ├─ assets   source:gen → gpt-image-1 stills · HeyGen avatars · kie videos
  │           source:upload video → ffmpeg poster
  └─ compose  alpha graphics overlay + real clips on ink base + audio → MP4
```

Verified composite (`web/ad-script.compose-test.json`): title → kie image-to-video clip with
copy → terminal → HeyGen talking-avatar (with voice audio) → CTA, as one 18 s 1080×1920 H.264+AAC
file. The alpha overlay keeps the DOM-rendered copy/motion-graphics pixel-perfect over real footage.

**kie video gen caveat (unchanged):** `assets` generates `source:gen` videos via kie only when the
asset carries a public `seed_url` (kie's file-upload host is IP-gated for floor2). HeyGen avatar gen
has no such limit.

`clemtock video --image <png> --prompt <...>` (kie image-to-video, kling-2.6) and
`clemtock avatar --text <...>` (HeyGen) are wired; both async providers poll to completion and
download the MP4. kie needs the seed image as a public URL, handled via kie's own base64
uploader — no third-party hosting of the user's file.

> **Phase 4 scope note (honesty over magic):** `export` rasterizes the DOM animation
> frame-by-frame in headless chromium, so it captures motion-graphics, AI **stills** (Ken-Burns),
> and copy perfectly. Uploaded/AI **video clips** currently contribute a poster still (Phase 2);
> compositing their actual motion is the ffmpeg-mux step (Phase 6).
