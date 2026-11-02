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


class TestExecutionNode(unittest.TestCase):
    """T014, T015, T016 [US2]: Unit tests for execution_node subprocess isolation and outcome capture."""

    def setUp(self):
        self.sample_state = {
            "render_script_path": "",
            "render_attempts": 0,
            "render_error": "",
            "render_exit_code": 0,
            "render_aborted": False,
            "current_cut_index": 0,
            "approved_cut_ids": [1],
            "rendered_video_paths": [],
        }

    def test_execution_node_running_successful_script(self):
        """T014 [US2]: execution_node running a successful script returns exit code 0 and empty render_error."""
        import tempfile
        import clipper.core.orchestrator as orchestrator

        with tempfile.TemporaryDirectory() as temp_dir:
            script_file = Path(temp_dir) / "render_script.py"
            script_file.write_text("print('Rendered cut successfully!')\n", encoding="utf-8")

            state = dict(self.sample_state)
            state["render_script_path"] = str(script_file)
            state["render_attempts"] = 0

            result = orchestrator.execution_node(state)

            self.assertEqual(result.get("render_attempts"), 1)
            self.assertEqual(result.get("render_exit_code"), 0)
            self.assertEqual(result.get("render_error"), "")

    def test_execution_node_running_failing_script_captures_error(self):
        """T015 [US2]: execution_node captures non-zero exit code and stderr traceback without crashing."""
        import tempfile
        import clipper.core.orchestrator as orchestrator

        with tempfile.TemporaryDirectory() as temp_dir:
            script_file = Path(temp_dir) / "render_script.py"
            script_file.write_text("raise ValueError('Simulated MoviePy crash')\n", encoding="utf-8")

            state = dict(self.sample_state)
            state["render_script_path"] = str(script_file)
            state["render_attempts"] = 1

            result = orchestrator.execution_node(state)

            self.assertEqual(result.get("render_attempts"), 2)
            self.assertNotEqual(result.get("render_exit_code"), 0)
            self.assertIn("Simulated MoviePy crash", result.get("render_error", ""))

    def test_execution_node_handles_missing_script_file(self):
        """T015 [US2]: execution_node handles missing script file gracefully without crashing."""
        import clipper.core.orchestrator as orchestrator

        state = dict(self.sample_state)
        state["render_script_path"] = "/nonexistent/path/to/render_script.py"
        state["render_attempts"] = 0

        result = orchestrator.execution_node(state)

        self.assertEqual(result.get("render_attempts"), 1)
        self.assertNotEqual(result.get("render_exit_code"), 0)
        self.assertTrue(len(result.get("render_error", "")) > 0)

    def test_execution_node_handles_timeout(self):
        """T016 [US2]: execution_node terminates hanging child process and records timeout diagnostic."""
        import subprocess
        from unittest.mock import patch
        import clipper.core.orchestrator as orchestrator

        state = dict(self.sample_state)
        state["render_script_path"] = "/fake/hanging_script.py"
        state["render_attempts"] = 0

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["python"], timeout=5)):
            with patch("os.path.exists", return_value=True):
                result = orchestrator.execution_node(state)

        self.assertEqual(result.get("render_attempts"), 1)
        self.assertEqual(result.get("render_exit_code"), -1)
        self.assertIn("timed out", result.get("render_error", "").lower())


class TestRouteExecutionOutcome(unittest.TestCase):
    """T019 [US3]: Unit tests for route_execution_outcome conditional router."""

    def test_routes_to_complete_when_exit_code_zero(self):
        """Assert route_execution_outcome returns 'complete' when render_exit_code is 0."""
        import clipper.core.orchestrator as orchestrator

        state = {"render_exit_code": 0, "render_attempts": 1}
        self.assertEqual(orchestrator.route_execution_outcome(state), "complete")

        state = {"render_exit_code": 0, "render_attempts": 3}
        self.assertEqual(orchestrator.route_execution_outcome(state), "complete")

    def test_routes_to_retry_when_exit_code_nonzero_and_attempts_under_three(self):
        """Assert route_execution_outcome returns 'retry' when exit code is non-zero and attempts < 3."""
        import clipper.core.orchestrator as orchestrator

        state = {"render_exit_code": 1, "render_attempts": 1}
        self.assertEqual(orchestrator.route_execution_outcome(state), "retry")

        state = {"render_exit_code": -1, "render_attempts": 2}
        self.assertEqual(orchestrator.route_execution_outcome(state), "retry")

    def test_routes_to_abort_when_exit_code_nonzero_and_attempts_three_or_more(self):
        """Assert route_execution_outcome returns 'abort' when exit code is non-zero and attempts >= 3."""
        import clipper.core.orchestrator as orchestrator

        state = {"render_exit_code": 1, "render_attempts": 3}
        self.assertEqual(orchestrator.route_execution_outcome(state), "abort")

        state = {"render_exit_code": 2, "render_attempts": 4}
        self.assertEqual(orchestrator.route_execution_outcome(state), "abort")


