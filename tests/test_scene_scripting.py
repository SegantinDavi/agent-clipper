"""Unit, contract, and validation tests for Scene and CorteVideo models (Feature 016)."""
import json
from pathlib import Path
import unittest

import openai
from pydantic import ValidationError

from clipper.core.schemas import CorteVideo, CortesResponse, Scene
from clipper.core.prompts import EXTRACTOR_SYSTEM_PROMPT_TEMPLATE, EXTRACTOR_FEW_SHOT_EXAMPLES


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


class TestExtractorNodeSceneExtraction(unittest.TestCase):
    """T006: Unit test extractor_node scene extraction and cortes_finais dictionary mapping."""

    def test_extractor_node_returns_cuts_with_valid_scenes_dict_mapping(self):
        """Verify extractor_node produces valid cuts with enriched scenes in cortes_finais."""
        from unittest.mock import MagicMock, patch
        from clipper.core.orchestrator import extractor_node

        mock_response = CortesResponse(
            cortes=[
                CorteVideo(
                    title="Engenharia de Software Moderna",
                    description="Discussão sobre sistemas determinísticos.",
                    start_time=10.0,
                    end_time=35.0,
                    scenes=[
                        Scene(
                            start_word="Começamos",
                            end_word="arquitetura",
                            visual_metaphor="blueprint arquitetônico",
                            animation_trigger="zoom_in",
                        ),
                        Scene(
                            start_word="depois",
                            end_word="produção",
                            visual_metaphor="linha de montagem automatizada",
                            animation_trigger="cut_transition",
                        ),
                    ],
                )
            ]
        )

        mock_client = MagicMock()
        mock_instructor = MagicMock()
        mock_instructor.chat.completions.create.return_value = mock_response

        with patch("clipper.core.orchestrator.create_llm_client", return_value=mock_client), \
             patch("instructor.from_openai", return_value=mock_instructor):
            state = {
                "transcript_grouped": "[10.00 - 35.00] Começamos a arquitetura depois fomos para produção.",
                "raciocinio_bruto": "Momento de alta relevância técnica entre 10 e 35 segundos.",
            }
            result = extractor_node(state)

        self.assertIn("cortes_finais", result)
        cortes = result["cortes_finais"]
        self.assertEqual(len(cortes), 1)
        cut = cortes[0]
        self.assertIsInstance(cut, dict)
        self.assertEqual(cut["title"], "Engenharia de Software Moderna")
        self.assertIn("scenes", cut)
        self.assertEqual(len(cut["scenes"]), 2)

        scene_1 = cut["scenes"][0]
        self.assertIsInstance(scene_1, dict)
        self.assertEqual(scene_1["start_word"], "Começamos")
        self.assertEqual(scene_1["end_word"], "arquitetura")
        self.assertEqual(scene_1["visual_metaphor"], "blueprint arquitetônico")
        self.assertEqual(scene_1["animation_trigger"], "zoom_in")

        scene_2 = cut["scenes"][1]
        self.assertIsInstance(scene_2, dict)
        self.assertEqual(scene_2["start_word"], "depois")
        self.assertEqual(scene_2["end_word"], "produção")
        self.assertEqual(scene_2["visual_metaphor"], "linha de montagem automatizada")
        self.assertEqual(scene_2["animation_trigger"], "cut_transition")
        mock_client.close.assert_called_once()


