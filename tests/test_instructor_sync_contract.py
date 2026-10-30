import json
import inspect
import unittest
import warnings
from unittest.mock import MagicMock, patch

import httpx
import openai
import instructor

import clipper.runtime.config as config
import clipper.core.orchestrator as orchestrator
from clipper.core.schemas import CorteVideo, CortesResponse


SAMPLE_TRANSCRIPT = "[0.00 - 30.00] Welcome to this presentation on deterministic pipelines."
SAMPLE_THINKER_REASONING = (
    "Recomendação editorial: O segmento de 0 a 30s possui gancho excelente e ritmo rápido. "
    "Corte sugerido: [0.00 - 30.00] com retenção nos primeiros 5 segundos."
)
SAMPLE_CORTES_JSON = json.dumps(
    {
        "cortes": [
            {
                "title": "Deterministic Pipelines",
                "description": "High retention hook explaining predictable architecture.",
                "start_time": 0.0,
                "end_time": 30.0,
            }
        ]
    }
)


def build_chat_completion_payload(content: str, model: str = "test-model") -> dict:
    """Builds an OpenAI-compliant ChatCompletion JSON response structure."""
    return {
        "id": "mock-completion-id",
        "object": "chat.completion",
        "created": 1700000000,
        "model": model,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": content,
                },
            }
        ],
        "usage": {
            "prompt_tokens": 50,
            "completion_tokens": 50,
            "total_tokens": 100,
        },
    }


