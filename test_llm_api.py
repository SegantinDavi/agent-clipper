import ast
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
import openai

import config
import orchestrator


class LlmApiTests(unittest.TestCase):
    def test_missing_key_is_rejected(self):
        with patch.object(config, "GEMINI_API_KEY", ""):
            with self.assertRaisesRegex(ValueError, "GEMINI_API_KEY"):
                orchestrator.create_llm_client()

    def test_placeholder_key_is_rejected(self):
        with patch.object(config, "GEMINI_API_KEY", "COLE_SUA_API_KEY_AQUI"):
            with self.assertRaisesRegex(ValueError, "GEMINI_API_KEY"):
                orchestrator.create_llm_client()

    def test_client_uses_gemini_endpoint_and_hardcoded_key(self):
        with patch.object(config, "GEMINI_API_KEY", "test-only"):
            with patch.object(orchestrator, "GEMINI_API_KEY", "test-only"):
                with orchestrator.create_llm_client() as client:
                    self.assertEqual(client.api_key, "test-only")
                    self.assertEqual(str(client.base_url), config.GEMINI_BASE_URL)

    def test_nodes_use_model_and_strict_schema(self):
        requests = []

        def respond(request):
            import json

            body = json.loads(request.content)
            self.assertEqual(request.url.host, "generativelanguage.googleapis.com")
            requests.append(body)
            content = (
                '{"cortes":[{"title":"Example","description":"A story about validation.","start_time":0,"end_time":30}]}'
                if "response_format" in body
                else "CORTE [0 - 30]: A complete story with a clear hook."
            )
            return httpx.Response(200, json={
                "id": "test", "object": "chat.completion", "created": 0,
                "model": "gemini-3.6-flash",
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": content}}],
            })

        def client():
            return openai.OpenAI(
                api_key="test-only", base_url=config.GEMINI_BASE_URL, max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(respond)),
            )

        with patch.object(orchestrator, "create_llm_client", side_effect=client):
            state = {"transcript_grouped": "[0 - 30] Example story."}
            state.update(orchestrator.thinker_node(state))
            result = orchestrator.extractor_node(state)

        self.assertEqual(result["cortes_finais"][0]["end_time"], 30)
        self.assertEqual(result["cortes_finais"][0]["description"], "A story about validation.")
        self.assertEqual(len(requests), 2)
        for request in requests:
            self.assertEqual(request["model"], config.MODEL_NAME)
            self.assertNotIn("temperature", request)
            self.assertNotIn("tools", request)
            self.assertEqual(request["max_tokens"], config.LLM_MAX_COMPLETION_TOKENS)
        schema = requests[1]["response_format"]
        self.assertEqual(schema["type"], "json_schema")
        self.assertTrue(schema["json_schema"]["strict"])

    def test_empty_thinker_response_fails(self):
        from unittest.mock import MagicMock

        client = MagicMock()
        client.chat.completions.create.return_value.choices[0].message.content = ""
        with patch.object(orchestrator, "create_llm_client", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "no editorial"):
                orchestrator.thinker_node({"transcript_grouped": "Example"})
        client.close.assert_called_once()

    def test_no_valid_cuts_skip_preview_approval_and_render(self):
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={
                "id": "test", "object": "chat.completion", "created": 0,
                "model": config.MODEL_NAME,
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": '{"cortes":[]}'}}],
            })

        client = openai.OpenAI(
            api_key="test-only", base_url=config.GEMINI_BASE_URL, max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(respond)),
        )
        state = {
            "transcript_grouped": "[0 - 5] Obrigado por assistir.",
            "raciocinio_bruto": "SEM CORTES VÁLIDOS: duração insuficiente.",
        }
        with patch.object(orchestrator, "create_llm_client", return_value=client):
            state.update(orchestrator.extractor_node(state))

        self.assertEqual(len(requests), 1)
        self.assertEqual(state["cortes_finais"], [])
        with patch.object(orchestrator, "prepare_review") as preview, \
             patch.object(orchestrator, "interrupt") as approval, \
             patch.object(orchestrator, "cut_and_format_video") as render:
            state.update(orchestrator.preview_node(state))
            state.update(orchestrator.approval_node(state))
            result = orchestrator.editor_node(state)
        self.assertEqual(result, {})
        self.assertTrue(state["approval_complete"])
        self.assertEqual(state["approved_cut_ids"], [])
        preview.assert_not_called()
        approval.assert_not_called()
        render.assert_not_called()

    def test_python_sources_parse(self):
        for path in Path(__file__).parent.glob("*.py"):
            ast.parse(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