class TestExtractorNodeEmptyScenesFailFast(unittest.TestCase):
    """T007: Unit test extractor_node fail-fast behavior when LLM returns cuts with empty scenes."""

    def test_extractor_node_raises_value_error_on_empty_scenes(self):
        """Verify extractor_node raises ValueError when a cut has an empty scenes list."""
        from unittest.mock import MagicMock, patch
        from clipper.core.orchestrator import extractor_node

        mock_response = CortesResponse(
            cortes=[
                CorteVideo(
                    title="Corte sem cenas",
                    description="Descrição do corte",
                    start_time=0.0,
                    end_time=15.0,
                    scenes=[],
                )
            ]
        )
        mock_client = MagicMock()
        mock_instructor = MagicMock()
        mock_instructor.chat.completions.create.return_value = mock_response

        with patch("clipper.core.orchestrator.create_llm_client", return_value=mock_client), \
             patch("instructor.from_openai", return_value=mock_instructor):
            state = {
                "transcript_grouped": "[0.00 - 15.00] Fala do vídeo",
                "raciocinio_bruto": "Análise editorial",
            }
            with self.assertRaises(ValueError) as ctx:
                extractor_node(state)

            self.assertIn("cenas", str(ctx.exception).lower())
        mock_client.close.assert_called_once()

    def test_extractor_node_fails_fast_when_any_cut_has_empty_scenes(self):
        """Verify extractor_node fails fast if any cut in a multi-cut response has empty scenes."""
        from unittest.mock import MagicMock, patch
        from clipper.core.orchestrator import extractor_node

        mock_response = CortesResponse(
            cortes=[
                CorteVideo(
                    title="Corte com cenas",
                    start_time=0.0,
                    end_time=10.0,
                    scenes=[
                        Scene(
                            start_word="Olá",
                            end_word="mundo",
                            visual_metaphor="globo",
                            animation_trigger="impact",
                        )
                    ],
                ),
                CorteVideo(
                    title="Corte sem cenas",
                    start_time=15.0,
                    end_time=30.0,
                    scenes=[],
                ),
            ]
        )
        mock_client = MagicMock()
        mock_instructor = MagicMock()
        mock_instructor.chat.completions.create.return_value = mock_response

        with patch("clipper.core.orchestrator.create_llm_client", return_value=mock_client), \
             patch("instructor.from_openai", return_value=mock_instructor):
            state = {
                "transcript_grouped": "[0.00 - 30.00] Fala completa",
                "raciocinio_bruto": "Análise editorial",
            }
            with self.assertRaises(ValueError) as ctx:
                extractor_node(state)

            self.assertIn("cenas", str(ctx.exception).lower())
        mock_client.close.assert_called_once()


