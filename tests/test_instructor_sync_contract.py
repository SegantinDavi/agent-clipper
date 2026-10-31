import asyncio
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


def is_async_coroutine_function(fn) -> bool:
    """Wrapper auditing asyncio.iscoroutinefunction while filtering Python 3.14+ DeprecationWarning."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return asyncio.iscoroutinefunction(fn)


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

    # -------------------------------------------------------------------------
    # User Story 2: Blindagem e Verificação de Conformidade Arquitetural (T010 - T012)
    # -------------------------------------------------------------------------

    def test_graph_nodes_are_synchronous_contract(self):
        """T010 [US2]: Contract test auditing 100% of nodes in create_graph (AC-01, FR-001, FR-007, SC-001)."""
        workflow = orchestrator.create_graph()

        expected_nodes = {
            "download",
            "fatiamento",
            "transcricao",
            "pensador",
            "extrator",
            "preview",
            "approval",
            "editor",
        }
        self.assertTrue(
            expected_nodes.issubset(workflow.nodes.keys()),
            f"Missing required nodes in graph: {expected_nodes - set(workflow.nodes.keys())}",
        )

        for node_name, node_spec in workflow.nodes.items():
            runnable = getattr(node_spec, "runnable", node_spec)
            fn = getattr(runnable, "func", None)

            self.assertIsNotNone(
                fn,
                f"Node '{node_name}' does not define a synchronous callable (func is None).",
            )
            self.assertTrue(
                callable(fn),
                f"Node '{node_name}' target {fn} is not callable.",
            )
            self.assertFalse(
                inspect.iscoroutinefunction(fn),
                f"Node '{node_name}' ({fn.__name__}) must not be an inspect.iscoroutinefunction.",
            )
            self.assertFalse(
                is_async_coroutine_function(fn),
                f"Node '{node_name}' ({fn.__name__}) must not be an asyncio.iscoroutinefunction.",
            )
            self.assertFalse(
                inspect.isasyncgenfunction(fn),
                f"Node '{node_name}' ({fn.__name__}) must not be an async generator function.",
            )

        # Directly audit the individual node functions
        individual_nodes = [
            orchestrator.download_node,
            orchestrator.fatiamento_node,
            orchestrator.transcription_node,
            orchestrator.thinker_node,
            orchestrator.extractor_node,
            orchestrator.preview_node,
            orchestrator.approval_node,
            orchestrator.editor_node,
        ]
        for fn in individual_nodes:
            self.assertFalse(inspect.iscoroutinefunction(fn), f"{fn.__name__} must be synchronous")
            self.assertFalse(is_async_coroutine_function(fn), f"{fn.__name__} must be synchronous")

    def test_create_graph_rejects_async_node(self):
        """T010 [US2]: Contract test asserting create_graph fails fast if an async node is registered."""
        async def dummy_async_node(state):
            return {}

        with patch.object(orchestrator, "download_node", dummy_async_node):
            with self.assertRaisesRegex(TypeError, "must be a synchronous function"):
                orchestrator.create_graph()

    def test_create_llm_client_returns_strict_sync_openai_instance(self):
        """T011 [US2]: Contract test asserting create_llm_client returns openai.OpenAI and not AsyncOpenAI (AC-02, FR-002, FR-008)."""
        with patch.object(orchestrator, "LLM_API_KEY", "test-key"), \
             patch.object(orchestrator, "LLM_BASE_URL", "http://localhost:11434/v1"):
            client = orchestrator.create_llm_client()

        try:
            self.assertIsInstance(client, openai.OpenAI)
            self.assertNotIsInstance(client, openai.AsyncOpenAI)
            self.assertFalse(hasattr(client, "__await__"))
            self.assertFalse(inspect.iscoroutinefunction(client.chat.completions.create))
            self.assertFalse(is_async_coroutine_function(client.chat.completions.create))
            self.assertTrue(hasattr(client, "close") and callable(client.close))
        finally:
            client.close()

        # Contract assertion: create_llm_client raises TypeError if an async or invalid client is instantiated
        fake_async_client = openai.AsyncOpenAI(api_key="test-key")
        with patch.object(orchestrator, "LLM_API_KEY", "test-key"), \
             patch.object(orchestrator, "LLM_BASE_URL", "http://localhost:11434/v1"), \
             patch.object(openai, "OpenAI", return_value=fake_async_client):
            with self.assertRaisesRegex(TypeError, "must return an instance of openai.OpenAI and not AsyncOpenAI"):
                orchestrator.create_llm_client()

        with patch.object(orchestrator, "LLM_API_KEY", "test-key"), \
             patch.object(orchestrator, "LLM_BASE_URL", "http://localhost:11434/v1"), \
             patch.object(openai, "OpenAI", return_value="invalid_client_object"):
            with self.assertRaisesRegex(TypeError, "must return an instance of openai.OpenAI"):
                orchestrator.create_llm_client()

    def test_instructor_from_openai_wraps_into_synchronous_instructor(self):
        """T012 [US2]: Contract test asserting instructor.from_openai wraps openai.OpenAI into synchronous Instructor (AC-03, FR-003)."""
        handler, _ = create_mock_transport_handler()
        client = build_mock_sync_client(handler=handler)

        try:
            instructor_client = instructor.from_openai(client, mode=instructor.Mode.JSON_SCHEMA)

            self.assertIsInstance(instructor_client, instructor.Instructor)
            self.assertNotIsInstance(instructor_client, instructor.AsyncInstructor)
            self.assertFalse(inspect.iscoroutinefunction(instructor_client.chat.completions.create))
            self.assertFalse(is_async_coroutine_function(instructor_client.chat.completions.create))
            self.assertIs(instructor_client.client, client)
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
