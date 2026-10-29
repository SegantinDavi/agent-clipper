import tests
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


class CheckpointThreadIdUserStory2Tests(unittest.TestCase):
    """Unit tests for User Story 2: Retomada Segura com Configuração de Silêncio Diferente (T012, T013, T014)."""

    def test_t012_silence_cut_toggle_isolation(self):
        """T012: Verify thread ID isolates when silence_cut_enabled toggles (True vs False)."""
        thread_enabled = orchestrator.checkpoint_thread_id("vid-silence", silence_cut_enabled=True)
        thread_disabled = orchestrator.checkpoint_thread_id("vid-silence", silence_cut_enabled=False)

        self.assertNotEqual(thread_enabled, thread_disabled)
        self.assertEqual(len(thread_enabled), 16)
        self.assertEqual(len(thread_disabled), 16)
        self.assertRegex(thread_enabled, r"^[0-9a-f]{16}$")
        self.assertRegex(thread_disabled, r"^[0-9a-f]{16}$")

    def test_t013_silence_min_pause_duration_isolation(self):
        """T013: Verify thread ID isolates when silence_min_pause duration changes."""
        thread_06 = orchestrator.checkpoint_thread_id("vid-silence", silence_cut_enabled=True, silence_min_pause=0.6)
        thread_08 = orchestrator.checkpoint_thread_id("vid-silence", silence_cut_enabled=True, silence_min_pause=0.8)
        thread_10 = orchestrator.checkpoint_thread_id("vid-silence", silence_cut_enabled=True, silence_min_pause=1.0)

        self.assertNotEqual(thread_06, thread_08)
        self.assertNotEqual(thread_06, thread_10)
        self.assertNotEqual(thread_08, thread_10)

    def test_t014_silence_boolean_normalization(self):
        """T014: Boolean equivalents must normalize to canonical true or false."""
        expected_true = orchestrator.checkpoint_thread_id("vid-norm", silence_cut_enabled=True)
        for truthy in (True, 1, "1", "true", "True", "TRUE", "yes", "YES"):
            self.assertEqual(
                orchestrator.checkpoint_thread_id("vid-norm", silence_cut_enabled=truthy),
                expected_true,
                f"Failed for truthy value {truthy!r}",
            )

        expected_false = orchestrator.checkpoint_thread_id("vid-norm", silence_cut_enabled=False)
        for falsy in (False, 0, "0", "false", "False", "FALSE", "no", "NO", ""):
            self.assertEqual(
                orchestrator.checkpoint_thread_id("vid-norm", silence_cut_enabled=falsy),
                expected_false,
                f"Failed for falsy value {falsy!r}",
            )

        self.assertNotEqual(expected_true, expected_false)

    def test_t014_silence_float_normalization(self):
        """T014: Float representations must normalize consistently."""
        thread_float = orchestrator.checkpoint_thread_id("vid-norm", silence_min_pause=0.6)
        thread_str = orchestrator.checkpoint_thread_id("vid-norm", silence_min_pause="0.6")
        thread_trailing_zero = orchestrator.checkpoint_thread_id("vid-norm", silence_min_pause=0.60)
        self.assertEqual(thread_float, thread_str)
        self.assertEqual(thread_float, thread_trailing_zero)

        thread_int = orchestrator.checkpoint_thread_id("vid-norm", silence_min_pause=1)
        thread_int_float = orchestrator.checkpoint_thread_id("vid-norm", silence_min_pause=1.0)
        thread_int_str = orchestrator.checkpoint_thread_id("vid-norm", silence_min_pause="1.0")
        self.assertEqual(thread_int, thread_int_float)
        self.assertEqual(thread_int, thread_int_str)

    def test_t014_silence_safe_fallbacks_on_invalid_or_none(self):
        """T014: Invalid or None values must safely fallback without raising exceptions."""
        thread_default = orchestrator.checkpoint_thread_id("vid-norm", silence_min_pause=None)
        self.assertEqual(len(thread_default), 16)

        # Invalid float strings fallback safely to 0.6
        thread_invalid = orchestrator.checkpoint_thread_id("vid-norm", silence_min_pause="not-a-number")
        thread_expected_default = orchestrator.checkpoint_thread_id("vid-norm", silence_min_pause=0.6)
        self.assertEqual(thread_invalid, thread_expected_default)

        # Non-positive values fallback safely to 0.6
        thread_zero = orchestrator.checkpoint_thread_id("vid-norm", silence_min_pause=0)
        thread_negative = orchestrator.checkpoint_thread_id("vid-norm", silence_min_pause=-1.0)
        self.assertEqual(thread_zero, thread_expected_default)
        self.assertEqual(thread_negative, thread_expected_default)

    def test_t014_silence_runtime_patching_isolation(self):
        """T014: Patching PauseSettings dynamically isolates checkpoint thread ID."""
        from clipper.video.pause_editing import PauseSettings

        baseline = orchestrator.checkpoint_thread_id("vid-patch")
        with patch.object(orchestrator, "PauseSettings", return_value=PauseSettings(enabled=False)):
            self.assertNotEqual(baseline, orchestrator.checkpoint_thread_id("vid-patch"))

        with patch.object(orchestrator, "PauseSettings", return_value=PauseSettings(min_pause=1.2)):
            self.assertNotEqual(baseline, orchestrator.checkpoint_thread_id("vid-patch"))