class TestExtractorNodeEditorialDurationWarning(unittest.TestCase):
    """T008: Unit test extractor_node editorial duration warning (> 4s) and graceful fallback."""

    def test_extractor_node_logs_warning_when_scene_duration_exceeds_4s(self):
        """Verify extractor_node logs a WARNING when a scene's duration exceeds 4.0s without rejecting cut."""
        from unittest.mock import MagicMock, patch
        from clipper.core.orchestrator import extractor_node

        mock_response = CortesResponse(
            cortes=[
                CorteVideo(
                    title="Corte Pacing Longo",
                    description="Cena única com mais de 4 segundos",
                    start_time=0.0,
                    end_time=10.0,
                    scenes=[
                        Scene(
                            start_word="Início",
                            end_word="Conclusão",
                            visual_metaphor="ampulheta",
                            animation_trigger="slow_zoom",
                        )
                    ],
                )
            ]
        )
        mock_client = MagicMock()
        mock_instructor = MagicMock()
        mock_instructor.chat.completions.create.return_value = mock_response

        with patch("clipper.core.orchestrator.create_llm_client", return_value=mock_client), \
             patch("instructor.from_openai", return_value=mock_instructor):
            state = {
                "transcript_grouped": "[0.00 - 10.00] Início da explicação detalhada até a Conclusão.",
                "raciocinio_bruto": "Análise editorial",
                "word_timestamps": [
                    {"word": "Início", "start": 0.5, "end": 1.0},
                    {"word": "da", "start": 1.1, "end": 1.3},
                    {"word": "explicação", "start": 1.4, "end": 2.2},
                    {"word": "detalhada", "start": 2.3, "end": 3.2},
                    {"word": "até", "start": 3.3, "end": 3.6},
                    {"word": "a", "start": 3.7, "end": 3.9},
                    {"word": "Conclusão.", "start": 4.0, "end": 6.2},
                ],
            }

            with self.assertLogs("clipper.core.orchestrator", level="WARNING") as log_ctx:
                result = extractor_node(state)

        # Assert cut is still included and not discarded
        self.assertEqual(len(result["cortes_finais"]), 1)
        self.assertEqual(result["cortes_finais"][0]["title"], "Corte Pacing Longo")

        # Assert warning log occurred for 4.0s guideline
        self.assertTrue(
            any("4.0s" in msg or "exceeds" in msg.lower() or "4" in msg for msg in log_ctx.output),
            f"Expected 4.0s duration warning in logs, got: {log_ctx.output}",
        )
        mock_client.close.assert_called_once()

    def test_extractor_node_graceful_fallback_when_word_timestamps_empty(self):
        """Verify extractor_node skips duration checks gracefully when word_timestamps is empty."""
        from unittest.mock import MagicMock, patch
        from clipper.core.orchestrator import extractor_node

        mock_response = CortesResponse(
            cortes=[
                CorteVideo(
                    title="Corte Normal",
                    start_time=0.0,
                    end_time=5.0,
                    scenes=[
                        Scene(
                            start_word="Olá",
                            end_word="mundo",
                            visual_metaphor="sol",
                            animation_trigger="fade",
                        )
                    ],
                )
            ]
        )
        mock_client = MagicMock()
        mock_instructor = MagicMock()
        mock_instructor.chat.completions.create.return_value = mock_response

        with patch("clipper.core.orchestrator.create_llm_client", return_value=mock_client), \
             patch("instructor.from_openai", return_value=mock_instructor):
            state = {
                "transcript_grouped": "[0.00 - 5.00] Olá mundo",
                "raciocinio_bruto": "Análise editorial",
                "word_timestamps": [],
            }
            result = extractor_node(state)

        self.assertEqual(len(result["cortes_finais"]), 1)
        mock_client.close.assert_called_once()

    def test_extractor_node_graceful_fallback_when_word_timestamps_missing(self):
        """Verify extractor_node skips duration checks gracefully when word_timestamps is absent from state."""
        from unittest.mock import MagicMock, patch
        from clipper.core.orchestrator import extractor_node

        mock_response = CortesResponse(
            cortes=[
                CorteVideo(
                    title="Corte Normal",
                    start_time=0.0,
                    end_time=5.0,
                    scenes=[
                        Scene(
                            start_word="Olá",
                            end_word="mundo",
                            visual_metaphor="sol",
                            animation_trigger="fade",
                        )
                    ],
                )
            ]
        )
        mock_client = MagicMock()
        mock_instructor = MagicMock()
        mock_instructor.chat.completions.create.return_value = mock_response

        with patch("clipper.core.orchestrator.create_llm_client", return_value=mock_client), \
             patch("instructor.from_openai", return_value=mock_instructor):
            state = {
                "transcript_grouped": "[0.00 - 5.00] Olá mundo",
                "raciocinio_bruto": "Análise editorial",
            }
            result = extractor_node(state)

        self.assertEqual(len(result["cortes_finais"]), 1)
        mock_client.close.assert_called_once()

    def test_extractor_node_does_not_warn_when_scenes_under_4s(self):
        """Verify extractor_node does not emit duration warning when scene is under 4.0s."""
        from unittest.mock import MagicMock, patch
        from clipper.core.orchestrator import extractor_node

        mock_response = CortesResponse(
            cortes=[
                CorteVideo(
                    title="Corte Pacing Ideal",
                    start_time=0.0,
                    end_time=5.0,
                    scenes=[
                        Scene(
                            start_word="Olá",
                            end_word="mundo",
                            visual_metaphor="sol",
                            animation_trigger="fade",
                        )
                    ],
                )
            ]
        )
        mock_client = MagicMock()
        mock_instructor = MagicMock()
        mock_instructor.chat.completions.create.return_value = mock_response

        with patch("clipper.core.orchestrator.create_llm_client", return_value=mock_client), \
             patch("instructor.from_openai", return_value=mock_instructor):
            state = {
                "transcript_grouped": "[0.00 - 5.00] Olá mundo",
                "raciocinio_bruto": "Análise editorial",
                "word_timestamps": [
                    {"word": "Olá", "start": 0.5, "end": 1.0},
                    {"word": "mundo", "start": 1.2, "end": 2.5},
                ],
            }
            # Catch all logs to assert no 4.0s warnings were produced
            with patch("clipper.core.orchestrator.logger.warning") as mock_warn:
                result = extractor_node(state)
                # Ensure no warning was called for 4.0s guideline
                for call_args in mock_warn.call_args_list:
                    msg = call_args[0][0] if call_args[0] else ""
                    self.assertNotIn("4.0s", msg)

        self.assertEqual(len(result["cortes_finais"]), 1)
        mock_client.close.assert_called_once()


