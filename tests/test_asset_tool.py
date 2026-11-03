"""Unit tests for the asset_tool CLI and media inspection (Feature 021)."""
import json
import tempfile
import wave
from pathlib import Path
import unittest

from PIL import Image

from clipper.tools.asset_tool import (
    inspect_media_file,
    sync_manifest,
    validate_assets_directory,
)


class TestAssetTool(unittest.TestCase):
    """Test suite for asset technical inspection and manifest synchronization."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.assets_dir = Path(self.temp_dir.name)
        (self.assets_dir / "icons").mkdir(parents=True)
        (self.assets_dir / "sfx").mkdir(parents=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_inspect_png_valid_rgba_even(self):
        """Verify inspection of valid RGBA PNG with even dimensions."""
        png_path = self.assets_dir / "icons" / "icon_valid.png"
        img = Image.new("RGBA", (128, 128), (255, 0, 0, 128))
        img.save(png_path)

        res = inspect_media_file(png_path)
        self.assertTrue(res.valid)
        self.assertTrue(res.has_alpha)
        self.assertEqual(res.dimensions, (128, 128))
        self.assertEqual(res.asset_type, "icon_with_card")
        self.assertEqual(len(res.errors), 0)

    def test_inspect_png_odd_dimensions_fails(self):
        """Verify inspection fails on odd dimensions."""
        png_path = self.assets_dir / "icons" / "icon_odd.png"
        img = Image.new("RGBA", (129, 128), (255, 0, 0, 128))
        img.save(png_path)

        res = inspect_media_file(png_path)
        self.assertFalse(res.valid)
        self.assertTrue(any("not even" in e for e in res.errors))

    def test_inspect_png_missing_alpha_fails(self):
        """Verify inspection fails on RGB mode without alpha."""
        png_path = self.assets_dir / "icons" / "icon_rgb.png"
        img = Image.new("RGB", (100, 100), (255, 0, 0))
        img.save(png_path)

        res = inspect_media_file(png_path)
        self.assertFalse(res.valid)
        self.assertTrue(any("lacks alpha" in e for e in res.errors))

    def test_inspect_wav_valid(self):
        """Verify inspection of valid WAV audio."""
        wav_path = self.assets_dir / "sfx" / "click.wav"
        with wave.open(str(wav_path), "w") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(44100)
            wav.writeframes(b"\x00\x00" * int(44100 * 0.3))

        res = inspect_media_file(wav_path)
        self.assertTrue(res.valid)
        self.assertEqual(res.asset_type, "sfx")
        self.assertIsNotNone(res.duration)
        self.assertAlmostEqual(res.duration, 0.3, places=2)

    def test_sync_manifest_discovers_new_files(self):
        """Verify sync_manifest detects untracked assets and appends to manifest.json."""
        # Create an icon and an audio file
        png_path = self.assets_dir / "icons" / "star_symbol.png"
        Image.new("RGBA", (64, 64), (0, 255, 0, 255)).save(png_path)

        added = sync_manifest(self.assets_dir)
        self.assertEqual(added, 1)

        manifest_path = self.assets_dir / "manifest.json"
        self.assertTrue(manifest_path.exists())

        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        registered_files = [item["file"] for item in data["assets"]]
        self.assertIn("icons/star_symbol.png", registered_files)

        # Running sync again should add 0 files
        added_again = sync_manifest(self.assets_dir)
        self.assertEqual(added_again, 0)

    def test_validate_assets_directory_empty_manifest(self):
        """Verify validate_assets_directory fails gracefully if manifest.json is missing."""
        valid, results = validate_assets_directory(self.assets_dir)
        self.assertFalse(valid)
        self.assertEqual(len(results), 0)


if __name__ == "__main__":
    unittest.main()
