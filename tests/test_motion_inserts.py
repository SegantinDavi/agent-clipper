"""Unit tests for motion inserts composition, easing curves, and SFX mixing (Feature 021)."""
import math
import os
import tempfile
from pathlib import Path
import unittest

import numpy as np
from PIL import Image

from clipper.core.schemas import AssetPosition, AssetType
from clipper.video.asset_resolver import EasingProfile, ResolvedInsert
from clipper.video.motion_engine import (
    create_animated_insert_clip,
    create_procedural_card_image,
    ease_out_back,
    mix_audio_sfx,
    sine_float,
    smooth_fade,
)


class TestMotionInserts(unittest.TestCase):
    """Test suite for motion insert math curves, clip generation, and audio mixing."""

    def test_ease_out_back_boundaries_and_overshoot(self):
        """Verify ease_out_back starts at 0, overshoots > 1.0, and ends at 1.0."""
        # At t=0, scale should be 0.0
        self.assertAlmostEqual(ease_out_back(0.0), 0.0, places=3)
        # At t=1, scale should be exactly 1.0
        self.assertAlmostEqual(ease_out_back(1.0), 1.0, places=3)
        # Around t=0.7, scale should overshoot > 1.0
        overshoot_val = ease_out_back(0.7)
        self.assertGreater(overshoot_val, 1.0)
        self.assertLessEqual(overshoot_val, 1.25)

    def test_sine_float_oscillation(self):
        """Verify sine float oscillates around 0 with given amplitude."""
        # At t=0, sin(0) = 0
        self.assertAlmostEqual(sine_float(0.0, amplitude=5.0, frequency=1.0), 0.0, places=3)
        # At t=0.25 (quarter period of 1Hz), sin(pi/2) = 1 -> amplitude
        self.assertAlmostEqual(sine_float(0.25, amplitude=5.0, frequency=1.0), 5.0, places=3)
        # At t=0.75, sin(3pi/2) = -1 -> -amplitude
        self.assertAlmostEqual(sine_float(0.75, amplitude=5.0, frequency=1.0), -5.0, places=3)

    def test_smooth_fade_exit(self):
        """Verify smooth fade stays 1.0 during active time and fades to 0.0 at total_duration."""
        total_dur = 3.0
        fade_dur = 0.5
        # During middle of clip, opacity is 1.0
        self.assertEqual(smooth_fade(1.5, total_dur, fade_dur), 1.0)
        # At total_dur - fade_dur / 2 (2.75s), opacity should be 0.5
        self.assertAlmostEqual(smooth_fade(2.75, total_dur, fade_dur), 0.5, places=2)
        # At end of clip (3.0s), opacity is 0.0
        self.assertAlmostEqual(smooth_fade(3.0, total_dur, fade_dur), 0.0, places=2)

    def test_create_procedural_card_image_even_dimensions(self):
        """Verify procedural card creates RGBA image with strictly even dimensions."""
        img = create_procedural_card_image(
            label_text="Crescimento de 200%",
            target_width=481,  # odd input
            target_height=121, # odd input
            visual_identity={"caption_color": "#FFCC00"},
        )
        self.assertIsInstance(img, Image.Image)
        self.assertEqual(img.mode, "RGBA")
        w, h = img.size
        self.assertTrue(w % 2 == 0, f"Width {w} must be even")
        self.assertTrue(h % 2 == 0, f"Height {h} must be even")

    def test_create_animated_insert_clip_procedural(self):
        """Verify create_animated_insert_clip builds a valid VideoClip with mask."""
        resolved = ResolvedInsert(
            scene_index=0,
            start_time=2.0,
            duration=2.5,
            asset_path=None,  # procedural
            asset_type=AssetType.ICON_WITH_CARD,
            label_text="Dica Estratégica",
            target_width=480,
            target_height=120,
            center_x_ratio=0.5,
            center_y_ratio=0.20,
            sfx_path=None,
        )
        clip = create_animated_insert_clip(
            resolved_insert=resolved,
            video_size=(1080, 1920),
            visual_identity=None,
        )
        self.assertIsNotNone(clip)
        self.assertEqual(clip.duration, 2.5)
        self.assertEqual(clip.start, 2.0)
        self.assertEqual(resolved.target_width % 2, 0)
        self.assertEqual(resolved.target_height % 2, 0)
        self.assertIsNotNone(clip.mask)
        clip.close()

    def test_mix_audio_sfx_graceful_with_no_sfx(self):
        """Verify mix_audio_sfx returns original audio intact when no SFX present."""
        from moviepy.editor import AudioClip
        # Create silent 5-second audio
        orig_audio = AudioClip(lambda t: [0.0, 0.0], duration=5.0)
        resolved_without_sfx = ResolvedInsert(
            scene_index=0,
            start_time=1.0,
            duration=2.0,
            asset_path=None,
            asset_type=AssetType.ICON_WITH_CARD,
            label_text="Test",
            target_width=480,
            target_height=120,
            sfx_path=None,
        )
        mixed = mix_audio_sfx(orig_audio, [resolved_without_sfx])
        self.assertEqual(mixed, orig_audio)
        orig_audio.close()

    def test_mix_audio_sfx_with_valid_sfx(self):
        """Verify mix_audio_sfx mixes SFX at correct start time."""
        import wave
        from moviepy.editor import AudioClip

        with tempfile.TemporaryDirectory() as tmp_dir:
            sfx_file = Path(tmp_dir) / "test_pop.wav"
            # Write a small valid WAV file (0.2s of 44100Hz audio)
            with wave.open(str(sfx_file), "w") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(44100)
                wav.writeframes(b"\x00\x00" * int(44100 * 0.2))

            orig_audio = AudioClip(lambda t: [0.0, 0.0], duration=5.0)
            resolved_with_sfx = ResolvedInsert(
                scene_index=0,
                start_time=1.5,
                duration=2.0,
                asset_path=None,
                asset_type=AssetType.ICON_WITH_CARD,
                label_text="Pop Test",
                target_width=480,
                target_height=120,
                sfx_path=str(sfx_file),
            )
            mixed = mix_audio_sfx(orig_audio, [resolved_with_sfx])
            self.assertIsNotNone(mixed)
            self.assertEqual(mixed.duration, 5.0)
            mixed.close()
            orig_audio.close()


if __name__ == "__main__":
    unittest.main()