class TestExtractorPromptsAndFewShotValidation(unittest.TestCase):
    """T012: Unit tests for EXTRACTOR_SYSTEM_PROMPT_TEMPLATE and EXTRACTOR_FEW_SHOT_EXAMPLES."""

    def test_extractor_system_prompt_contains_scene_scripting_instructions(self):
        """Verify EXTRACTOR_SYSTEM_PROMPT_TEMPLATE contains explicit scene segmentation rules (FR-004)."""
        prompt = EXTRACTOR_SYSTEM_PROMPT_TEMPLATE.lower()
        # Must instruct 2 to 4 seconds segmentation
        self.assertTrue(
            "2 a 4" in prompt or "2-4" in prompt or "2 a 4 segundos" in prompt,
            "Prompt template must specify 2-4 seconds scene duration rule.",
        )
        # Must mention scene fields
        self.assertIn("cenas", prompt)
        self.assertIn("start_word", prompt)
        self.assertIn("end_word", prompt)
        self.assertIn("visual_metaphor", prompt)
        self.assertIn("animation_trigger", prompt)

    def test_extractor_few_shot_examples_assistant_payloads_parse_strictly_with_scenes(self):
        """Verify that all assistant payloads in EXTRACTOR_FEW_SHOT_EXAMPLES parse into CortesResponse (FR-005)."""
        assistant_messages = [
            msg for msg in EXTRACTOR_FEW_SHOT_EXAMPLES if msg.get("role") == "assistant"
        ]
        self.assertGreaterEqual(
            len(assistant_messages),
            2,
            "Must have at least 2 few-shot assistant examples (FR-005).",
        )

        for i, msg in enumerate(assistant_messages):
            content = msg["content"]
            # Must strictly validate as CortesResponse
            parsed = CortesResponse.model_validate_json(content)
            self.assertGreater(
                len(parsed.cortes),
                0,
                f"Assistant example {i} has no cuts.",
            )
            for j, cut in enumerate(parsed.cortes):
                self.assertGreater(
                    len(cut.scenes),
                    0,
                    f"Assistant example {i}, cut {j} must contain at least one scene (FR-002, FR-005).",
                )
                for k, scene in enumerate(cut.scenes):
                    self.assertTrue(
                        len(scene.start_word.strip()) > 0,
                        f"Assistant example {i}, cut {j}, scene {k} has empty start_word.",
                    )
                    self.assertTrue(
                        len(scene.end_word.strip()) > 0,
                        f"Assistant example {i}, cut {j}, scene {k} has empty end_word.",
                    )
                    self.assertTrue(
                        len(scene.visual_metaphor.strip()) > 0,
                        f"Assistant example {i}, cut {j}, scene {k} has empty visual_metaphor.",
                    )
                    self.assertTrue(
                        len(scene.animation_trigger.strip()) > 0,
                        f"Assistant example {i}, cut {j}, scene {k} has empty animation_trigger.",
                    )

    def test_extractor_few_shot_examples_demonstrate_diverse_metaphors_and_triggers(self):
        """Verify that multi-scene few-shot examples exhibit diversity in visual metaphors and triggers."""
        assistant_messages = [
            msg for msg in EXTRACTOR_FEW_SHOT_EXAMPLES if msg.get("role") == "assistant"
        ]
        all_metaphors = []
        all_triggers = []
        for msg in assistant_messages:
            parsed = CortesResponse.model_validate_json(msg["content"])
            for cut in parsed.cortes:
                if len(cut.scenes) > 1:
                    metaphors = [s.visual_metaphor for s in cut.scenes]
                    # Metaphors within the same multi-scene cut must be diverse (not all identical)
                    self.assertGreater(
                        len(set(metaphors)),
                        1,
                        f"Cut '{cut.title}' has repetitive visual metaphors: {metaphors}",
                    )
                all_metaphors.extend([s.visual_metaphor for s in cut.scenes])
                all_triggers.extend([s.animation_trigger for s in cut.scenes])

        # Overall trigger set should include dynamic triggers like zoom, impact, or cut
        trigger_str = " ".join(all_triggers).lower()
        self.assertTrue(
            any(t in trigger_str for t in ["zoom", "impact", "cut"]),
            f"Expected dynamic animation triggers in few-shot examples, found: {all_triggers}",
        )