class TestCoderRetryPrompt(unittest.TestCase):
    """T020 [US3]: Unit test CODER_RETRY_PROMPT_TEMPLATE formatting and coder_node retry logic."""

    def test_coder_retry_prompt_template_formatting(self):
        """Assert CODER_RETRY_PROMPT_TEMPLATE formats required diagnostic placeholders cleanly."""
        from clipper.core.prompts import CODER_RETRY_PROMPT_TEMPLATE

        formatted = CODER_RETRY_PROMPT_TEMPLATE.format(
            attempt=2,
            error_diagnostic="ZeroDivisionError: division by zero",
            previous_script="x = 1 / 0",
            cut_metadata="Cut 1: 0s - 30s",
        )
        self.assertIn("Tentativa 2", formatted)
        self.assertIn("ZeroDivisionError: division by zero", formatted)
        self.assertIn("x = 1 / 0", formatted)
        self.assertIn("Cut 1: 0s - 30s", formatted)

    def test_coder_node_retry_injects_truncated_stderr_into_llm_prompt(self):
        """Assert coder_node with render_attempts > 0 injects truncated stderr into user message."""
        import tempfile
        from unittest.mock import MagicMock, patch
        import clipper.core.orchestrator as orchestrator

        sample_state = {
            "video_path": "/app/output/source.mp4",
            "cortes_finais": [
                {
                    "title": "Retry Cut",
                    "description": "Desc",
                    "start_time": 0.0,
                    "end_time": 30.0,
                    "scenes": [
                        {
                            "start_word": "Retry",
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
            "render_attempts": 1,
            "render_error": "LONG_PREFIX_" * 300 + "CRITICAL_ROOT_ERROR_LINE",
        }

        mock_raw_client = MagicMock()
        mock_instructor_client = MagicMock()
        mock_payload = RenderScriptPayload(script_code="print('Fixed')")
        mock_instructor_client.chat.completions.create.return_value = mock_payload

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(orchestrator, "create_llm_client", return_value=mock_raw_client), \
                 patch.object(orchestrator.instructor, "from_openai", return_value=mock_instructor_client), \
                 patch.object(orchestrator, "OUTPUT_DIR", temp_dir):

                orchestrator.coder_node(sample_state)

        # Inspect messages passed to chat.completions.create
        call_kwargs = mock_instructor_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        user_message = next(m["content"] for m in messages if m["role"] == "user")

        self.assertIn("CRITICAL_ROOT_ERROR_LINE", user_message)
        self.assertIn("Tentativa 1", user_message)
        # Ensure error diagnostic was truncated within RENDER_ERROR_MAX_CHARS (2000 chars)
        self.assertLess(len(user_message), 3000)


class TestAbortNode(unittest.TestCase):
    """T021 [US3]: Unit test abort_node setting render_aborted True and logging warning."""

    def test_abort_node_sets_render_aborted_true(self):
        """Assert abort_node returns dict with render_aborted = True without crashing."""
        import clipper.core.orchestrator as orchestrator

        state = {
            "current_cut_index": 0,
            "approved_cut_ids": [1],
            "render_attempts": 3,
            "render_error": "Persistent BrokenPipeError",
        }

        result = orchestrator.abort_node(state)
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("render_aborted"))


class TestSelfHealingIntegration(unittest.TestCase):
    """T023, T024, T025 [US3]: Integration tests for self-healing retry loop, abort termination, and SqliteSaver persistence."""

    def setUp(self):
        import os
        self._prev_engine = os.environ.get("RENDER_ENGINE")
        os.environ["RENDER_ENGINE"] = "coder"

    def tearDown(self):
        import os
        if self._prev_engine is not None:
            os.environ["RENDER_ENGINE"] = self._prev_engine
        else:
            os.environ.pop("RENDER_ENGINE", None)

    def test_end_to_end_self_healing_retry_loop_recovering(self):
        """T023 [US3]: Verify DAG self-healing recovers from initial failure on attempt 2."""
        import tempfile
        from unittest.mock import MagicMock, patch
        import clipper.core.orchestrator as orchestrator

        with tempfile.TemporaryDirectory() as temp_dir:
            # Attempt 1: broken script, Attempt 2: valid working script
            script_attempt_1 = RenderScriptPayload(script_code="raise RuntimeError('Transient failure')")
            script_attempt_2 = RenderScriptPayload(script_code="print('Render Success!')")

            mock_raw_client = MagicMock()
            mock_instructor_client = MagicMock()
            mock_instructor_client.chat.completions.create.side_effect = [script_attempt_1, script_attempt_2]

            workflow = orchestrator.create_graph()
            app = workflow.compile()

            initial_state = {
                "video_url": "https://youtu.be/dummy",
                "video_path": "/fake/video.mp4",
                "audio_chunks": [],
                "transcript_grouped": "test transcript",
                "word_timestamps": [],
                "raciocinio_bruto": "raciocinio",
                "cortes_finais": [
                    {
                        "title": "Recovering Cut",
                        "description": "Desc",
                        "start_time": 0.0,
                        "end_time": 30.0,
                        "scenes": [
                            {
                                "start_word": "test",
                                "end_word": "transcript",
                                "visual_metaphor": "icon",
                                "animation_trigger": "cut",
                            }
                        ],
                    }
                ],
                "review_directory": "",
                "review_session": "sess1",
                "approved_cut_ids": [1],
                "approval_complete": True,
                "visual_identity": {},
                "style_path": "",
                "render_script_path": "",
                "render_attempts": 0,
                "render_error": "",
                "render_exit_code": 0,
                "render_aborted": False,
                "current_cut_index": 0,
                "rendered_video_paths": [],
            }

            with patch.object(orchestrator, "create_llm_client", return_value=mock_raw_client), \
                 patch.object(orchestrator.instructor, "from_openai", return_value=mock_instructor_client), \
                 patch.object(orchestrator, "OUTPUT_DIR", temp_dir), \
                 patch.object(orchestrator, "download_node", return_value={"video_path": "/fake/video.mp4"}), \
                 patch.object(orchestrator, "fatiamento_node", return_value={}), \
                 patch.object(orchestrator, "style_node", return_value={}), \
                 patch.object(orchestrator, "transcription_node", return_value={}), \
                 patch.object(orchestrator, "thinker_node", return_value={}), \
                 patch.object(orchestrator, "extractor_node", return_value={}), \
                 patch.object(orchestrator, "preview_node", return_value={}), \
                 patch.object(orchestrator, "approval_node", return_value={"approved_cut_ids": [1], "approval_complete": True}):

                workflow = orchestrator.create_graph()
                app = workflow.compile()
                final_state = app.invoke(initial_state)

            self.assertEqual(final_state.get("render_exit_code"), 0)
            self.assertEqual(final_state.get("render_error"), "")
            self.assertEqual(mock_instructor_client.chat.completions.create.call_count, 2)

    def test_abort_edge_termination_after_three_failures(self):
        """T024 [US3]: Verify abort edge marks render_aborted=True after 3 consecutive failures without crash."""
        import tempfile
        from unittest.mock import MagicMock, patch
        import clipper.core.orchestrator as orchestrator

        with tempfile.TemporaryDirectory() as temp_dir:
            broken_script = RenderScriptPayload(script_code="raise RuntimeError('Permanent failure')")

            mock_raw_client = MagicMock()
            mock_instructor_client = MagicMock()
            mock_instructor_client.chat.completions.create.return_value = broken_script

            initial_state = {
                "video_url": "https://youtu.be/dummy",
                "video_path": "/fake/video.mp4",
                "audio_chunks": [],
                "transcript_grouped": "test transcript",
                "word_timestamps": [],
                "raciocinio_bruto": "raciocinio",
                "cortes_finais": [
                    {
                        "title": "Aborting Cut",
                        "description": "Desc",
                        "start_time": 0.0,
                        "end_time": 30.0,
                        "scenes": [
                            {
                                "start_word": "test",
                                "end_word": "transcript",
                                "visual_metaphor": "icon",
                                "animation_trigger": "cut",
                            }
                        ],
                    }
                ],
                "review_directory": "",
                "review_session": "sess1",
                "approved_cut_ids": [1],
                "approval_complete": True,
                "visual_identity": {},
                "style_path": "",
                "render_script_path": "",
                "render_attempts": 0,
                "render_error": "",
                "render_exit_code": 0,
                "render_aborted": False,
                "current_cut_index": 0,
                "rendered_video_paths": [],
            }

            with patch.object(orchestrator, "create_llm_client", return_value=mock_raw_client), \
                 patch.object(orchestrator.instructor, "from_openai", return_value=mock_instructor_client), \
                 patch.object(orchestrator, "OUTPUT_DIR", temp_dir), \
                 patch.object(orchestrator, "download_node", return_value={"video_path": "/fake/video.mp4"}), \
                 patch.object(orchestrator, "fatiamento_node", return_value={}), \
                 patch.object(orchestrator, "style_node", return_value={}), \
                 patch.object(orchestrator, "transcription_node", return_value={}), \
                 patch.object(orchestrator, "thinker_node", return_value={}), \
                 patch.object(orchestrator, "extractor_node", return_value={}), \
                 patch.object(orchestrator, "preview_node", return_value={}), \
                 patch.object(orchestrator, "approval_node", return_value={"approved_cut_ids": [1], "approval_complete": True}):

                workflow = orchestrator.create_graph()
                app = workflow.compile()
                final_state = app.invoke(initial_state)

            self.assertTrue(final_state.get("render_aborted"))
            self.assertEqual(final_state.get("render_attempts"), 3)
            self.assertEqual(mock_instructor_client.chat.completions.create.call_count, 3)

    def test_sqlitesaver_checkpoint_persistence_and_recovery(self):
        """T025 [US3]: Verify SqliteSaver checkpoints state mid-loop and recovers across simulated restarts."""
        import tempfile
        import sqlite3
        from langgraph.checkpoint.sqlite import SqliteSaver
        from unittest.mock import MagicMock, patch
        import clipper.core.orchestrator as orchestrator

        with tempfile.TemporaryDirectory() as temp_dir:
            db_file = Path(temp_dir) / "estado.db"
            conn = sqlite3.connect(str(db_file), check_same_thread=False)

            broken_script = RenderScriptPayload(script_code="raise RuntimeError('Retry loop test')")

            mock_raw_client = MagicMock()
            mock_instructor_client = MagicMock()
            mock_instructor_client.chat.completions.create.return_value = broken_script

            checkpointer = SqliteSaver(conn)
            checkpointer.setup()

            thread_id = "test-thread-recovery"
            graph_config = {"configurable": {"thread_id": thread_id}}

            initial_state = {
                "video_url": "https://youtu.be/dummy",
                "video_path": "/fake/video.mp4",
                "audio_chunks": [],
                "transcript_grouped": "test transcript",
                "word_timestamps": [],
                "raciocinio_bruto": "raciocinio",
                "cortes_finais": [
                    {
                        "title": "Persistent Cut",
                        "description": "Desc",
                        "start_time": 0.0,
                        "end_time": 30.0,
                        "scenes": [
                            {
                                "start_word": "test",
                                "end_word": "transcript",
                                "visual_metaphor": "icon",
                                "animation_trigger": "cut",
                            }
                        ],
                    }
                ],
                "review_directory": "",
                "review_session": "sess1",
                "approved_cut_ids": [1],
                "approval_complete": True,
                "visual_identity": {},
                "style_path": "",
                "render_script_path": "",
                "render_attempts": 0,
                "render_error": "",
                "render_exit_code": 0,
                "render_aborted": False,
                "current_cut_index": 0,
                "rendered_video_paths": [],
            }

            with patch.object(orchestrator, "create_llm_client", return_value=mock_raw_client), \
                 patch.object(orchestrator.instructor, "from_openai", return_value=mock_instructor_client), \
                 patch.object(orchestrator, "OUTPUT_DIR", temp_dir), \
                 patch.object(orchestrator, "download_node", return_value={"video_path": "/fake/video.mp4"}), \
                 patch.object(orchestrator, "fatiamento_node", return_value={}), \
                 patch.object(orchestrator, "style_node", return_value={}), \
                 patch.object(orchestrator, "transcription_node", return_value={}), \
                 patch.object(orchestrator, "thinker_node", return_value={}), \
                 patch.object(orchestrator, "extractor_node", return_value={}), \
                 patch.object(orchestrator, "preview_node", return_value={}), \
                 patch.object(orchestrator, "approval_node", return_value={"approved_cut_ids": [1], "approval_complete": True}):

                workflow = orchestrator.create_graph()
                app = workflow.compile(checkpointer=checkpointer)
                final_state = app.invoke(initial_state, config=graph_config)

            # Recover checkpoint from SQLite
            latest_checkpoint = checkpointer.get(graph_config)
            self.assertIsNotNone(latest_checkpoint)
            checkpoint_state = latest_checkpoint["channel_values"]

            self.assertTrue(checkpoint_state.get("render_aborted"))
            self.assertEqual(checkpoint_state.get("render_attempts"), 3)
            self.assertIn("Retry loop test", checkpoint_state.get("render_error", ""))


class TestCoderStaticAnalysisCompliance(unittest.TestCase):
    """T030 [P] [Polish]: Static analysis scan asserting zero occurrences of regex or manual json.loads (SC-002)."""

    def test_zero_regex_or_manual_json_loads_in_coder_layer(self):
        """Verify coder_node, execution_node, abort_node, advance_cut_node use zero regex or manual json.loads."""
        import ast
        import inspect
        import clipper.core.orchestrator as orchestrator

        targets = [
            orchestrator.coder_node,
            orchestrator.execution_node,
            orchestrator.abort_node,
            orchestrator.advance_cut_node,
            orchestrator.route_execution_outcome,
            orchestrator.route_cut_iteration,
        ]

        for fn in targets:
            source = inspect.getsource(fn)
            tree = ast.parse(source)

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        if isinstance(node.func.value, ast.Name):
                            mod_name = node.func.value.id
                            attr_name = node.func.attr
                            self.assertFalse(
                                mod_name == "json" and attr_name in ("loads", "load"),
                                f"Disallowed manual json parse '{mod_name}.{attr_name}' found in {fn.__name__} at line {node.lineno}",
                            )
                            self.assertFalse(
                                mod_name in ("re", "regex"),
                                f"Disallowed regex call '{mod_name}.{attr_name}' found in {fn.__name__} at line {node.lineno}",
                            )
                    elif isinstance(node.func, ast.Name):
                        self.assertNotIn(
                            node.func.id,
                            {"loads", "search", "match", "findall", "sub"},
                            f"Disallowed function call '{node.func.id}' found in {fn.__name__} at line {node.lineno}",
                        )


class TestCoderExecutionOverheadBenchmark(unittest.TestCase):
    """T031 [P] [Polish]: Benchmark execution overhead of coder_node and execution_node wrapper asserting < 500ms (SC-003)."""

    def test_coder_and_execution_node_overhead_under_500ms(self):
        """Assert coder_node and execution_node wrapper overhead is strictly under 500ms wall-clock."""
        import tempfile
        import time
        from unittest.mock import MagicMock, patch
        import clipper.core.orchestrator as orchestrator

        mock_payload = RenderScriptPayload(script_code="print('Benchmark OK')\n")
        mock_raw_client = MagicMock()
        mock_instructor_client = MagicMock()
        mock_instructor_client.chat.completions.create.return_value = mock_payload

        state = {
            "video_path": "/fake/video.mp4",
            "cortes_finais": [
                {
                    "title": "Bench Cut",
                    "description": "Benchmark overhead",
                    "start_time": 0.0,
                    "end_time": 30.0,
                    "scenes": [
                        {
                            "start_word": "hello",
                            "end_word": "world",
                            "visual_metaphor": "clock",
                            "animation_trigger": "tick",
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

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(orchestrator, "create_llm_client", return_value=mock_raw_client), \
                 patch.object(orchestrator.instructor, "from_openai", return_value=mock_instructor_client), \
                 patch.object(orchestrator, "OUTPUT_DIR", temp_dir):

                # Benchmark coder_node overhead
                start_coder = time.perf_counter()
                coder_result = orchestrator.coder_node(state)
                coder_elapsed = time.perf_counter() - start_coder

                self.assertLess(
                    coder_elapsed,
                    0.500,
                    f"coder_node overhead exceeded 500ms limit: {coder_elapsed:.4f}s",
                )

                state["render_script_path"] = coder_result["render_script_path"]

                # Benchmark execution_node overhead
                start_exec = time.perf_counter()
                exec_result = orchestrator.execution_node(state)
                exec_elapsed = time.perf_counter() - start_exec

                self.assertLess(
                    exec_elapsed,
                    0.500,
                    f"execution_node overhead exceeded 500ms limit: {exec_elapsed:.4f}s",
                )
                self.assertEqual(exec_result["render_exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