class CheckpointThreadIdUserStory3Tests(unittest.TestCase):
    """Unit and integration tests for User Story 3: Retomada Legítima do Estado (T017, T018, T019)."""

    def test_t017_deterministic_idempotency_across_repeated_invocations(self):
        """T017: Ensure 100% deterministic idempotency across multiple repeated calls."""
        baseline = orchestrator.checkpoint_thread_id(
            video_id="idempotency-vid",
            llm_provider="gemini",
            model_name="gemini-3.6-flash",
            llm_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            silence_cut_enabled=True,
            silence_min_pause=0.6,
        )
        for _ in range(50):
            repeated = orchestrator.checkpoint_thread_id(
                video_id="idempotency-vid",
                llm_provider="gemini",
                model_name="gemini-3.6-flash",
                llm_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                silence_cut_enabled=True,
                silence_min_pause=0.6,
            )
            self.assertEqual(baseline, repeated)

    def test_t018_raw_video_id_preservation_and_url_extraction(self):
        """T018: URL variations of same video extract canonical ID and yield identical thread ID (FR-008)."""
        from clipper.core.ingestion import extract_video_id

        canonical_id = "dQw4w9WgXcQ"
        url_variations = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s&feature=share",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ?si=abcdef123456",
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "dQw4w9WgXcQ",
        ]
        
        expected_thread_id = orchestrator.checkpoint_thread_id(canonical_id)
        for url in url_variations:
            extracted = extract_video_id(url)
            self.assertEqual(extracted, canonical_id, f"Failed extraction for URL: {url}")
            thread_id = orchestrator.checkpoint_thread_id(extracted)
            self.assertEqual(thread_id, expected_thread_id, f"Inconsistent thread_id for URL: {url}")

        # Test non-URL raw identifier preservation
        raw_names = ["custom_test_clip", "video-alpha-123", "local_file.mp4"]
        for raw in raw_names:
            self.assertEqual(extract_video_id(raw), raw)

    def test_t019_sqlite_checkpointer_resumption_and_thread_purge(self):
        """T019: Integration test checkpointer resumption and thread purge with hardened thread ID."""
        import tempfile
        import sqlite3
        from pathlib import Path
        from langgraph.checkpoint.sqlite import SqliteSaver

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "estado.db")
            thread_id = orchestrator.checkpoint_thread_id("integration-test-vid")
            other_thread_id = orchestrator.checkpoint_thread_id("other-test-vid")

            with SqliteSaver.from_conn_string(db_path) as saver:
                saver.setup()
                with saver.conn:
                    saver.conn.execute(
                        "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, type) VALUES (?, '', 'chk-1', 'test')",
                        (thread_id,),
                    )
                    saver.conn.execute(
                        "INSERT INTO writes (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, type) VALUES (?, '', 'chk-1', 'task-1', 0, 'c', 't')",
                        (thread_id,),
                    )
                    saver.conn.execute(
                        "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, type) VALUES (?, '', 'chk-2', 'test')",
                        (other_thread_id,),
                    )

                # Verify records exist before purge
                with sqlite3.connect(db_path) as conn:
                    chk_count = conn.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (thread_id,)).fetchone()[0]
                    writes_count = conn.execute("SELECT COUNT(*) FROM writes WHERE thread_id = ?", (thread_id,)).fetchone()[0]
                    other_count = conn.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (other_thread_id,)).fetchone()[0]
                self.assertEqual(chk_count, 1)
                self.assertEqual(writes_count, 1)
                self.assertEqual(other_count, 1)

                # Purge target thread (simulating --restart)
                orchestrator.purge_thread_checkpoints(saver, thread_id)

                # Verify target thread records are 0 while other thread remains intact
                with sqlite3.connect(db_path) as conn:
                    chk_count_after = conn.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (thread_id,)).fetchone()[0]
                    writes_count_after = conn.execute("SELECT COUNT(*) FROM writes WHERE thread_id = ?", (thread_id,)).fetchone()[0]
                    other_count_after = conn.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (other_thread_id,)).fetchone()[0]
                self.assertEqual(chk_count_after, 0)
                self.assertEqual(writes_count_after, 0)
                self.assertEqual(other_count_after, 1)


if __name__ == "__main__":
    unittest.main()
