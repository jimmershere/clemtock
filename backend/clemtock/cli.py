"""clemtock CLI — `python -m clemtock <command>`.

Implemented now: `probe` (provider health), `script` (brief -> ad-script.json via
OpenRouter). `assets`, `render`, `export`, `run` are scaffolded and labeled as TODO so the
tool never pretends to do work it can't yet.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from . import vault as vault_mod
from .config import Config
from .providers import ProviderUnavailable
from .providers.openrouter import OpenRouterScriptProvider

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v"}
_REPO = Path(__file__).resolve().parents[2]


def _repo_path(p: str | Path) -> Path:
    """Resolve a relative path against the repo root (jobs run with cwd=backend/, so a
    UI-supplied 'out/foo.mp4' must map to <repo>/out/foo.mp4, not <repo>/backend/out/)."""
    q = Path(p)
    if q.is_absolute():
        return q
    return q if q.exists() else (_REPO / p)


def _manifest(assets_dir: Path) -> dict:
    """Build an asset manifest the script-brain can reference by id."""
    out: dict[str, dict] = {}
    if not assets_dir.exists():
        return out
    for p in sorted(assets_dir.iterdir()):
        ext = p.suffix.lower()
        if ext in _IMAGE_EXT:
            kind = "image"
        elif ext in _VIDEO_EXT:
            kind = "video"
        else:
            continue
        # emit web-relative paths so the renderer/static server resolves them as URLs
        web = _REPO / "web"
        src = str(p.relative_to(web)) if p.is_relative_to(web) else str(p)
        out[p.stem] = {"kind": kind, "source": "upload", "src": src}
    return out


def cmd_probe(args: argparse.Namespace) -> int:
    script = _REPO / "scripts" / "probe-providers.sh"
    return subprocess.call(["bash", str(script)])


def cmd_script(args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    assets = _manifest(Path(args.assets)) if args.assets else {}
    try:
        provider = OpenRouterScriptProvider(cfg.openrouter_key, model=cfg.script_model)
        script = provider.generate(args.prompt, assets, float(args.duration))
    except ProviderUnavailable as e:
        print(f"clemtock script: {e}", file=sys.stderr)
        print("  (run `source scripts/load-env.sh` first)", file=sys.stderr)
        return 2

    # merge uploaded assets the model may have omitted, so the renderer can resolve them
    script.setdefault("assets", {})
    for aid, desc in assets.items():
        script["assets"].setdefault(aid, desc)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(script, indent=2))
    n = len(script.get("scenes", []))
    print(f"clemtock script: wrote {out} — {n} scenes, "
          f"{script.get('duration', '?')}s, {len(script['assets'])} assets")
    return 0


def _todo(name: str, detail: str) -> int:
    print(f"clemtock {name}: NOT YET IMPLEMENTED (Phase scaffold).\n  {detail}",
          file=sys.stderr)
    return 3


def cmd_assets(args: argparse.Namespace) -> int:
    """Generate source:gen stills + extract posters for uploaded video (Phase 2)."""
    from .pipeline import assets as assets_stage

    script = Path(args.script)
    if not script.exists():
        print(f"clemtock assets: ad-script not found: {script}", file=sys.stderr)
        return 2
    cfg = Config.from_env()
    summary = assets_stage.run(script, _REPO, cfg)
    print(f"clemtock assets: generated={summary['generated']} "
          f"posters={summary['posters']} skipped={len(summary['skipped'])}")
    if summary["failed"]:
        for aid, why in summary["failed"]:
            print(f"  FAILED {aid}: {why}", file=sys.stderr)
        return 1
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    return _todo("render",
                 "Open web/clemtock-renderer.dc.html (it reads web/ad-script.json) to "
                 "preview; headless frame capture lands here. See DESIGN.md Phase 3.")


def cmd_export(args: argparse.Namespace) -> int:
    """Headless render of an ad-script to an MP4 on disk (Phase 4)."""
    script = Path(args.script)
    if not script.exists():
        print(f"clemtock export: ad-script not found: {script}", file=sys.stderr)
        return 2
    cmd = ["node", str(_REPO / "web" / "render-headless.mjs"),
           "--script", str(script), "--out", str(args.out)]
    return subprocess.call(cmd)


def cmd_video(args: argparse.Namespace) -> int:
    """kie.ai image-to-video (Phase 5). Seeds from an input image + prompt."""
    from .providers.kie_video import KieVideoProvider
    cfg = Config.from_env()
    model = args.model or cfg.kie_video_model
    try:
        prov = KieVideoProvider(cfg.kie_key, model=model)
        print(f"clemtock video: submitting to kie ({model}); this takes ~1-5 min…",
              file=sys.stderr)
        out = prov.generate(args.prompt, Path(args.out), seconds=float(args.seconds),
                            seed_image=Path(args.image))
    except ProviderUnavailable as e:
        print(f"clemtock video: {e}", file=sys.stderr)
        return 2
    print(f"clemtock video: wrote {out} ({out.stat().st_size} bytes)")
    return 0


def cmd_avatar(args: argparse.Namespace) -> int:
    """HeyGen talking-avatar segment (Phase 5)."""
    from .providers.heygen import HeyGenAvatarProvider
    cfg = Config.from_env()
    try:
        prov = HeyGenAvatarProvider(cfg.heygen_key, avatar_id=cfg.heygen_avatar_id,
                                    voice_id=cfg.heygen_voice_id)
        print("clemtock avatar: submitting to HeyGen; this takes a few minutes…", file=sys.stderr)
        out = prov.generate(args.text, Path(args.out),
                           avatar_id=args.avatar_id, voice_id=args.voice_id)
    except ProviderUnavailable as e:
        print(f"clemtock avatar: {e}", file=sys.stderr)
        return 2
    print(f"clemtock avatar: wrote {out} ({out.stat().st_size} bytes)")
    return 0


def cmd_compose(args: argparse.Namespace) -> int:
    """Phase 6 — composite real clips + audio under the graphics layer (or plain export)."""
    from .pipeline import compose
    script = Path(args.script)
    if not script.exists():
        print(f"clemtock compose: ad-script not found: {script}", file=sys.stderr)
        return 2
    try:
        summary = compose.run(script, _REPO, _repo_path(args.out), fps=int(args.fps))
    except subprocess.CalledProcessError as e:
        print(f"clemtock compose: ffmpeg/render failed (exit {e.returncode})", file=sys.stderr)
        return 1
    print(f"clemtock compose: {summary['mode']} — {summary.get('clips',0)} clip(s), "
          f"{summary.get('audio_tracks',0)} audio track(s) -> {summary['out']}")
    return 0


def cmd_patch(args: argparse.Namespace) -> int:
    """Surgically edit ONE scene of an ad-script (no re-authoring), then optionally recompose."""
    from .pipeline import patch
    script = Path(args.script)
    copy: dict[str, str] = {}
    for item in (args.copy or []):
        if "=" not in item:
            print(f"clemtock patch: --copy expects KEY=VALUE, got {item!r}", file=sys.stderr)
            return 2
        k, v = item.split("=", 1)
        copy[k.strip()] = v
    try:
        summary = patch.apply(
            script, args.scene, _REPO,
            template=args.template, set_asset=args.set_asset, asset_kind=args.asset_kind,
            copy=copy or None, fit=args.fit, motion=args.motion,
            start=(float(args.start) if args.start is not None else None),
            end=(float(args.end) if args.end is not None else None))
    except patch.PatchError as e:
        print(f"clemtock patch: {e}", file=sys.stderr)
        return 2
    print(f"clemtock patch: scene {summary['scene']} — " + "; ".join(summary["changed"]))
    print(f"  backup: {summary['backup']}")
    if args.recompose:
        out = args.out or str(_REPO / "out" / "clemtock-ad.mp4")
        return cmd_compose(argparse.Namespace(script=str(script), out=out, fps=args.fps))
    print("  (run `clemtock compose` to re-render, or pass --recompose)")
    return 0


def cmd_music(args: argparse.Namespace) -> int:
    """Mux an optional royalty-free music bed into a rendered ad (looped/trimmed to length)."""
    from .pipeline import music
    video = _repo_path(args.video)
    try:
        track = music.resolve_track(_REPO, args.track)
        out = _repo_path(args.out) if args.out else _REPO / "out" / (video.stem + "-scored.mp4")
        summary = music.score(video, track, out, gain_db=float(args.gain), duck=args.duck)
    except music.MusicError as e:
        print(f"clemtock music: {e}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as e:
        print(f"clemtock music: ffmpeg failed (exit {e.returncode})", file=sys.stderr)
        return 1
    print(f"clemtock music: scored with {summary['track']}"
          f"{' (ducked under existing audio)' if summary['duck'] else ''} -> {summary['out']}")
    return 0


def cmd_caption(args: argparse.Namespace) -> int:
    """Draft a platform-tuned social caption + curated hashtags (OpenRouter)."""
    from . import captions
    cfg = Config.from_env()
    brief = args.brief or ""
    if not brief and args.script and Path(args.script).exists():
        try:  # fall back to a brief stored on the ad-script, if any
            doc = json.loads(Path(args.script).read_text())
            brief = doc.get("brief") or doc.get("prompt") or ""
        except Exception:
            pass
    try:
        res = captions.draft(_REPO, brief, args.platform, cfg.openrouter_key,
                             preset=args.preset, extra_tags=args.tags, model=cfg.script_model)
    except ProviderUnavailable as e:
        print(f"clemtock caption: {e}", file=sys.stderr)
        return 2
    print(res["text"])  # full caption (body + hashtags) to stdout for piping
    return 0


# platform aliases -> the names Post Bridge reports for connected accounts
_PLATFORM_ALIAS = {"x": "twitter", "twitter/x": "twitter"}


def cmd_accounts(args: argparse.Namespace) -> int:
    """List connected social accounts (Post Bridge)."""
    from .providers.postbridge import PostBridgeProvider
    cfg = Config.from_env()
    try:
        for a in PostBridgeProvider(cfg.postbridge_key).accounts():
            print(f"  {a.get('id')}  {a.get('platform'):<10} {a.get('username') or a.get('name')}")
    except ProviderUnavailable as e:
        print(f"clemtock accounts: {e}", file=sys.stderr)
        return 2
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    """Publish a rendered MP4 to social accounts. Dry-run unless --execute (irreversible)."""
    from .providers.postbridge import PostBridgeProvider
    cfg = Config.from_env()
    video = _repo_path(args.video)
    if not video.exists():
        print(f"clemtock publish: not found: {video}", file=sys.stderr)
        return 2
    names = [_PLATFORM_ALIAS.get(s.strip().lower(), s.strip().lower())
             for s in (args.to or "").split(",") if s.strip()]
    music_name = getattr(args, "music", None)
    if music_name:
        # TikTok requires sound be added in-app; never bake a bed onto a TikTok upload
        if "tiktok" in names:
            print("clemtock publish: TikTok can't carry a baked-in music bed — publish TikTok "
                  "separately without --music (add sound in the app).", file=sys.stderr)
            return 2
        from .pipeline import music as music_mod
        try:
            track = music_mod.resolve_track(_REPO, music_name)
            scored = _REPO / "out" / (video.stem + "-scored.mp4")
            music_mod.score(video, track, scored, gain_db=float(getattr(args, "gain", -3.0)),
                            duck=getattr(args, "duck", False))
            print(f"clemtock publish: scored with {track.stem} -> {scored.name}")
            video = scored
        except music_mod.MusicError as e:
            print(f"clemtock publish: {e}", file=sys.stderr)
            return 2
        except subprocess.CalledProcessError as e:
            print(f"clemtock publish: music mux failed (exit {e.returncode})", file=sys.stderr)
            return 1
    try:
        prov = PostBridgeProvider(cfg.postbridge_key)
        ids = prov.resolve(names)
        if not ids:
            print(f"clemtock publish: no accounts matched {names}; try `clemtock accounts`", file=sys.stderr)
            return 1
        if not args.execute:
            print(f"clemtock publish [DRY-RUN]: would post {video.name} "
                  f"({video.stat().st_size//1024} KB) to accounts {ids}\n"
                  f"  caption: {args.caption!r}\n  re-run with --execute to publish.")
            return 0
        res = prov.publish(video, args.caption, ids)
        print(f"clemtock publish: posted {video.name} to {res['accounts']} (media {res['media_id']})")
    except ProviderUnavailable as e:
        print(f"clemtock publish: {e}", file=sys.stderr)
        return 2
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """End-to-end: (optional script) -> assets -> compose -> final MP4."""
    script = Path(args.script)
    if args.prompt:
        rc = cmd_script(argparse.Namespace(
            prompt=args.prompt, assets=args.assets, duration=args.duration, out=str(script)))
        if rc != 0:
            return rc
    if not script.exists():
        print(f"clemtock run: no ad-script at {script} (pass --prompt to generate one)",
              file=sys.stderr)
        return 2
    rc = cmd_assets(argparse.Namespace(script=str(script)))
    if rc not in (0,):
        print("clemtock run: assets step had failures; continuing to compose", file=sys.stderr)
    return cmd_compose(argparse.Namespace(script=str(script), out=args.out, fps=args.fps))


def cmd_vault(args: argparse.Namespace) -> int:
    """Encrypted secret store (init/set/get/list/rm/import-env)."""
    from .vault import Vault, VaultError, DEFAULT_VAULT
    try:
        if args.vault_cmd == "init":
            v = Vault.init()
            print(f"clemtock vault: ready at {v.path} (passphrase: "
                  f"{'env' if os.environ.get('CLEMTOCK_VAULT_PASSPHRASE') else vault_mod.DEFAULT_KEYFILE})")
            return 0
        if args.vault_cmd == "set":
            value = sys.stdin.read().strip()  # value via stdin only — never argv/logs
            if not value:
                print("clemtock vault set: no value on stdin", file=sys.stderr)
                return 2
            v = Vault().load() if DEFAULT_VAULT.exists() else Vault.init()
            v.set(args.name, value)
            v.save()
            print(f"clemtock vault: stored {args.name} ({len(value)} chars)")
            return 0
        if args.vault_cmd == "get":
            val = Vault().load().get(args.name)
            if val is None:
                print(f"clemtock vault: {args.name} not set", file=sys.stderr)
                return 1
            sys.stdout.write(val)  # raw, for piping; no newline
            return 0
        if args.vault_cmd == "list":
            for n in Vault().load().names():
                print(n)
            return 0
        if args.vault_cmd == "rm":
            v = Vault().load()
            ok = v.delete(args.name)
            v.save()
            print(f"clemtock vault: {'removed ' + args.name if ok else args.name + ' not present'}")
            return 0
        if args.vault_cmd == "import-env":
            v = Vault().load() if DEFAULT_VAULT.exists() else Vault.init()
            count = 0
            for line in Path(args.file).read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, val = line.split("=", 1)
                val = val.strip().strip('"').strip("'")
                if val:
                    v.set(k.strip(), val)
                    count += 1
            v.save()
            print(f"clemtock vault: imported {count} secrets from {args.file}")
            return 0
    except VaultError as e:
        print(f"clemtock vault: {e}", file=sys.stderr)
        return 2
    return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="clemtock", description="prompt-driven ad generator")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("probe", help="auth-only provider health check")
    sp.set_defaults(func=cmd_probe)

    sc = sub.add_parser("script", help="brief -> ad-script.json (OpenRouter)")
    sc.add_argument("--prompt", required=True, help="the ad brief")
    sc.add_argument("--assets", help="directory of uploaded media to reference")
    sc.add_argument("--duration", default=15, help="target length in seconds")
    sc.add_argument("--out", default=str(_REPO / "web" / "ad-script.json"))
    sc.set_defaults(func=cmd_script)

    asset = sub.add_parser("assets", help="AI-generate stills + extract video posters")
    asset.add_argument("--script", default=str(_REPO / "web" / "ad-script.json"))
    asset.set_defaults(func=cmd_assets)

    ex = sub.add_parser("export", help="headless render ad-script -> MP4 on disk")
    ex.add_argument("--script", default=str(_REPO / "web" / "ad-script.json"))
    ex.add_argument("--out", default=str(_REPO / "out" / "clemtock-ad.mp4"))
    ex.set_defaults(func=cmd_export)

    vlt = sub.add_parser("vault", help="encrypted secret store")
    vsub = vlt.add_subparsers(dest="vault_cmd", required=True)
    vsub.add_parser("init", help="create the vault + passphrase")
    vset = vsub.add_parser("set", help="store a secret (value read from stdin)")
    vset.add_argument("name")
    vget = vsub.add_parser("get", help="print a secret (for piping)")
    vget.add_argument("name")
    vsub.add_parser("list", help="list secret names")
    vrm = vsub.add_parser("rm", help="remove a secret")
    vrm.add_argument("name")
    vimp = vsub.add_parser("import-env", help="bulk-import KEY=VALUE lines from a file")
    vimp.add_argument("file")
    vlt.set_defaults(func=cmd_vault)

    vid = sub.add_parser("video", help="kie.ai image-to-video (seed image + prompt)")
    vid.add_argument("--image", required=True, help="seed image path")
    vid.add_argument("--prompt", required=True)
    vid.add_argument("--model", default=None, help="kie video model (default kling-2.6/image-to-video)")
    vid.add_argument("--seconds", default=5)
    vid.add_argument("--out", default=str(_REPO / "out" / "clem-clip.mp4"))
    vid.set_defaults(func=cmd_video)

    av = sub.add_parser("avatar", help="HeyGen talking-avatar segment")
    av.add_argument("--text", required=True, help="what the avatar says")
    av.add_argument("--avatar-id", dest="avatar_id", default=None)
    av.add_argument("--voice-id", dest="voice_id", default=None)
    av.add_argument("--out", default=str(_REPO / "out" / "clem-avatar.mp4"))
    av.set_defaults(func=cmd_avatar)

    comp = sub.add_parser("compose", help="composite real clips + audio under graphics (Phase 6)")
    comp.add_argument("--script", default=str(_REPO / "web" / "ad-script.json"))
    comp.add_argument("--out", default=str(_REPO / "out" / "clemtock-final.mp4"))
    comp.add_argument("--fps", default=30)
    comp.set_defaults(func=cmd_compose)

    pat = sub.add_parser("patch", help="edit ONE scene of an ad-script without re-authoring")
    pat.add_argument("--scene", required=True, help="id of the scene to edit")
    pat.add_argument("--script", default=str(_REPO / "web" / "ad-script.json"))
    pat.add_argument("--template", default=None, help="title|photo|video|terminal|split|cta")
    pat.add_argument("--set-asset", dest="set_asset", default=None,
                     help="path to a local clip/still (ingested) or an existing asset id")
    pat.add_argument("--asset-kind", dest="asset_kind", default=None,
                     choices=["video", "image"], help="override kind for an ingested file")
    pat.add_argument("--copy", action="append", metavar="KEY=VALUE",
                     help="set a copy field (kicker/headline/sub/cta); repeatable; empty clears")
    pat.add_argument("--fit", default=None, choices=["cover", "contain"],
                     help="clip fit: cover-crop or contain (letterbox on ink)")
    pat.add_argument("--motion", default=None, help="scene motion type")
    pat.add_argument("--start", default=None, help="retime scene start (seconds)")
    pat.add_argument("--end", default=None, help="retime scene end (seconds)")
    pat.add_argument("--recompose", action="store_true", help="re-render right after patching")
    pat.add_argument("--out", default=None, help="output MP4 when --recompose")
    pat.add_argument("--fps", default=30)
    pat.set_defaults(func=cmd_patch)

    run = sub.add_parser("run", help="end-to-end: [script] -> assets -> compose")
    run.add_argument("--prompt", default=None, help="brief; if given, generates the ad-script first")
    run.add_argument("--assets", default=None, help="uploads dir for the script step")
    run.add_argument("--duration", default=15)
    run.add_argument("--script", default=str(_REPO / "web" / "ad-script.json"))
    run.add_argument("--out", default=str(_REPO / "out" / "clemtock-final.mp4"))
    run.add_argument("--fps", default=30)
    run.set_defaults(func=cmd_run)

    acc = sub.add_parser("accounts", help="list connected social accounts")
    acc.set_defaults(func=cmd_accounts)

    cap = sub.add_parser("caption", help="draft a platform-tuned social caption (OpenRouter)")
    cap.add_argument("--brief", default="", help="what the ad/product is about")
    cap.add_argument("--platform", default="tiktok",
                     help="tiktok/instagram/youtube/x/lemon8/threads/facebook")
    cap.add_argument("--preset", default=None, help="hashtag preset (see web/hashtag-presets.json)")
    cap.add_argument("--tags", default=None, help="extra hashtags (space/comma separated)")
    cap.add_argument("--script", default=str(_REPO / "web" / "ad-script.json"),
                     help="fallback brief source if --brief is omitted")
    cap.set_defaults(func=cmd_caption)

    mus = sub.add_parser("music", help="mux an optional royalty-free music bed into an ad")
    mus.add_argument("--video", required=True)
    mus.add_argument("--track", required=True, help="track id (from assets/music) or a path")
    mus.add_argument("--gain", default=-3.0, help="bed gain in dB (default -3)")
    mus.add_argument("--duck", action="store_true", help="keep existing audio, tuck music under it")
    mus.add_argument("--out", default=None, help="output MP4 (default out/<name>-scored.mp4)")
    mus.set_defaults(func=cmd_music)

    pub = sub.add_parser("publish", help="publish an MP4 to socials (dry-run unless --execute)")
    pub.add_argument("--video", required=True)
    pub.add_argument("--caption", default="")
    pub.add_argument("--to", default="", help="comma list of platforms or account ids "
                     "(tiktok,youtube,facebook,instagram,x,lemon8,threads)")
    pub.add_argument("--music", default=None, help="optional music track id to bake in "
                     "(non-TikTok only); see `clemtock music`")
    pub.add_argument("--gain", default=-3.0, help="music bed gain in dB when --music is set")
    pub.add_argument("--duck", action="store_true", help="duck music under existing audio")
    pub.add_argument("--execute", action="store_true", help="actually post (irreversible)")
    pub.set_defaults(func=cmd_publish)

    rnd = sub.add_parser("render", help="(alias of export) DOM render -> MP4")
    rnd.add_argument("--script", default=str(_REPO / "web" / "ad-script.json"))
    rnd.add_argument("--out", default=str(_REPO / "out" / "clemtock-ad.mp4"))
    rnd.set_defaults(func=cmd_export)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # transparently unlock vault secrets into env for everything except vault admin itself
    if args.command != "vault":
        vault_mod.apply_to_env()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
