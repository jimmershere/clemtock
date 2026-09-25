"""Rewrite ad copy into something a TTS engine reads without stumbling.

Web addresses are where synthesised speech falls apart, and it matters commercially: an
ad that hesitates over the client's own domain sounds like the reader does not know the
brand. Appearance Unlimited is a weekly-ad account, so the domain gets spoken constantly.

Measured on Chatterbox with the cloned Michael voice, 2026-09-25 — internal silences over
80 ms inside the phrase "Go to <domain> today", leading/trailing silence excluded:

    AppearanceUnlimited dot com        0 gaps   0.000 s   <- chosen
    appearance-unlimited dot com       1 gap    0.271 s
    appearance dash unlimited dot com  2 gaps   0.275 s  (and 0.84 s longer)
    appearance unlimited dot com       2 gaps   0.295 s
    appearanceunlimited dot com        3 gaps   0.315 s
    appearance-unlimited.com           2 gaps   0.592 s   <- worst: never pass the raw URL

Two results worth keeping, because both are counter-intuitive:

1. **Saying "dash" out loud does not help.** It is the obvious fix and it measured no
   better than plain spaces, while adding nearly a second of runtime.
2. **CamelCase with no separator is what stops the pause.** The engine still pronounces
   both words — the camel version runs 3.34 s against 3.30 s for the spaced version, so
   it is not simply rushing — but it treats them as one token and does not breathe
   between them.

Lower-casing the join ("appearanceunlimited") is worse than CamelCase, so the capitals
are doing real work rather than being cosmetic.
"""
from __future__ import annotations

import re

# Spoken forms for the TLDs a small-business ad plausibly mentions. Anything not listed
# is read letter-by-letter-ish by the engine anyway, which is usually right for oddities.
TLD_SPOKEN = {
    "com": "com", "net": "net", "org": "org", "io": "I O", "co": "co",
    "us": "U S", "biz": "biz", "shop": "shop", "store": "store", "app": "app",
    "dev": "dev", "ai": "A I", "me": "me", "tv": "T V", "etsy": "etsy",
}

_URL = re.compile(
    r"""(?<![\w@.\-])              # never start mid-domain: a preceding - or . means we
                                   # are inside a host already (hello@appearance-unlimited
                                   # .com matched at "unlimited" until - was added here)
        (?:https?://)?             # optional scheme
        (?:www\.)?                 # optional www
        (?P<host>(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,})
        (?P<path>/[^\s,;]*)?       # optional path, dropped when spoken
        """,
    re.VERBOSE,
)


def _camel(label: str) -> str:
    """appearance-unlimited -> AppearanceUnlimited (the form that does not pause)."""
    parts = [p for p in re.split(r"[-_]+", label) if p]
    return "".join(p[:1].upper() + p[1:] for p in parts)


def speak_domain(host: str) -> str:
    """Spoken form of a bare host: appearance-unlimited.com -> AppearanceUnlimited dot com."""
    labels = host.split(".")
    tld = labels[-1].lower()
    spoken_tld = TLD_SPOKEN.get(tld, tld)
    body = [_camel(l) for l in labels[:-1]]
    return " dot ".join(body + [spoken_tld])


def speakable(text: str) -> str:
    """Rewrite every URL in `text` into its spoken form, leaving the rest alone.

    Idempotent in practice: the output contains no dots or schemes for the pattern to
    match a second time, so running it twice is harmless.
    """
    if not text:
        return text

    def sub(m: re.Match) -> str:
        host = m.group("host")
        # An email address slipped past the lookbehind? Leave it; speaking it is worse.
        if "@" in m.group(0):
            return m.group(0)
        return speak_domain(host)

    return _URL.sub(sub, text)
