"""Tests for the cartoon-avatar chain's pure logic.

Deliberately no network, no model weights, no ffmpeg: these cover the parts that
decide *what* gets rendered, which is where the silent-wrongness lives. The
expensive parts (Chatterbox synthesis, rhubarb recognition, ffmpeg muxing) are
verified by running them, not by unit tests.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from clemtock.providers import rhubarb_lipsync as rl          # noqa: E402
from clemtock.providers.base import ProviderUnavailable        # noqa: E402
from clemtock.providers.ollama_script import _repair           # noqa: E402


def _sprites(tmp: Path, letters: str) -> dict:
    for ch in letters:
        (tmp / f"{ch}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return rl.load_sprites(tmp)


class SpriteFallback(unittest.TestCase):
    def test_exact_shape_wins(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            sp = _sprites(tmp, "ABCDEF")
            tl = rl.MouthTimeline(cues=[], duration=0)
            self.assertEqual(tl.sprite_for("D", sp).stem, "D")

    def test_missing_shape_degrades_to_nearest(self):
        # A six-image set is the documented minimum; G/H/X must still render.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            sp = _sprites(tmp, "ABCDEF")
            tl = rl.MouthTimeline(cues=[], duration=0)
            self.assertEqual(tl.sprite_for("G", sp).stem, "B")   # G -> B
            self.assertEqual(tl.sprite_for("H", sp).stem, "C")   # H -> C
            self.assertEqual(tl.sprite_for("X", sp).stem, "A")   # X -> A

    def test_degrades_all_the_way_to_A(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            sp = _sprites(tmp, "A")
            tl = rl.MouthTimeline(cues=[], duration=0)
            for shape in "BCDEFGHX":
                self.assertEqual(tl.sprite_for(shape, sp).stem, "A")

    def test_empty_sprite_set_is_an_error_not_a_crash(self):
        tl = rl.MouthTimeline(cues=[], duration=0)
        with self.assertRaises(ProviderUnavailable):
            tl.sprite_for("A", {})

    def test_load_sprites_ignores_junk_and_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "a.png").write_bytes(b"x")
            (tmp / "C.PNG").write_bytes(b"x")
            (tmp / "notes.txt").write_text("ignore me")
            (tmp / "Z.png").write_bytes(b"x")       # not a mouth shape
            sp = rl.load_sprites(tmp)
            self.assertEqual(set(sp), {"A", "C"})

    def test_empty_directory_names_the_problem(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ProviderUnavailable):
                rl.load_sprites(Path(d))


class MouthCues(unittest.TestCase):
    def test_duration_never_negative(self):
        self.assertEqual(rl.MouthCue(1.0, 0.5, "A").duration, 0.0)

    def test_shapes_used(self):
        tl = rl.MouthTimeline(
            cues=[rl.MouthCue(0, 1, "A"), rl.MouthCue(1, 2, "B"), rl.MouthCue(2, 3, "A")],
            duration=3)
        self.assertEqual(tl.shapes_used(), {"A", "B"})


class WeakModelRepair(unittest.TestCase):
    """Shapes qwen3:8b actually emitted on 2026-09-23 that would break the renderer."""

    def test_assets_list_becomes_dict_keyed_by_id(self):
        out = _repair({"assets": [{"id": "hero", "kind": "image", "src": "a.png"}]})
        self.assertEqual(out["assets"], {"hero": {"kind": "image", "src": "a.png"}})

    def test_assets_list_of_strings_becomes_gen_entries(self):
        out = _repair({"assets": ["a catfish"]})
        self.assertEqual(out["assets"]["a catfish"]["source"], "gen")

    def test_non_dict_assets_becomes_empty_dict(self):
        self.assertEqual(_repair({"assets": None})["assets"], {})
        self.assertEqual(_repair({})["assets"], {})

    def test_bare_string_copy_becomes_headline(self):
        out = _repair({"scenes": [{"copy": "Gone Fishin"}]})
        self.assertEqual(out["scenes"][0]["copy"], {"headline": "Gone Fishin"})

    def test_singular_asset_keys_become_the_assets_array(self):
        for wrong in ("asset", "assetId", "image"):
            out = _repair({"scenes": [{wrong: "hero"}]})
            self.assertEqual(out["scenes"][0]["assets"], ["hero"])
            self.assertNotIn(wrong, out["scenes"][0])

    def test_existing_assets_array_wins_over_singular_key(self):
        out = _repair({"scenes": [{"assets": ["a"], "image": "b"}]})
        self.assertEqual(out["scenes"][0]["assets"], ["a"])
        self.assertNotIn("image", out["scenes"][0])

    def test_repaired_script_survives_the_cli_merge_step(self):
        # cli.cmd_script does exactly this; it used to raise on a list.
        script = _repair({"assets": [{"id": "hero", "kind": "image"}]})
        script.setdefault("assets", {})
        script["assets"].setdefault("extra", {"kind": "image"})
        self.assertEqual(set(script["assets"]), {"hero", "extra"})


if __name__ == "__main__":
    unittest.main()
