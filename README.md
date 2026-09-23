# clemtock

Prompt-driven social-media **ad generator**. Feed it images, a short video, and/or image
"snips" plus a prompt; it writes an ad script, generates missing visuals/footage with AI,
animates a vertical (9:16) spot, and exports an MP4.

Generalized from the `clanimator` "Local 81 Promo" — the hand-authored animation becomes a
**data-driven** renderer that plays an `ad-script.json`.

> Status: **scaffold (Phase 0)**. See [DESIGN.md](DESIGN.md) for the architecture and the
> validated provider matrix. Unimplemented steps are labeled as stubs, never faked.

## Quickstart

```bash
# 0. First time on quasimodo: install ffmpeg/chromium/node + python3-cryptography, npm install, probe.
bash scripts/quasimodo-setup.sh

# 1. Keys are read from /app/portrender/.env → /app/clemtock/.env → /app/tee-empire/.env
#    (never written back). Source this only if you want them in your shell too.
source scripts/load-env.sh

# 2. Confirm every provider authenticates (auth-only, no generation spend).
scripts/probe-providers.sh

# 3. Turn a brief into an ad-script (real — calls OpenRouter).        [Phase 1]
python -m clemtock script \
  --prompt "30s vertical ad for Local 81, gritty union-shop tone, end on GitHub CTA" \
  --assets uploads/ \
  --out web/ad-script.json

# 4. Generate any source:gen stills + extract posters from uploaded clips.  [Phase 2]
python -m clemtock assets --script web/ad-script.json

# 5. Preview / scrub in the browser (open web/clemtock-renderer.dc.html), then
#    render the spot straight to an MP4 on disk.                       [Phase 4]
python -m clemtock export --script web/ad-script.json --out out/clemtock-ad.mp4
```

`export` drives the renderer in headless chromium (via playwright-core + system chromium)
and pipes frames through ffmpeg — no browser download dialog, the file lands in `out/`.

## Layout

```
clemtock/
  DESIGN.md                      architecture, schema, phases, provider matrix
  schema/ad-script.schema.json   the ad-script contract
  scripts/
    load-env.sh                  export keys from the .env files (no ssh, nothing written)
    probe-providers.sh           auth-only health check for every provider + local toolchain
    quasimodo-setup.sh           one-shot host setup (apt packages, npm install, probe)
    serve.sh                     start/stop the studio server (0.0.0.0:3053)
    install-user-service.sh      systemd user unit for the studio (survives logout with linger)
  backend/clemtock/              stdlib-first Python package
    config.py                    provider config from env (no secrets at rest)
    providers/                   ScriptProvider / Image / Video / Avatar interfaces + impls
    cli.py                       `python -m clemtock <script|assets|render|export|run>`
  web/
    support.js                   DC runtime (from clanimator)
    clemtock-renderer.dc.html    data-driven renderer: plays ad-script.json
    templates.js                 scene template library (title/photo/video/terminal/cta)
    render-mp4.html              offline MP4 exporter (generalized)
    ad-script.json               example script (renders out of the box)
  uploads/                       your input media (gitignored)
  out/                           generated assets + MP4s (gitignored)
```

## Secrets

clemtock **never stores keys** in the repo. It reads them at runtime from, in order:

- `/app/portrender/.env` — `OPENAI_API_KEY` (shared with portrender; gpt-image-2 stills)
- `/app/clemtock/.env` — `KIEAI_API_KEY`, `HEYGEN_API_KEY`, `HEYGEN_VOICE_CLONE_ID`,
  `HEYGEN_CARTOON_AVATAR_ID`, `XAI_API_KEY`, `POST_BRIDGE_API_KEY`, `OPENROUTER_API_KEY` (gitignored; chmod 600)
- `/app/tee-empire/.env` — `OPENROUTER_API_KEY`, Printify (when tee-empire is cloned on this host)
- the encrypted vault (`clemtock vault …`, needs `python3-cryptography`) — optional

`config.load_env_files()` does this for the CLI and the studio server; `scripts/load-env.sh`
does the same for an interactive shell. Override the list with `CLEMTOCK_ENV_FILES=a:b:c`.

## Where it runs

**quasimodo**, `/app/clemtock` (user `jimbro`). ffmpeg, chromium, node and every provider call are
local to that host; there is no remote render host. pop-os pushes code with
`local81 deploy --scope clemtock` (excludes `out/`, `uploads/`, `.vault/`, `node_modules/`, `.env`),
and the post-deploy hook restarts the studio. Studio: **http://192.168.0.20:3053**
(`scripts/serve.sh start` or `scripts/install-user-service.sh`). portrender on the same host
drops approved art into `assets/<category>/` and calls `POST /api/rescan`.
