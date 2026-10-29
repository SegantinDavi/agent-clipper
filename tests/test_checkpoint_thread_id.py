import re
import unittest
from unittest.mock import patch

import clipper.runtime.config as config
import clipper.core.orchestrator as orchestrator


class CheckpointThreadIdUserStory1Tests(unittest.TestCase):
    """Unit tests for User Story 1: Retomada Segura em Perfil Diferente (T006, T007, T008)."""

    def test_t006_format_and_16_hex_length(self):
        """T006: Verify 16-hex lowercase format and length."""
        thread_id = orchestrator.checkpoint_thread_id("video-123")
        self.assertEqual(len(thread_id), 16)
        self.assertRegex(thread_id, r"^[0-9a-f]{16}$")

    def test_t006_provider_isolation(self):
        """T006: Verify distinct thread IDs when switching providers (ollama vs gemini)."""
        thread_ollama = orchestrator.checkpoint_thread_id(
            video_id="test-vid",
            llm_provider="ollama",
            model_name="qwen2.5:14b",
            llm_base_url="http://localhost:11434/v1",
        )
        thread_gemini = orchestrator.checkpoint_thread_id(
            video_id="test-vid",
            llm_provider="gemini",
            model_name="qwen2.5:14b",
            llm_base_url="http://localhost:11434/v1",
        )
        self.assertNotEqual(thread_ollama, thread_gemini)
        self.assertEqual(len(thread_ollama), 16)
        self.assertEqual(len(thread_gemini), 16)

    def test_t006_provider_case_normalization(self):
        """T006: Provider name should be case-insensitive (GEMINI vs gemini)."""
        thread_upper = orchestrator.checkpoint_thread_id("vid", llm_provider="GEMINI")
        thread_lower = orchestrator.checkpoint_thread_id("vid", llm_provider="gemini")
        thread_mixed = orchestrator.checkpoint_thread_id("vid", llm_provider="  Gemini  ")
        self.assertEqual(thread_upper, thread_lower)
        self.assertEqual(thread_upper, thread_mixed)

    def test_t007_model_name_isolation(self):
        """T007: Verify distinct thread IDs when changing model names."""
        thread_m1 = orchestrator.checkpoint_thread_id(
            video_id="test-vid",
            llm_provider="gemini",
            model_name="gemini-3.6-flash",
        )
        thread_m2 = orchestrator.checkpoint_thread_id(
            video_id="test-vid",
            llm_provider="gemini",
            model_name="gemini-1.5-pro",
        )
        self.assertNotEqual(thread_m1, thread_m2)

    def test_t007_endpoint_isolation_and_normalization(self):
        """T007: Verify distinct endpoints yield distinct thread IDs, and trailing slashes normalize."""
        thread_local = orchestrator.checkpoint_thread_id(
            video_id="test-vid",
            llm_provider="ollama",
            model_name="qwen2.5:14b",
            llm_base_url="http://localhost:11434/v1",
        )
        thread_remote = orchestrator.checkpoint_thread_id(
            video_id="test-vid",
            llm_provider="ollama",
            model_name="qwen2.5:14b",
            llm_base_url="http://192.168.1.100:11434/v1",
        )
        self.assertNotEqual(thread_local, thread_remote)

        # Trailing slash normalization
        thread_slash = orchestrator.checkpoint_thread_id(
            video_id="test-vid",
            llm_provider="ollama",
            model_name="qwen2.5:14b",
            llm_base_url="http://localhost:11434/v1/",
        )
        self.assertEqual(thread_local, thread_slash)

    def test_t008_default_fallbacks_when_parameters_are_none(self):
        """T008: None parameters must fallback to runtime config defaults."""
        default_thread = orchestrator.checkpoint_thread_id("test-vid")
        explicit_none_thread = orchestrator.checkpoint_thread_id(
            video_id="test-vid",
            llm_provider=None,
            model_name=None,
            llm_base_url=None,
        )
        self.assertEqual(default_thread, explicit_none_thread)

    def test_t008_fallback_picks_up_runtime_config_changes(self):
        """T008: Fallback should dynamically resolve from orchestrator/config attributes."""
        baseline = orchestrator.checkpoint_thread_id("test-vid")
        with patch.object(orchestrator, "LLM_PROVIDER", "ollama"):
            thread_with_patched_provider = orchestrator.checkpoint_thread_id("test-vid")
            self.assertNotEqual(baseline, thread_with_patched_provider)

        with patch.object(orchestrator, "MODEL_NAME", "custom-model"):
            thread_with_patched_model = orchestrator.checkpoint_thread_id("test-vid")
            self.assertNotEqual(baseline, thread_with_patched_model)

        with patch.object(orchestrator, "LLM_BASE_URL", "http://custom-endpoint:8000"):
            thread_with_patched_endpoint = orchestrator.checkpoint_thread_id("test-vid")
            self.assertNotEqual(baseline, thread_with_patched_endpoint)


if __name__ == "__main__":
    unittest.main()
