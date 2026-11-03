"""Unit tests for AssetResolver and semantic matching (Feature 021)."""
import json
import tempfile
from pathlib import Path
import unittest

from clipper.core.schemas import AssetPosition, AssetType, Scene
from clipper.video.asset_resolver import (
    AssetResolver,
    EasingProfile,
    ResolvedInsert,
    normalize_text,
)


class TestAssetResolver(unittest.TestCase):
    """Test suite for AssetResolver catalog loading, matching, and fallback."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.assets_dir = Path(self.temp_dir.name)

        # Create subdirectories and dummy files
        (self.assets_dir / "animations" / "business").mkdir(parents=True)
        (self.assets_dir / "animations" / "emotions").mkdir(parents=True)
        (self.assets_dir / "icons" / "general").mkdir(parents=True)
        (self.assets_dir / "sfx" / "whooshes").mkdir(parents=True)

        self.chart_file = self.assets_dir / "animations" / "business" / "chart_up.webm"
        self.chart_file.write_bytes(b"dummy_webm")

        self.alert_file = self.assets_dir / "animations" / "emotions" / "alert.webm"
        self.alert_file.write_bytes(b"dummy_alert")

        self.target_file = self.assets_dir / "icons" / "general" / "target.png"
        self.target_file.write_bytes(b"dummy_png")

        self.sfx_file = self.assets_dir / "sfx" / "whooshes" / "whoosh.wav"
        self.sfx_file.write_bytes(b"dummy_wav")

        # Create valid manifest.json
        manifest_data = {
            "version": "1.0.0",
            "assets": [
                {
                    "id": "chart_growth",
                    "file": "animations/business/chart_up.webm",
                    "type": "animated_video",
                    "tags": ["lucro", "crescimento", "investimento", "vendas"],
                    "default_position": "upper_third",
                    "default_sfx": "sfx/whooshes/whoosh.wav",
                    "max_duration": 3.0,
                },
                {
                    "id": "alert_warning",
                    "file": "animations/emotions/alert.webm",
                    "type": "animated_video",
                    "tags": ["alerta", "perigo", "cuidado"],
                    "default_position": "middle_third",
                    "default_sfx": None,
                    "max_duration": 2.0,
                },
                {
                    "id": "target_goal",
                    "file": "icons/general/target.png",
                    "type": "icon_with_card",
                    "tags": ["meta", "estrategia", "foco"],
                    "default_position": "lower_third",
                    "default_sfx": None,
                    "max_duration": 3.5,
                },
            ],
        }
        (self.assets_dir / "manifest.json").write_text(
            json.dumps(manifest_data), encoding="utf-8"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_normalize_text_removes_accents_and_punctuation(self):
        """Verify accent removal and lowercasing."""
        self.assertEqual(normalize_text("Atenção! Cuidado com Ações"), "atencao cuidado com acoes")
        self.assertEqual(normalize_text("  LUCRO  100%  "), "lucro 100")
        self.assertEqual(normalize_text(""), "")

    def test_load_manifest_success(self):
        """Verify manifest.json is loaded and validated correctly."""
        resolver = AssetResolver(assets_dir=str(self.assets_dir))
        self.assertIsNotNone(resolver.manifest)
        self.assertEqual(len(resolver.manifest.assets), 3)

    def test_load_manifest_missing_graceful_fallback(self):
        """Verify graceful fallback when manifest.json does not exist."""
        empty_dir = tempfile.TemporaryDirectory()
        try:
            resolver = AssetResolver(assets_dir=empty_dir.name)
            self.assertIsNone(resolver.manifest)
        finally:
            empty_dir.cleanup()

    def test_match_asset_exact_tag(self):
        """Verify matching asset by exact tag."""
        resolver = AssetResolver(assets_dir=str(self.assets_dir))
        match = resolver.match_asset("gráfico de crescimento e lucro")
        self.assertIsNotNone(match)
        self.assertEqual(match.id, "chart_growth")

    def test_match_asset_accent_insensitive(self):
        """Verify matching works even with accented words."""
        resolver = AssetResolver(assets_dir=str(self.assets_dir))
        match = resolver.match_asset("Estratégia e Ações")
        self.assertIsNotNone(match)
        self.assertIn(match.id, ("target_goal", "chart_growth"))

    def test_match_asset_missing_file_on_disk_skips(self):
        """Verify that if asset file is missing from disk, resolver does not return it."""
        self.chart_file.unlink()  # delete physical file
        resolver = AssetResolver(assets_dir=str(self.assets_dir))
        match = resolver.match_asset("lucro")
        self.assertIsNone(match)

    def test_match_asset_unknown_metaphor_returns_none(self):
        """Verify unknown metaphor returns None (for procedural fallback)."""
        resolver = AssetResolver(assets_dir=str(self.assets_dir))
        match = resolver.match_asset("arqueologia subaquática")
        self.assertIsNone(match)

    def test_resolve_insert_for_scene_with_matched_asset(self):
        """Verify resolved insert incorporates asset path, SFX, and safe bounds."""
        resolver = AssetResolver(assets_dir=str(self.assets_dir))
        scene = Scene(
            start_word="vamos",
            end_word="lucrar",
            visual_metaphor="investimento em acoes",
            animation_trigger="impact",
        )
        resolved = resolver.resolve_insert_for_scene(
            scene=scene,
            scene_index=0,
            scene_start_time=10.0,
            scene_duration=4.0,
        )
        self.assertIsNotNone(resolved)
        self.assertIsInstance(resolved, ResolvedInsert)
        self.assertEqual(resolved.asset_type, AssetType.ANIMATED_VIDEO)
        self.assertEqual(resolved.duration, 3.0)  # max_duration is 3.0
        self.assertEqual(resolved.start_time, 10.0)
        self.assertTrue(resolved.target_width % 2 == 0)
        self.assertTrue(resolved.target_height % 2 == 0)
        self.assertLessEqual(resolved.center_y_ratio, 0.70)
        self.assertIsNotNone(resolved.sfx_path)
        self.assertTrue(Path(resolved.sfx_path).exists())

    def test_resolve_insert_for_scene_fallback_procedural(self):
        """Verify procedural card fallback for unknown visual metaphor."""
        resolver = AssetResolver(assets_dir=str(self.assets_dir))
        scene = Scene(
            start_word="novo",
            end_word="conceito",
            visual_metaphor="paradigma quântico",
            animation_trigger="zoom_in",
        )
        resolved = resolver.resolve_insert_for_scene(
            scene=scene,
            scene_index=1,
            scene_start_time=5.0,
            scene_duration=2.0,
        )
        self.assertIsNotNone(resolved)
        self.assertIsNone(resolved.asset_path)
        self.assertEqual(resolved.asset_type, AssetType.ICON_WITH_CARD)
        self.assertEqual(resolved.label_text, "paradigma quântico")
        self.assertEqual(resolved.duration, 2.0)
        self.assertTrue(resolved.target_width % 2 == 0)
        self.assertTrue(resolved.target_height % 2 == 0)
        self.assertIsNone(resolved.sfx_path)

    def test_resolve_insert_for_empty_metaphor_returns_none(self):
        """Verify empty or '-' metaphor yields no insert."""
        resolver = AssetResolver(assets_dir=str(self.assets_dir))
        scene = Scene(
            start_word="um",
            end_word="dois",
            visual_metaphor="-",
            animation_trigger="cut_transition",
        )
        resolved = resolver.resolve_insert_for_scene(
            scene=scene,
            scene_index=0,
            scene_start_time=0.0,
            scene_duration=3.0,
        )
        self.assertIsNone(resolved)

    def test_resolve_insert_short_scene_skipped(self):
        """Verify scenes shorter than 0.6s are skipped to prevent visual clutter."""
        resolver = AssetResolver(assets_dir=str(self.assets_dir))
        scene = Scene(
            start_word="oi",
            end_word="tchau",
            visual_metaphor="lucro",
            animation_trigger="impact",
        )
        resolved = resolver.resolve_insert_for_scene(
            scene=scene,
            scene_index=0,
            scene_start_time=0.0,
            scene_duration=0.4,
        )
        self.assertIsNone(resolved)


if __name__ == "__main__":
    unittest.main()
