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
# 1. Assemble the runtime environment (ephemeral — sources existing env files + floor2).
#    Nothing is written to disk; keys never enter this repo.
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
    load-env.sh                  assemble runtime env (tee-empire .env + floor2 over ssh)
    probe-providers.sh           auth-only health check for every provider
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

clemtock **never stores keys**. They stay in the existing files they already live in:

- `/app/tee-empire/.env` — `OPENAI_API_KEY` (gpt-image-1), `OPENROUTER_API_KEY`
- `floor2:/home/floor2/content-machine/.env.agents` — `KIEAI_API_KEY`, `HEYGEN_*`,
  `OPENROUTER_API_KEY`, `XAI_API_KEY`, publish keys

`scripts/load-env.sh` loads them into the current shell at runtime only.
