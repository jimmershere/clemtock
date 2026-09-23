"""Provider configuration, read from process environment.

No secret is stored by clemtock. Keys come from the process env, from the encrypted
vault, or from the plain ``.env`` files listed in ``CLEMTOCK_ENV_FILES`` (default:
``/app/portrender/.env`` → ``/app/clemtock/.env`` → ``/app/tee-empire/.env``) — the same
files portrender reads, so one key on the box serves both tools. ``load_env_files()`` is
called by the CLI and the server at startup; nothing is ever written back.
`available()` lets the CLI degrade honestly when a key is missing.

Everything runs on ONE host (quasimodo, /app/clemtock): ffmpeg, chromium, node and the
providers are all local — there is no remote render host any more.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILES = ["/app/portrender/.env", str(_REPO / ".env"), "/app/tee-empire/.env"]


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
            v = v[1:-1]
        else:
            v = v.split(" #", 1)[0].rstrip()
        if k:
            out[k] = v
    return out


def load_env_files(files: list[str] | None = None) -> dict[str, str]:
    """Populate os.environ from .env files without overriding what is already set.
    Returns {VAR: file} for what was loaded (never the values)."""
    files = files if files is not None else [
        f for f in os.environ.get("CLEMTOCK_ENV_FILES", ":".join(DEFAULT_ENV_FILES)).split(":") if f]
    loaded: dict[str, str] = {}
    for f in files:
        for k, v in _parse_env_file(Path(f)).items():
            if v and k not in os.environ:
                os.environ[k] = v
                loaded[k] = f
    return loaded


@dataclass(frozen=True)
class Config:
    # script brain (LLM -> ad-script.json), via OpenRouter
    openrouter_key: str = ""
    script_model: str = "anthropic/claude-sonnet-4.5"

    # local script brain — ollama on this host, no key, no per-call cost.
    # script_provider: "auto" (openrouter if keyed, else ollama) | "ollama" | "openrouter"
    script_provider: str = "auto"
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"

    # stills
    openai_key: str = ""            # OpenAI Images API (gpt-image-2 by default)
    openai_image_model: str = "gpt-image-2"
    image_model: str = "black-forest-labs/flux-schnell"  # OpenRouter fallback

    # video clips
    kie_key: str = ""
    kie_model: str = "flux-kontext-pro"             # image-edit model (KIEAI_MODEL)
    kie_video_model: str = "kling-2.6/image-to-video"  # image-to-video model

    # spokesperson + voice-over
    heygen_key: str = ""
    heygen_voice_id: str = ""
    heygen_avatar_id: str = ""

    # publishing
    postbridge_key: str = ""

    @classmethod
    def from_env(cls) -> "Config":
        e = os.environ.get
        return cls(
            openrouter_key=e("OPENROUTER_API_KEY", ""),
            script_model=e("CLEMTOCK_SCRIPT_MODEL", "anthropic/claude-sonnet-4.5"),
            script_provider=e("CLEMTOCK_SCRIPT_PROVIDER", "auto"),
            ollama_host=e("OLLAMA_HOST", "http://127.0.0.1:11434"),
            ollama_model=e("CLEMTOCK_OLLAMA_MODEL", "qwen3:8b"),
            openai_key=e("OPENAI_API_KEY", ""),
            openai_image_model=e("CLEMTOCK_IMAGE_MODEL", e("PORTRENDER_MODEL", "gpt-image-2")),
            image_model=e("OPENROUTER_IMAGE_MODEL", "black-forest-labs/flux-schnell"),
            kie_key=e("KIEAI_API_KEY", ""),
            kie_model=e("KIEAI_MODEL", "flux-kontext-pro"),
            kie_video_model=e("CLEMTOCK_KIE_VIDEO_MODEL", "kling-2.6/image-to-video"),
            heygen_key=e("HEYGEN_API_KEY", ""),
            heygen_voice_id=e("HEYGEN_VOICE_CLONE_ID", ""),
            heygen_avatar_id=e("HEYGEN_CARTOON_AVATAR_ID", ""),
            postbridge_key=e("POST_BRIDGE_API_KEY", ""),
        )

    def available(self) -> dict[str, bool]:
        """Which capabilities have a key present (not validated — see probe-providers.sh)."""
        return {
            # ollama needs no key, so "script" is also satisfied by a local daemon;
            # reachability is probed separately (scripts/probe-providers.sh).
            "script": bool(self.openrouter_key) or self.script_provider == "ollama",
            "image": bool(self.openai_key or self.openrouter_key),
            "video": bool(self.kie_key),
            "avatar": bool(self.heygen_key),
        }