class TestLLMProviderNeutralitySceneExtraction(unittest.TestCase):
    """T013: Unit test verifying LLM provider neutrality across Ollama and Gemini response fixtures."""

    def test_extractor_node_provider_neutrality_ollama_and_gemini(self):
        """Verify extractor_node functions identically for both 'ollama' and 'gemini' providers (FR-007)."""
        from unittest.mock import MagicMock, patch
        from clipper.core.orchestrator import extractor_node

        mock_cut = CorteVideo(
            title="Provider Neutral Cut",
            description="Testing provider neutrality for scene extraction.",
            start_time=10.0,
            end_time=30.0,
            scenes=[
                Scene(
                    start_word="Primeiro",
                    end_word="ponto",
                    visual_metaphor="lâmpada acendendo",
                    animation_trigger="zoom_in",
                ),
                Scene(
                    start_word="Segundo",
                    end_word="resultado",
                    visual_metaphor="foguete decolando",
                    animation_trigger="impact",
                ),
            ],
        )
        mock_response = CortesResponse(cortes=[mock_cut])

        for provider in ["ollama", "gemini"]:
            with self.subTest(provider=provider):
                mock_client = MagicMock()
                mock_instructor = MagicMock()
                mock_instructor.chat.completions.create.return_value = mock_response

                with patch("clipper.core.orchestrator.create_llm_client", return_value=mock_client) as mock_create_client, \
                     patch("instructor.from_openai", return_value=mock_instructor), \
                     patch("os.getenv", side_effect=lambda k, default=None: provider if k == "LLM_PROVIDER" else default):

                    state = {
                        "transcript_grouped": "[10.00 - 30.00] Primeiro ponto relevante e Segundo resultado.",
                        "raciocinio_bruto": "Análise editorial recomendando corte entre 10 e 30s.",
                    }
                    result = extractor_node(state)

                    mock_create_client.assert_called_once()
                    mock_client.close.assert_called_once()
                    self.assertIn("cortes_finais", result)
                    cortes = result["cortes_finais"]
                    self.assertEqual(len(cortes), 1)
                    self.assertEqual(cortes[0]["title"], "Provider Neutral Cut")
                    self.assertEqual(len(cortes[0]["scenes"]), 2)
                    self.assertEqual(cortes[0]["scenes"][0]["visual_metaphor"], "lâmpada acendendo")
                    self.assertEqual(cortes[0]["scenes"][1]["animation_trigger"], "impact")


if __name__ == "__main__":
    unittest.main()
