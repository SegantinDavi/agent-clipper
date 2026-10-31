"""Unit, contract, and validation tests for Scene and CorteVideo models (Feature 016)."""
import json
from pathlib import Path
import unittest

import openai
from pydantic import ValidationError

from clipper.core.schemas import CorteVideo, CortesResponse, Scene


class TestSceneScriptingSchemaContract(unittest.TestCase):
    """T003: Contract test verifying openai.pydantic_function_tool schema generation."""

    def test_pydantic_function_tool_schema_matches_contract(self):
        """Verify openai.pydantic_function_tool schema matches corte_video_schema.json."""
        contract_path = (
            Path(__file__).resolve().parent.parent
            / "specs"
            / "016-dynamic-scene-scripting"
            / "contracts"
            / "corte_video_schema.json"
        )
        self.assertTrue(
            contract_path.exists(),
            f"Contract schema file does not exist at {contract_path}",
        )

        with open(contract_path, "r", encoding="utf-8") as f:
            expected_schema = json.load(f)

        tool = openai.pydantic_function_tool(CortesResponse)
        parameters = tool["function"]["parameters"]

        self.assertEqual(
            parameters,
            expected_schema,
            "Generated openai.pydantic_function_tool parameters differ from JSON contract.",
        )


class TestSceneValidationConstraints(unittest.TestCase):
    """T004: Unit tests for Scene validation constraints."""

    def test_valid_scene_creation(self):
        """Assert valid Scene instance can be constructed with non-empty fields."""
        scene = Scene(
            start_word="Comecei",
            end_word="empresa",
            visual_metaphor="mesa de escritório vazia",
            animation_trigger="zoom_in",
        )
        self.assertEqual(scene.start_word, "Comecei")
        self.assertEqual(scene.end_word, "empresa")
        self.assertEqual(scene.visual_metaphor, "mesa de escritório vazia")
        self.assertEqual(scene.animation_trigger, "zoom_in")

    def test_empty_start_word_raises_validation_error(self):
        """Assert empty start_word raises ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            Scene(
                start_word="",
                end_word="fim",
                visual_metaphor="metáfora",
                animation_trigger="corte",
            )
        self.assertIn("start_word", str(ctx.exception))

    def test_empty_end_word_raises_validation_error(self):
        """Assert empty end_word raises ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            Scene(
                start_word="inicio",
                end_word="",
                visual_metaphor="metáfora",
                animation_trigger="corte",
            )
        self.assertIn("end_word", str(ctx.exception))

    def test_empty_visual_metaphor_raises_validation_error(self):
        """Assert empty visual_metaphor raises ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            Scene(
                start_word="inicio",
                end_word="fim",
                visual_metaphor="",
                animation_trigger="corte",
            )
        self.assertIn("visual_metaphor", str(ctx.exception))

    def test_empty_animation_trigger_raises_validation_error(self):
        """Assert empty animation_trigger raises ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            Scene(
                start_word="inicio",
                end_word="fim",
                visual_metaphor="metáfora",
                animation_trigger="",
            )
        self.assertIn("animation_trigger", str(ctx.exception))


class TestCorteVideoBackwardCompatibilityAndScenes(unittest.TestCase):
    """T004: Unit tests for CorteVideo backward compatibility and scenes field."""

    def test_corte_video_instantiation_without_scenes_defaults_to_empty_list(self):
        """Assert CorteVideo backward compatibility when scenes argument is omitted."""
        corte = CorteVideo(
            title="Corte sem cenas explícitas",
            description="Descrição de teste",
            start_time=10.0,
            end_time=35.0,
        )
        self.assertEqual(corte.scenes, [])

    def test_corte_video_deserialization_without_scenes_defaults_to_empty_list(self):
        """Assert JSON without scenes field deserializes with scenes=[] default."""
        payload = '{"title": "Corte Legacy", "start_time": 0.0, "end_time": 20.0}'
        corte = CorteVideo.model_validate_json(payload)
        self.assertEqual(corte.scenes, [])

    def test_corte_video_with_valid_scenes(self):
        """Assert CorteVideo with valid scenes list is created successfully."""
        scene = Scene(
            start_word="Início",
            end_word="conclusão",
            visual_metaphor="gráfico ascendente",
            animation_trigger="cut_transition",
        )
        corte = CorteVideo(
            title="Corte com cena",
            start_time=5.0,
            end_time=15.0,
            scenes=[scene],
        )
        self.assertEqual(len(corte.scenes), 1)
        self.assertEqual(corte.scenes[0].visual_metaphor, "gráfico ascendente")

    def test_corte_video_scenes_preserves_empty_list_for_backward_compatibility(self):
        """Assert empty scenes list is preserved on legacy cut validation."""
        payload = '{"title": "Corte Legacy", "start_time": 0.0, "end_time": 20.0, "scenes": []}'
        corte = CorteVideo.model_validate_json(payload)
        self.assertEqual(corte.scenes, [])


if __name__ == "__main__":
    unittest.main()
