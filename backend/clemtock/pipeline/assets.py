"""Asset preparation (Phase 2).

For each asset in an ad-script:
  - source:gen + kind:image  -> generate a still via ImageProvider, write to web/assets/.
  - source:upload + kind:video -> extract a poster keyframe via ffmpeg so a still is
    available (full motion compositing of real clips is the server-mux step, Phase 4+).

Generated assets are written under web/assets/ and the ad-script `src` fields are rewritten
to point at them, so the renderer resolves everything relative to web/. The updated
ad-script is written back in place.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from ..config import Config
from ..providers.base import ProviderUnavailable
from ..providers.openai_images import OpenAIImageProvider
from ..providers.kie_video import KieVideoProvider
from ..providers.heygen import HeyGenAvatarProvider


def _ffmpeg() -> str:
    home = os.environ.get("HOME", "")
    local = Path(home) / "bin" / "ffmpeg"
    return str(local) if local.exists() else (shutil.which("ffmpeg") or "ffmpeg")


def _poster(video_src: Path, out_png: Path, at: float = 0.5) -> bool:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    cmd = [_ffmpeg(), "-y", "-loglevel", "error", "-ss", str(at), "-i", str(video_src),
           "-frames:v", "1", str(out_png)]
    return subprocess.call(cmd) == 0


def run(script_path: Path, repo: Path, cfg: Config, aspect: str = "9:16") -> dict:
    doc = json.loads(script_path.read_text())
    assets_dir = repo / "web" / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    summary = {"generated": [], "posters": [], "skipped": [], "failed": []}

    img_provider = None  # lazy: only construct (and validate key) if needed

    for aid, a in (doc.get("assets") or {}).items():
        kind, source = a.get("kind"), a.get("source")

        if source == "gen" and kind == "avatar":
            out_mp4 = assets_dir / f"{aid}.mp4"
            if out_mp4.exists() and a.get("src"):
                summary["skipped"].append(aid); continue
            text = a.get("prompt") or a.get("text")
            if not text:
                summary["failed"].append((aid, "avatar needs prompt/text")); continue
            try:
                HeyGenAvatarProvider(cfg.heygen_key, avatar_id=cfg.heygen_avatar_id,
                                     voice_id=cfg.heygen_voice_id).generate(text, out_mp4)
                a["src"] = f"assets/{out_mp4.name}"
                summary["generated"].append(aid)
            except ProviderUnavailable as e:
                summary["failed"].append((aid, str(e)))

        elif source == "gen" and kind == "video":
            out_mp4 = assets_dir / f"{aid}.mp4"
            if out_mp4.exists() and a.get("src"):
                summary["skipped"].append(aid); continue
            # kie needs a public seed URL (local-image upload host is IP-gated); accept seed_url
            seed = a.get("seed_url")
            if not seed:
                summary["failed"].append((aid, "video needs seed_url (public image URL)")); continue
            try:
                KieVideoProvider(cfg.kie_key, model=cfg.kie_video_model).generate(
                    a.get("prompt", ""), out_mp4, seconds=float(a.get("duration", 5)), seed_image=seed)
                a["src"] = f"assets/{out_mp4.name}"
                summary["generated"].append(aid)
            except ProviderUnavailable as e:
                summary["failed"].append((aid, str(e)))

        elif source == "gen" and kind == "image":
            out_png = assets_dir / f"{aid}.png"
            if out_png.exists() and a.get("src"):
                summary["skipped"].append(aid)
                continue
            prompt = a.get("prompt")
            if not prompt:
                summary["failed"].append((aid, "no prompt"))
                continue
            try:
                if img_provider is None:
                    img_provider = OpenAIImageProvider(cfg.openai_key)
                img_provider.generate(prompt, out_png, size=a.get("aspect", aspect))
                a["src"] = f"assets/{out_png.name}"
                summary["generated"].append(aid)
            except ProviderUnavailable as e:
                summary["failed"].append((aid, str(e)))

        elif source == "upload" and kind == "video":
            src = a.get("src")
            if not src:
                summary["failed"].append((aid, "no src"))
                continue
            video = (repo / src) if not Path(src).is_absolute() else Path(src)
            poster = assets_dir / f"{aid}-poster.png"
            if _poster(video, poster):
                a["poster"] = f"assets/{poster.name}"
                summary["posters"].append(aid)
            else:
                summary["failed"].append((aid, "ffmpeg poster failed"))

        else:
            summary["skipped"].append(aid)

    script_path.write_text(json.dumps(doc, indent=2))
    return summary