class CloseTrackingOpenAI(openai.OpenAI):
    """Subclass of openai.OpenAI that tracks invocation of the close() method."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.close_call_count = 0

    def close(self) -> None:
        self.close_call_count += 1
        super().close()


def create_mock_transport_handler(respond_callback=None, response_contents=None):
    """
    Creates an httpx transport handler for mock responses.
    Captures intercepted requests in an inspectable list.
    """
    intercepted_requests = []
    responses = list(response_contents or [])

    def handler(request: httpx.Request) -> httpx.Response:
        intercepted_requests.append(request)
        if respond_callback:
            return respond_callback(request)

        body = json.loads(request.content) if request.content else {}
        if responses:
            content = responses.pop(0)
        elif "response_format" in body:
            content = SAMPLE_CORTES_JSON
        else:
            content = SAMPLE_THINKER_REASONING

        return httpx.Response(
            status_code=200,
            json=build_chat_completion_payload(content, model=body.get("model", "test-model")),
        )

    return handler, intercepted_requests


def build_mock_sync_client(
    handler=None,
    base_url: str = "http://localhost:11434/v1",
    api_key: str = "test-key",
) -> CloseTrackingOpenAI:
    """
    Factory creating a CloseTrackingOpenAI instance isolated from network
    using an httpx.MockTransport.
    """
    if handler is None:
        handler, _ = create_mock_transport_handler()

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return CloseTrackingOpenAI(
        api_key=api_key,
        base_url=base_url,
        max_retries=0,
        http_client=http_client,
    )


class InstructorSyncContractTests(unittest.TestCase):
    """
    Architectural contract test suite ensuring synchronous concurrency alignment
    between LangGraph nodes and the Instructor LLM client.
    """

    def test_mock_transport_and_client_fixtures(self):
        """Sanity test verifying that mock transport and close tracking fixtures operate correctly."""
        handler, requests = create_mock_transport_handler()
        client = build_mock_sync_client(handler=handler)

        self.assertIsInstance(client, openai.OpenAI)
        self.assertNotIsInstance(client, openai.AsyncOpenAI)
        self.assertEqual(client.close_call_count, 0)

        response = client.chat.completions.create(
            model="test-model",
            messages=[{"role": "user", "content": "test"}],
        )
        self.assertEqual(len(requests), 1)
        self.assertEqual(response.choices[0].message.content, SAMPLE_THINKER_REASONING)

        client.close()
        self.assertEqual(client.close_call_count, 1)

    def test_mock_client_with_sync_instructor(self):
        """Sanity test verifying that mock client wraps cleanly with synchronous Instructor."""
        handler, requests = create_mock_transport_handler()
        client = build_mock_sync_client(handler=handler)

        instructor_client = instructor.from_openai(client, mode=instructor.Mode.JSON_SCHEMA)
        self.assertIsInstance(instructor_client, instructor.Instructor)

        extraction: CortesResponse = instructor_client.chat.completions.create(
            model="test-model",
            response_model=CortesResponse,
            messages=[{"role": "user", "content": "extract"}],
        )
        self.assertEqual(len(extraction.cortes), 1)
        self.assertEqual(extraction.cortes[0].title, "Deterministic Pipelines")
        self.assertEqual(extraction.cortes[0].start_time, 0.0)
        self.assertEqual(extraction.cortes[0].end_time, 30.0)

        client.close()
        self.assertEqual(client.close_call_count, 1)

    # -------------------------------------------------------------------------
    # User Story 1: Execução Contínua e Previsível do Pipeline (T005 - T007)
    # -------------------------------------------------------------------------

    def test_thinker_node_sync_execution_returns_raciocinio_bruto(self):
        """T005 [US1]: Verify thinker_node executes synchronously and returns raciocinio_bruto dict."""
        handler, requests = create_mock_transport_handler()
        mock_client = build_mock_sync_client(handler=handler)

        with patch.object(orchestrator, "create_llm_client", return_value=mock_client):
            state = {"transcript_grouped": SAMPLE_TRANSCRIPT}
            result = orchestrator.thinker_node(state)

        self.assertIsInstance(result, dict)
        self.assertIn("raciocinio_bruto", result)
        self.assertEqual(result["raciocinio_bruto"], SAMPLE_THINKER_REASONING)
        self.assertFalse(inspect.iscoroutine(result))
        self.assertEqual(mock_client.close_call_count, 1)

    def test_thinker_node_validates_transcript_input(self):
        """T005 [US1]: thinker_node raises ValueError when transcript_grouped is missing or empty."""
        with self.assertRaisesRegex(ValueError, "Transcrição vazia ou ausente"):
            orchestrator.thinker_node({"transcript_grouped": ""})

        with self.assertRaisesRegex(ValueError, "Transcrição vazia ou ausente"):
            orchestrator.thinker_node({})

    def test_extractor_node_sync_execution_returns_cortes_finais(self):
        """T006 [US1]: Verify extractor_node executes synchronously with Instructor returning cortes_finais."""
        handler, requests = create_mock_transport_handler()
        mock_client = build_mock_sync_client(handler=handler)

        with patch.object(orchestrator, "create_llm_client", return_value=mock_client):
            state = {
                "transcript_grouped": SAMPLE_TRANSCRIPT,
                "raciocinio_bruto": SAMPLE_THINKER_REASONING,
            }
            result = orchestrator.extractor_node(state)

        self.assertIsInstance(result, dict)
        self.assertIn("cortes_finais", result)
        self.assertIsInstance(result["cortes_finais"], list)
        self.assertEqual(len(result["cortes_finais"]), 1)
        self.assertEqual(result["cortes_finais"][0]["title"], "Deterministic Pipelines")
        self.assertEqual(result["cortes_finais"][0]["start_time"], 0.0)
        self.assertEqual(result["cortes_finais"][0]["end_time"], 30.0)
        self.assertFalse(inspect.iscoroutine(result))
        self.assertEqual(mock_client.close_call_count, 1)

    def test_extractor_node_validates_reasoning_input(self):
        """T006 [US1]: extractor_node raises ValueError when raciocinio_bruto is missing or empty."""
        with self.assertRaisesRegex(ValueError, "Raciocínio bruto ausente"):
            orchestrator.extractor_node({"transcript_grouped": SAMPLE_TRANSCRIPT, "raciocinio_bruto": ""})

        with self.assertRaisesRegex(ValueError, "Raciocínio bruto ausente"):
            orchestrator.extractor_node({"transcript_grouped": SAMPLE_TRANSCRIPT})

    def test_graph_compilation_and_sync_invoke_emits_zero_coroutine_warnings(self):
        """T007 [US1]: Integration test verifying create_graph compilation and app.invoke emits 0 RuntimeWarning coroutines."""
        with warnings.catch_warnings(record=True) as recorded_warnings:
            warnings.simplefilter("always")

            with patch.object(orchestrator, "create_llm_client", side_effect=build_mock_sync_client), \
                 patch.object(orchestrator, "download_node", return_value={"video_path": "/fake/video.mp4"}), \
                 patch.object(orchestrator, "fatiamento_node", return_value={"audio_chunks": [{"chunk_path": "/fake/c.wav", "offset": 0.0}]}), \
                 patch.object(orchestrator, "transcription_node", return_value={"transcript_grouped": SAMPLE_TRANSCRIPT, "word_timestamps": []}), \
                 patch.object(orchestrator, "preview_node", return_value={"review_directory": "/fake/rev"}), \
                 patch.object(orchestrator, "approval_node", return_value={"approved_cut_ids": [1], "approval_complete": True}), \
                 patch.object(orchestrator, "editor_node", return_value={}):

                workflow = orchestrator.create_graph()
                app = workflow.compile()

                initial_state = {
                    "video_url": "https://youtu.be/dummy",
                    "video_path": "",
                    "audio_chunks": [],
                    "transcript_grouped": "",
                    "word_timestamps": [],
                    "raciocinio_bruto": "",
                    "cortes_finais": [],
                    "review_directory": "",
                    "review_session": "sess1",
                    "approved_cut_ids": [],
                    "approval_complete": False,
                }
                res = app.invoke(initial_state)

            self.assertIsInstance(res, dict)
            self.assertIn("raciocinio_bruto", res)
            self.assertEqual(res["raciocinio_bruto"], SAMPLE_THINKER_REASONING)
            self.assertEqual(len(res.get("cortes_finais", [])), 1)

            coroutine_warnings = [
                w for w in recorded_warnings
                if issubclass(w.category, RuntimeWarning) and "coroutine" in str(w.message).lower()
            ]
            self.assertEqual(len(coroutine_warnings), 0, f"Found unawaited coroutine warnings: {coroutine_warnings}")


if __name__ == "__main__":
    unittest.main()
