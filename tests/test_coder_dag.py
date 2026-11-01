"""Unit, contract, execution, and self-healing tests for Coder DAG (Feature 017)."""
import json
from pathlib import Path
import unittest

import openai
from pydantic import ValidationError

from clipper.core.schemas import RenderScriptPayload


class TestRenderScriptPayloadSchemaContract(unittest.TestCase):
    """T003: Contract test verifying openai.pydantic_function_tool schema generation."""

    def test_pydantic_function_tool_schema_matches_contract(self):
        """Verify openai.pydantic_function_tool schema matches render_script_schema.json."""
        contract_path = (
            Path(__file__).resolve().parent.parent
            / "specs"
            / "017-self-healing-coder-dag"
            / "contracts"
            / "render_script_schema.json"
        )
        self.assertTrue(
            contract_path.exists(),
            f"Contract schema file does not exist at {contract_path}",
        )

        with open(contract_path, "r", encoding="utf-8") as f:
            expected_schema = json.load(f)

        tool = openai.pydantic_function_tool(RenderScriptPayload)
        parameters = tool["function"]["parameters"]

        self.assertEqual(
            parameters,
            expected_schema,
            "Generated openai.pydantic_function_tool parameters differ from JSON contract.",
        )


class TestRenderScriptPayloadValidationConstraints(unittest.TestCase):
    """T004: Unit tests for RenderScriptPayload validation constraints."""

    def test_valid_payload_creation(self):
        """Assert valid RenderScriptPayload instance can be constructed with valid python code."""
        code = "import moviepy.editor as mp\nprint('Render OK')\n"
        payload = RenderScriptPayload(script_code=code)
        self.assertEqual(payload.script_code, code)

    def test_empty_script_code_raises_validation_error(self):
        """Assert empty script_code raises ValidationError due to min_length=1."""
        with self.assertRaises(ValidationError) as ctx:
            RenderScriptPayload(script_code="")
        errors = ctx.exception.errors()
        self.assertTrue(any(err["type"] == "string_too_short" for err in errors))

    def test_missing_script_code_raises_validation_error(self):
        """Assert missing script_code raises ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            RenderScriptPayload.model_validate({})
        errors = ctx.exception.errors()
        self.assertTrue(any(err["type"] == "missing" for err in errors))


class TestCoderConfigSettings(unittest.TestCase):
    """T006: Unit tests for RENDER_TIMEOUT_SECONDS and RENDER_ERROR_MAX_CHARS configuration."""

    def test_default_config_constants(self):
        """Assert default values for render timeout and error max chars."""
        from clipper.runtime.config import RENDER_TIMEOUT_SECONDS, RENDER_ERROR_MAX_CHARS

        self.assertEqual(RENDER_TIMEOUT_SECONDS, 300)
        self.assertEqual(RENDER_ERROR_MAX_CHARS, 2000)


class TestVideoStateExtensions(unittest.TestCase):
    """T007: Verify VideoState TypedDict has been extended with Feature 017 fields."""

    def test_video_state_has_feature_017_annotations(self):
        """Assert VideoState defines all required fields for self-healing coder DAG."""
        from clipper.core.orchestrator import VideoState

        annotations = VideoState.__annotations__
        required_fields = {
            "render_script_path": str,
            "render_attempts": int,
            "render_error": str,
            "render_exit_code": int,
            "render_aborted": bool,
            "current_cut_index": int,
            "rendered_video_paths": list[str],
        }

        for field_name, expected_type in required_fields.items():
            self.assertIn(
                field_name,
                annotations,
                f"VideoState is missing expected field '{field_name}'",
            )
            self.assertEqual(
                annotations[field_name],
                expected_type,
                f"VideoState field '{field_name}' has unexpected type {annotations[field_name]}",
            )


class TestCoderNodeGeneration(unittest.TestCase):
    """T008 [US1]: Unit test coder_node generating render_script.py and storing path in VideoState."""

    def setUp(self):
        self.sample_cut = {
            "title": "Deterministic Engineering",
            "description": "Explaining predictability in distributed pipelines.",
            "start_time": 10.0,
            "end_time": 40.0,
            "scenes": [
                {
                    "start_word": "Deterministic",
                    "end_word": "pipelines",
                    "visual_metaphor": "engrenagens alinhadas",
                    "animation_trigger": "zoom_in",
                }
            ],
        }
        self.sample_state = {
            "video_path": "/app/output/source_video.mp4",
            "cortes_finais": [self.sample_cut],
            "approved_cut_ids": [1],
            "approval_complete": True,
            "word_timestamps": [
                {"word": "Deterministic", "start": 10.0, "end": 10.8},
                {"word": "pipelines", "start": 10.9, "end": 11.5},
            ],
            "visual_identity": {"theme": "cyberpunk", "primary_color": "#00FFCC"},
            "current_cut_index": 0,
            "render_attempts": 0,
            "render_error": "",
        }

    def test_coder_node_generates_script_and_saves_to_disk(self):
        """Verify coder_node generates render_script.py via instructor and updates render_script_path."""
        import tempfile
        from unittest.mock import MagicMock, patch
        import clipper.core.orchestrator as orchestrator

        script_code = (
            "import os\n"
            "from moviepy.editor import VideoFileClip\n"
            "print('Rendering vertical clip for cut 1')\n"
        )
        mock_payload = RenderScriptPayload(script_code=script_code)

        mock_raw_client = MagicMock()
        mock_instructor_client = MagicMock()
        mock_instructor_client.chat.completions.create.return_value = mock_payload

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(orchestrator, "create_llm_client", return_value=mock_raw_client), \
                 patch.object(orchestrator.instructor, "from_openai", return_value=mock_instructor_client), \
                 patch.object(orchestrator, "OUTPUT_DIR", temp_dir):

                update = orchestrator.coder_node(self.sample_state)

            self.assertIn("render_script_path", update)
            saved_path = Path(update["render_script_path"])
            self.assertTrue(saved_path.exists(), f"File does not exist: {saved_path}")
            self.assertEqual(saved_path.name, "render_script.py")
            self.assertEqual(saved_path.parent.name, "1")

            with open(saved_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertEqual(content, script_code)
            self.assertEqual(update.get("render_error", ""), "")


class TestCoderNodeErrorHandling(unittest.TestCase):
    """T009 [US1]: Unit test coder_node fail-fast and error handling on empty or malformed LLM completions."""

    def setUp(self):
        self.sample_state = {
            "video_path": "/app/output/source_video.mp4",
            "cortes_finais": [
                {
                    "title": "Test Cut",
                    "description": "Desc",
                    "start_time": 0.0,
                    "end_time": 30.0,
                    "scenes": [
                        {
                            "start_word": "Test",
                            "end_word": "Cut",
                            "visual_metaphor": "icon",
                            "animation_trigger": "cut",
                        }
                    ],
                }
            ],
            "approved_cut_ids": [1],
            "approval_complete": True,
            "word_timestamps": [],
            "visual_identity": {},
            "current_cut_index": 0,
            "render_attempts": 0,
            "render_error": "",
        }

    def test_coder_node_requires_approval_complete(self):
        """Assert coder_node raises ValueError when approval_complete is not True."""
        import clipper.core.orchestrator as orchestrator

        state = dict(self.sample_state)
        state["approval_complete"] = False
        with self.assertRaisesRegex(ValueError, "Cut approval is required"):
            orchestrator.coder_node(state)

    def test_coder_node_handles_empty_approved_cuts(self):
        """Assert coder_node sets render_error when no cuts are approved."""
        import clipper.core.orchestrator as orchestrator

        state = dict(self.sample_state)
        state["approved_cut_ids"] = []
        result = orchestrator.coder_node(state)
        self.assertEqual(result.get("render_script_path"), "")
        self.assertIn("No approved cuts", result.get("render_error", ""))

    def test_coder_node_handles_llm_api_failure(self):
        """Assert coder_node captures LLM API errors into render_error without unhandled exception."""
        from unittest.mock import MagicMock, patch
        import clipper.core.orchestrator as orchestrator

        mock_raw_client = MagicMock()
        mock_instructor_client = MagicMock()
        mock_instructor_client.chat.completions.create.side_effect = openai.APIConnectionError(
            request=MagicMock()
        )

        with patch.object(orchestrator, "create_llm_client", return_value=mock_raw_client), \
             patch.object(orchestrator.instructor, "from_openai", return_value=mock_instructor_client):

            result = orchestrator.coder_node(self.sample_state)

        self.assertEqual(result.get("render_script_path"), "")
        self.assertTrue(len(result.get("render_error", "")) > 0)

    def test_coder_node_handles_validation_error(self):
        """Assert coder_node captures Pydantic ValidationError when LLM returns invalid payload."""
        from unittest.mock import MagicMock, patch
        import clipper.core.orchestrator as orchestrator

        mock_raw_client = MagicMock()
        mock_instructor_client = MagicMock()
        mock_instructor_client.chat.completions.create.side_effect = ValidationError.from_exception_data(
            title="RenderScriptPayload", line_errors=[]
        )

        with patch.object(orchestrator, "create_llm_client", return_value=mock_raw_client), \
             patch.object(orchestrator.instructor, "from_openai", return_value=mock_instructor_client):

            result = orchestrator.coder_node(self.sample_state)

        self.assertEqual(result.get("render_script_path"), "")
        self.assertTrue(len(result.get("render_error", "")) > 0)

    def test_coder_node_handles_io_write_failure(self):
        """Assert coder_node captures disk write errors into render_error."""
        from unittest.mock import MagicMock, patch
        import clipper.core.orchestrator as orchestrator

        mock_raw_client = MagicMock()
        mock_instructor_client = MagicMock()
        mock_payload = RenderScriptPayload(script_code="print('ok')")
        mock_instructor_client.chat.completions.create.return_value = mock_payload

        with patch.object(orchestrator, "create_llm_client", return_value=mock_raw_client), \
             patch.object(orchestrator.instructor, "from_openai", return_value=mock_instructor_client), \
             patch("builtins.open", side_effect=OSError("Disk write failed")):

            result = orchestrator.coder_node(self.sample_state)

        self.assertEqual(result.get("render_script_path"), "")
        self.assertIn("Disk write failed", result.get("render_error", ""))


class TestCoderNodeClientLifecycle(unittest.TestCase):
    """T010 [US1]: Unit test coder_node client lifecycle and deterministic raw_client.close cleanup."""

    def setUp(self):
        self.sample_state = {
            "video_path": "/app/output/source_video.mp4",
            "cortes_finais": [
                {
                    "title": "Lifecycle Cut",
                    "description": "Desc",
                    "start_time": 0.0,
                    "end_time": 30.0,
                    "scenes": [
                        {
                            "start_word": "Lifecycle",
                            "end_word": "Cut",
                            "visual_metaphor": "cycle",
                            "animation_trigger": "cut",
                        }
                    ],
                }
            ],
            "approved_cut_ids": [1],
            "approval_complete": True,
            "word_timestamps": [],
            "visual_identity": {},
            "current_cut_index": 0,
            "render_attempts": 0,
            "render_error": "",
        }

    def test_raw_client_close_called_on_success(self):
        """Assert raw_client.close is called deterministically when script generation succeeds."""
        import tempfile
        from unittest.mock import MagicMock, patch
        import clipper.core.orchestrator as orchestrator

        mock_raw_client = MagicMock()
        mock_instructor_client = MagicMock()
        mock_payload = RenderScriptPayload(script_code="print('Success')")
        mock_instructor_client.chat.completions.create.return_value = mock_payload

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(orchestrator, "create_llm_client", return_value=mock_raw_client), \
                 patch.object(orchestrator.instructor, "from_openai", return_value=mock_instructor_client), \
                 patch.object(orchestrator, "OUTPUT_DIR", temp_dir):

                orchestrator.coder_node(self.sample_state)

        mock_raw_client.close.assert_called_once()

    def test_raw_client_close_called_on_exception(self):
        """Assert raw_client.close is called deterministically when an exception occurs in LLM call."""
        from unittest.mock import MagicMock, patch
        import clipper.core.orchestrator as orchestrator

        mock_raw_client = MagicMock()
        mock_instructor_client = MagicMock()
        mock_instructor_client.chat.completions.create.side_effect = RuntimeError("Fatal LLM error")

        with patch.object(orchestrator, "create_llm_client", return_value=mock_raw_client), \
             patch.object(orchestrator.instructor, "from_openai", return_value=mock_instructor_client):

            orchestrator.coder_node(self.sample_state)

        mock_raw_client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
