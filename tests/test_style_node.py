import json
import logging
import tempfile
import unittest
from pathlib import Path

from src.clipper.core.style_loader import (
    DEFAULT_VISUAL_IDENTITY,
    VisualIdentityConfig,
    load_visual_identity,
)
from src.clipper.runtime import config


class TestVisualIdentityConfig(unittest.TestCase):
    """Unit tests for VisualIdentityConfig Pydantic model validation and defaults."""

    def test_default_values_match_config(self):
        model = VisualIdentityConfig()
        dumped = model.model_dump()
        self.assertEqual(dumped["caption_color"], config.CAPTION_COLOR)
        self.assertEqual(dumped["caption_stroke_color"], config.CAPTION_STROKE_COLOR)
        self.assertEqual(dumped["caption_font_size"], config.CAPTION_FONT_SIZE)
        self.assertEqual(dumped["caption_stroke_width"], config.CAPTION_STROKE_WIDTH)
        self.assertEqual(dumped["caption_reference_width"], config.CAPTION_REFERENCE_WIDTH)
        self.assertEqual(dumped["caption_center_x_ratio"], config.CAPTION_CENTER_X_RATIO)
        self.assertEqual(dumped["caption_center_y_ratio"], config.CAPTION_CENTER_Y_RATIO)
        self.assertEqual(dumped["caption_safe_width_ratio"], config.CAPTION_SAFE_WIDTH_RATIO)
        self.assertEqual(dumped["caption_max_words"], config.CAPTION_MAX_WORDS)
        self.assertEqual(dumped["caption_max_gap"], config.CAPTION_MAX_GAP)
        self.assertEqual(dumped["caption_max_duration"], config.CAPTION_MAX_DURATION)

    def test_valid_hex_color(self):
        model = VisualIdentityConfig(
            caption_color="#AABBCC",
            caption_stroke_color="#123456",
        )
        self.assertEqual(model.caption_color, "#AABBCC")
        self.assertEqual(model.caption_stroke_color, "#123456")

    def test_invalid_hex_color_falls_back_to_defaults(self):
        with self.assertLogs("src.clipper.core.style_loader", level="WARNING") as cm:
            model = VisualIdentityConfig(
                caption_color="#ZZZZZZ",
                caption_stroke_color="invalid-color",
            )
        self.assertEqual(model.caption_color, config.CAPTION_COLOR)
        self.assertEqual(model.caption_stroke_color, config.CAPTION_STROKE_COLOR)
        self.assertTrue(any("Invalid hex color" in msg for msg in cm.output))

    def test_positive_integers_fallback(self):
        with self.assertLogs("src.clipper.core.style_loader", level="WARNING") as cm:
            model = VisualIdentityConfig(
                caption_font_size=0,
                caption_stroke_width=-5,
                caption_reference_width="not-an-int",
                caption_max_words=-1,
            )
        self.assertEqual(model.caption_font_size, config.CAPTION_FONT_SIZE)
        self.assertEqual(model.caption_stroke_width, config.CAPTION_STROKE_WIDTH)
        self.assertEqual(model.caption_reference_width, config.CAPTION_REFERENCE_WIDTH)
        self.assertEqual(model.caption_max_words, config.CAPTION_MAX_WORDS)
        self.assertTrue(any("Invalid positive integer" in msg for msg in cm.output))

    def test_positive_floats_fallback(self):
        with self.assertLogs("src.clipper.core.style_loader", level="WARNING") as cm:
            model = VisualIdentityConfig(
                caption_max_gap=0.0,
                caption_max_duration=-2.5,
            )
        self.assertEqual(model.caption_max_gap, config.CAPTION_MAX_GAP)
        self.assertEqual(model.caption_max_duration, config.CAPTION_MAX_DURATION)
        self.assertTrue(any("Invalid positive number" in msg for msg in cm.output))

    def test_ratios_fallback(self):
        with self.assertLogs("src.clipper.core.style_loader", level="WARNING") as cm:
            model = VisualIdentityConfig(
                caption_center_x_ratio=-0.1,
                caption_center_y_ratio=1.5,
                caption_safe_width_ratio="bad_ratio",
            )
        self.assertEqual(model.caption_center_x_ratio, config.CAPTION_CENTER_X_RATIO)
        self.assertEqual(model.caption_center_y_ratio, config.CAPTION_CENTER_Y_RATIO)
        self.assertEqual(model.caption_safe_width_ratio, config.CAPTION_SAFE_WIDTH_RATIO)
        self.assertTrue(any("Invalid ratio" in msg for msg in cm.output))

    def test_extra_fields_ignored(self):
        model = VisualIdentityConfig.model_validate(
            {"extra_field_1": "value", "caption_font_size": 95}
        )
        self.assertEqual(model.caption_font_size, 95)
        self.assertNotIn("extra_field_1", model.model_dump())


