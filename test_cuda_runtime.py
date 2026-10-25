"""Opt-in GPU smoke test: bash run_pipeline.sh -m unittest test_cuda_runtime -v."""

import gc
import os
from pathlib import Path
import subprocess
import sys
import unittest

import ctranslate2
import numpy as np
from faster_whisper import WhisperModel


class CudaRuntimeTests(unittest.TestCase):
    def test_direct_orchestrator_initializes_cuda_without_loader_exports(self):
        environment = os.environ.copy()
        environment.pop("LD_LIBRARY_PATH", None)
        environment["WHISPER_DEVICE"] = "cuda"
        environment["WHISPER_COMPUTE_TYPE"] = "float16"
        result = subprocess.run(
            [sys.executable, "orchestrator.py", "--help"],
            cwd=Path(__file__).parent, env=environment,
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--restart", result.stdout)

    def test_cached_model_transcribes_silence_on_gpu(self):
        self.assertGreater(ctranslate2.get_cuda_device_count(), 0)
        model = WhisperModel(
            "small", device="cuda", compute_type="float16", local_files_only=True,
        )
        try:
            self.assertEqual(model.model.device, "cuda")
            segments, _ = model.transcribe(
                np.zeros(16000, dtype=np.float32), language="en", word_timestamps=True,
            )
            list(segments)
        finally:
            del model
            gc.collect()


if __name__ == "__main__":
    unittest.main()
