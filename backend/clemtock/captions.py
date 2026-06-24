"""Platform-tuned social caption drafting (Phase 7 publish helper).

Given a short brief about the ad/product and a target platform, ask OpenRouter to write
a caption in that platform's voice + length budget, then append a curated hashtag set.
The MODEL writes the copy; HASHTAGS come from operator-curated presets (web/
hashtag-presets.json) so tags stay controlled rather than hallucinated. Stdlib HTTP.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from .providers.base import ProviderUnavailable

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

# per-platform voice + length budget (chars refer to the caption BODY, before hashtags)
PLATFORM_SPECS = {
    "tiktok":    {"max": 150, "voice": "punchy hook-first, 1-2 short lines, casual, at most one emoji"},
    "instagram": {"max": 300, "voice": "engaging, 1-3 lines, a little personality, emoji ok"},
    "youtube":   {"max": 400, "voice": "a strong title-like first line, then a 1-2 sentence description"},
    "x":         {"max": 200, "voice": "tight single thought, under 200 chars so tags fit in 280"},
    "lemon8":    {"max": 400, "voice": "discovery/lifestyle tips framing, friendly and concrete"},
    "threads":   {"max": 300, "voice": "conversational, a touch opinionated, no hard sell"},
    "facebook":  {"max": 300, "voice": "1-2 clear sentences with a plain call-to-action"},
}
DEFAULT_PLATFORM = "tiktok"

_FALLBACK_PRESETS = {
    "local81-oss": ["#local81", "#opensource", "#oss", "#ai", "#portright"],
    "oss-devtools": ["#opensource", "#oss", "#devtools", "#ai", "#coding"],
    "devops-homelab": ["#devops", "#sysadmin", "#homelab", "#selfhosted", "#linux"],
}
# note: TikTok/IG break a tag at the first non-letter, so brand tags are stored letters-only
# (e.g. #portright, not #portright.io which would tag "#portright" + literal ".io").


def load_presets(repo: Path) -> dict:
    f = repo / "web" / "hashtag-presets.json"
    try:
        data = json.loads(f.read_text())
        return data if isinstance(data, dict) and data else dict(_FALLBACK_PRESETS)
    except Exception:
        return dict(_FALLBACK_PRESETS)


def resolve_tags(repo: Path, preset: str | None, extra: str | None) -> list[str]:
    """Combine a named preset + free-form extra tags into a deduped, #-prefixed list."""
    tags: list[str] = []
    if preset:
        tags += load_presets(repo).get(preset, [])
    for t in (extra or "").replace(",", " ").split():
        t = t.strip()
        if t:
            tags.append(t if t.startswith("#") else "#" + t.lstrip("#"))
    seen, out = set(), []
    for t in tags:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out


def _system(platform: str) -> str:
    spec = PLATFORM_SPECS.get(platform, PLATFORM_SPECS[DEFAULT_PLATFORM])
    return (f"You write social captions. Write ONE {platform} caption for the product/ad in "
            f"the brief. Voice: {spec['voice']}. Keep the body under ~{spec['max']} characters. "
            "Do NOT include hashtags, @-mentions, quotation marks, or markdown — they are added "
            "separately. Output ONLY the caption text.")


def generate(brief: str, platform: str, api_key: str,
             model: str = "anthropic/claude-sonnet-4.5", timeout: int = 60) -> str:
    """Return a platform-tuned caption BODY (no hashtags). Raises ProviderUnavailable."""
    if not api_key:
        raise ProviderUnavailable("OPENROUTER_API_KEY is not set")
    if not (brief or "").strip():
        raise ProviderUnavailable("caption brief is empty")
    platform = platform if platform in PLATFORM_SPECS else DEFAULT_PLATFORM
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": _system(platform)},
            {"role": "user", "content": brief.strip()},
        ],
        "temperature": 0.8,
        "max_tokens": 400,
    }).encode("utf-8")
    req = urllib.request.Request(_ENDPOINT, data=body, method="POST", headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
        "X-Title": "clemtock"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ProviderUnavailable(
            f"OpenRouter HTTP {e.code}: {e.read().decode('utf-8','replace')[:300]}") from e
    except urllib.error.URLError as e:
        raise ProviderUnavailable(f"OpenRouter unreachable: {e.reason}") from e
    text = payload["choices"][0]["message"]["content"].strip().strip('"').strip()
    return text


def compose(body: str, tags: list[str]) -> str:
    """Caption body + a blank line + space-joined hashtags."""
    return body if not tags else f"{body}\n\n{' '.join(tags)}"


def draft(repo: Path, brief: str, platform: str, api_key: str, *,
          preset: str | None = None, extra_tags: str | None = None,
          model: str = "anthropic/claude-sonnet-4.5") -> dict:
    tags = resolve_tags(repo, preset, extra_tags)
    body = generate(brief, platform, api_key, model=model)
    return {"platform": platform, "body": body, "hashtags": tags,
            "text": compose(body, tags)}
