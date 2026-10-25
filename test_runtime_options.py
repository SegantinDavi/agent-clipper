import contextlib
import importlib
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import config
import runtime_options


class RuntimeOptionsTests(unittest.TestCase):
    def configure(self, args, answers=(), interactive=True, environment=None):
        with patch.dict(os.environ, environment or {}, clear=True), \
             patch.object(runtime_options, "load_dotenv"), \
             patch.object(runtime_options.sys.stdin, "isatty", return_value=interactive), \
             patch("builtins.input", side_effect=answers) as prompt, \
             contextlib.redirect_stdout(io.StringIO()):
            runtime_options.configure_runtime(args)
            return dict(os.environ), prompt.call_count

    def test_local_menu_retries_invalid_choice_then_sets_model_and_url(self):
        environment, count = self.configure([], ["invalid", "2", "", "video"])
        self.assertEqual(environment["LLM_PROVIDER"], "ollama")
        self.assertEqual(environment["OLLAMA_MODEL"], "qwen2.5:14b")
        self.assertEqual(environment["YOUTUBE_URL"], "video")
        self.assertNotIn("GEMINI_API_KEY", environment)
        self.assertEqual(count, 4)

    def test_gemini_menu_defaults_and_hidden_key(self):
        with patch.object(runtime_options.getpass, "getpass", return_value="secret") as hidden:
            environment, _ = self.configure([], ["", "", ""], environment={"YOUTUBE_URL": "video"})
        self.assertEqual(environment["LLM_PROVIDER"], "gemini")
        self.assertEqual(environment["GEMINI_API_KEY"], "secret")
        self.assertEqual(environment["YOUTUBE_URL"], "video")
        hidden.assert_called_once()

    def test_cli_wins_without_prompts(self):
        environment, count = self.configure(
            ["--provider", "ollama", "--model", "chosen", "--url", "video"],
            environment={"LLM_PROVIDER": "gemini", "OLLAMA_MODEL": "old"},
        )
        self.assertEqual(count, 0)
        self.assertEqual(environment["OLLAMA_MODEL"], "chosen")
        self.assertEqual(environment["LLM_PROVIDER"], "ollama")

    def test_noninteractive_and_no_tty_never_prompt(self):
        for args, interactive in [(["--non-interactive"], True), ([], False)]:
            with self.subTest(args=args):
                environment, count = self.configure(args, interactive=interactive)
                self.assertEqual(count, 0)
                self.assertEqual(environment["LLM_PROVIDER"], "gemini")

    def test_cuda_reexecution_preserves_menu_selection(self):
        environment, count = self.configure([], environment={
            "_CLIPPER_RUNTIME_SELECTED": "1", "LLM_PROVIDER": "ollama", "OLLAMA_MODEL": "chosen",
        })
        self.assertEqual(count, 0)
        self.assertEqual(environment["OLLAMA_MODEL"], "chosen")

    def test_eof_and_keyboard_interrupt_cancel(self):
        for error in (EOFError, KeyboardInterrupt):
            with self.subTest(error=error), self.assertRaisesRegex(SystemExit, "cancelada"):
                self.configure([], [error])

    def test_invalid_environment_provider_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "LLM_PROVIDER"):
            self.configure([], interactive=False, environment={"LLM_PROVIDER": "unknown"})

    def test_profile_enforces_hardware_despite_legacy_exports(self):
        try:
            for provider, device, precision in [("ollama", "cpu", "int8"), ("gemini", "cuda", "float16")]:
                with self.subTest(provider=provider), patch.dict(os.environ, {
                    "LLM_PROVIDER": provider, "WHISPER_DEVICE": "stale", "WHISPER_COMPUTE_TYPE": "stale",
                    "GEMINI_API_KEY": "", "OLLAMA_MODEL": "qwen2.5:14b",
                }), patch("dotenv.load_dotenv"):
                    importlib.reload(config)
                    self.assertEqual((config.WHISPER_DEVICE, config.WHISPER_COMPUTE_TYPE), (device, precision))
                    if provider == "ollama":
                        config.validate_llm_config()
                    else:
                        with self.assertRaisesRegex(ValueError, "GEMINI_API_KEY"):
                            config.validate_llm_config()
        finally:
            importlib.reload(config)

    def test_help_needs_neither_cuda_nor_credentials(self):
        environment = os.environ.copy()
        environment.update({"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": ""})
        environment.pop("LD_LIBRARY_PATH", None)
        result = subprocess.run(
            [sys.executable, "orchestrator.py", "--help"],
            cwd=Path(__file__).parent, env=environment,
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--provider", result.stdout)


if __name__ == "__main__":
    unittest.main()