class TestLoadVisualIdentity(unittest.TestCase):
    """Scaffolded unit and integration tests for load_visual_identity."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_absent_file_returns_defaults_with_warning(self):
        nonexistent = self.temp_dir_path / "absent_estilo.json"
        with self.assertLogs("src.clipper.core.style_loader", level="WARNING") as cm:
            loaded = load_visual_identity(nonexistent)

        self.assertEqual(loaded, DEFAULT_VISUAL_IDENTITY)
        self.assertTrue(any("Style file not found" in msg for msg in cm.output))

    def test_load_corrupted_json_syntax_returns_defaults_with_warning(self):
        corrupt_file = self.temp_dir_path / "corrupt_estilo.json"
        corrupt_file.write_text("{ unclosed json: ", encoding="utf-8")

        with self.assertLogs("src.clipper.core.style_loader", level="WARNING") as cm:
            loaded = load_visual_identity(corrupt_file)

        self.assertEqual(loaded, DEFAULT_VISUAL_IDENTITY)
        self.assertTrue(any("Failed to parse style file" in msg for msg in cm.output))

    def test_load_non_dict_root_returns_defaults_with_warning(self):
        list_file = self.temp_dir_path / "list_estilo.json"
        list_file.write_text(json.dumps(["item1", "item2"]), encoding="utf-8")

        with self.assertLogs("src.clipper.core.style_loader", level="WARNING") as cm:
            loaded = load_visual_identity(list_file)

        self.assertEqual(loaded, DEFAULT_VISUAL_IDENTITY)
        self.assertTrue(any("root is not a dictionary" in msg for msg in cm.output))

    def test_load_nested_valid_file_flattens_and_applies_styles(self):
        valid_file = self.temp_dir_path / "valid_estilo.json"
        style_payload = {
            "palette": {
                "caption_color": "#FF5500",
                "caption_stroke_color": "#111111",
            },
            "typography": {
                "caption_font_size": 96,
                "caption_stroke_width": 10,
                "caption_reference_width": 1920,
            },
            "layout": {
                "caption_center_x_ratio": 0.48,
                "caption_center_y_ratio": 0.82,
                "caption_safe_width_ratio": 0.85,
            },
            "motion": {
                "caption_max_words": 4,
                "caption_max_gap": 0.4,
                "caption_max_duration": 1.8,
            },
        }
        valid_file.write_text(json.dumps(style_payload), encoding="utf-8")

        with self.assertLogs("src.clipper.core.style_loader", level="INFO") as cm:
            loaded = load_visual_identity(valid_file)

        self.assertEqual(loaded["caption_color"], "#FF5500")
        self.assertEqual(loaded["caption_stroke_color"], "#111111")
        self.assertEqual(loaded["caption_font_size"], 96)
        self.assertEqual(loaded["caption_stroke_width"], 10)
        self.assertEqual(loaded["caption_reference_width"], 1920)
        self.assertEqual(loaded["caption_center_x_ratio"], 0.48)
        self.assertEqual(loaded["caption_center_y_ratio"], 0.82)
        self.assertEqual(loaded["caption_safe_width_ratio"], 0.85)
        self.assertEqual(loaded["caption_max_words"], 4)
        self.assertEqual(loaded["caption_max_gap"], 0.4)
        self.assertEqual(loaded["caption_max_duration"], 1.8)
        self.assertTrue(any("Loaded visual identity from" in msg for msg in cm.output))

    def test_load_partial_file_uses_defaults_for_missing_keys_with_warning(self):
        partial_file = self.temp_dir_path / "partial_estilo.json"
        style_payload = {
            "palette": {
                "caption_color": "#336699",
            }
        }
        partial_file.write_text(json.dumps(style_payload), encoding="utf-8")

        with self.assertLogs("src.clipper.core.style_loader", level="WARNING") as cm:
            loaded = load_visual_identity(partial_file)

        self.assertEqual(loaded["caption_color"], "#336699")
        self.assertEqual(loaded["caption_stroke_color"], config.CAPTION_STROKE_COLOR)
        self.assertEqual(loaded["caption_font_size"], config.CAPTION_FONT_SIZE)
        self.assertTrue(any("Missing field 'caption_font_size'" in msg for msg in cm.output))

    def test_load_file_with_invalid_values_reverts_per_field(self):
        invalid_val_file = self.temp_dir_path / "invalid_vals.json"
        style_payload = {
            "palette": {
                "caption_color": "#INVALID",
                "caption_stroke_color": "#222222",
            },
            "typography": {
                "caption_font_size": -50,
            },
        }
        invalid_val_file.write_text(json.dumps(style_payload), encoding="utf-8")

        with self.assertLogs("src.clipper.core.style_loader", level="WARNING") as cm:
            loaded = load_visual_identity(invalid_val_file)

        self.assertEqual(loaded["caption_color"], config.CAPTION_COLOR)
        self.assertEqual(loaded["caption_stroke_color"], "#222222")
        self.assertEqual(loaded["caption_font_size"], config.CAPTION_FONT_SIZE)
        self.assertTrue(any("Invalid hex color" in msg for msg in cm.output))
        self.assertTrue(any("Invalid positive integer" in msg for msg in cm.output))

    def test_json_primitive_serializability(self):
        valid_file = self.temp_dir_path / "primitives.json"
        valid_file.write_text(json.dumps({"caption_color": "#123456"}), encoding="utf-8")

        with self.assertLogs("src.clipper.core.style_loader", level="WARNING"):
            loaded = load_visual_identity(valid_file)
        # Verify json dumps succeeds and all values are primitive
        serialized = json.dumps(loaded)
        deserialized = json.loads(serialized)
        self.assertEqual(loaded, deserialized)
        for k, v in loaded.items():
            self.assertIsInstance(v, (str, int, float, bool))


if __name__ == "__main__":
    unittest.main()
