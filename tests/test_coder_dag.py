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


if __name__ == "__main__":
    unittest.main()
