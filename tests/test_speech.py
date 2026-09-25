"""Domain-to-speech rewriting.

The numbers behind the chosen form are in clemtock/speech.py: measured hesitation on
six phrasings, synthesised with the real cloned voice.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from clemtock.speech import speak_domain, speakable  # noqa: E402


class SpeakDomain(unittest.TestCase):
    def test_hyphenated_host_becomes_camelcase(self):
        # The whole point: measured 0 internal pauses vs 0.295s for the spaced form.
        self.assertEqual(speak_domain("appearance-unlimited.com"),
                         "AppearanceUnlimited dot com")

    def test_plain_host(self):
        self.assertEqual(speak_domain("maddhatchery.com"), "Maddhatchery dot com")

    def test_subdomains_each_get_a_dot(self):
        self.assertEqual(speak_domain("earlbiggers.etsy.com"),
                         "Earlbiggers dot Etsy dot com")

    def test_letterwise_tlds(self):
        self.assertEqual(speak_domain("foo.io"), "Foo dot I O")
        self.assertEqual(speak_domain("foo.ai"), "Foo dot A I")

    def test_unknown_tld_passes_through(self):
        self.assertEqual(speak_domain("foo.zzz"), "Foo dot zzz")


class Speakable(unittest.TestCase):
    def test_rewrites_in_context_and_keeps_punctuation(self):
        self.assertEqual(
            speakable("Head to appearance-unlimited.com. Start your next project."),
            "Head to AppearanceUnlimited dot com. Start your next project.")

    def test_strips_scheme_www_and_path(self):
        self.assertEqual(speakable("Visit https://www.appearance-unlimited.com/services now"),
                         "Visit AppearanceUnlimited dot com now")

    def test_leaves_email_addresses_alone(self):
        # Regression: the pattern used to match at "unlimited" inside the address,
        # because a preceding '-' satisfied the lookbehind.
        for addr in ("hello@appearance-unlimited.com", "a@b.com", "x.y@maddhatchery.com"):
            self.assertIn("@", speakable(f"email {addr} today"))
            self.assertNotIn(" dot ", speakable(f"email {addr} today"))

    def test_text_without_urls_is_untouched(self):
        t = "Cold makes men. Built for the long winter."
        self.assertEqual(speakable(t), t)

    def test_idempotent(self):
        once = speakable("go to appearance-unlimited.com")
        self.assertEqual(speakable(once), once)

    def test_empty(self):
        self.assertEqual(speakable(""), "")


if __name__ == "__main__":
    unittest.main()
