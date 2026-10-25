"""Opt-in GPU smoke test: bash run_pipeline.sh -m unittest test_cuda_runtime -v."""

import gc
import unittest

import ctranslate2
import numpy as np
from faster_whisper import WhisperModel


class CudaRuntimeTests(unittest.TestCase):
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
