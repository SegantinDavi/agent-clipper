import sys
import unittest
from unittest.mock import MagicMock, call, patch

import clipper.runtime.cuda_runtime as cuda_runtime
from clipper.runtime.cuda_runtime import get_gpu_memory_info, release_cuda_memory
import clipper.core.ingestion as ingestion


class CudaCleanupTests(unittest.TestCase):
    def test_release_cuda_memory_purges_pytorch_cache_when_loaded(self):
        """T005: release_cuda_memory flushes torch cuda empty_cache and ipc_collect."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True

        with patch.object(cuda_runtime, "WHISPER_DEVICE", "cuda"):
            with patch.dict(sys.modules, {"torch": mock_torch}):
                release_cuda_memory()

        mock_torch.cuda.empty_cache.assert_called_once()
        mock_torch.cuda.ipc_collect.assert_called_once()

    def test_multi_chunk_sequential_execution_no_retention(self):
        """T007: Multiple chunks sequentially transcribe without unclosed handles or cumulative retention."""
        chunks = ["chunk_0.wav", "chunk_1.wav", "chunk_2.wav"]
        unloaded_models = []
        closed_generators = []
        cleanup_calls = []

        def mock_whisper_factory(*args, **kwargs):
            mock_model = MagicMock()
            ct2_model = MagicMock()
            ct2_model.unload_model.side_effect = lambda: unloaded_models.append(True)
            mock_model.model = ct2_model

            def gen():
                try:
                    yield MagicMock(start=0.0, end=1.0, text="test", words=[])
                finally:
                    closed_generators.append(True)

            mock_model.transcribe.return_value = (gen(), None)
            return mock_model

        with patch.object(ingestion, "WHISPER_DEVICE", "cuda"):
            with patch.object(ingestion, "WhisperModel", side_effect=mock_whisper_factory):
                with patch.object(ingestion, "release_cuda_memory", side_effect=lambda **kw: cleanup_calls.append(kw)):
                    with patch.object(ingestion, "get_gpu_memory_info", return_value=(1000.0, 11000.0, 12000.0)):
                        for chunk in chunks:
                            res = ingestion.transcribe_audio_chunk(chunk)
                            self.assertEqual(res["status"], "success")

        # Each chunk must trigger an unload, a generator close, and a release_cuda_memory call
        self.assertEqual(len(unloaded_models), 3)
        self.assertEqual(len(closed_generators), 3)
        self.assertEqual(len(cleanup_calls), 3)
        for call_kw in cleanup_calls:
            self.assertEqual(call_kw.get("before_mb"), 1000.0)

    def test_structured_info_logging_with_nvml_metrics(self):
        """T010: Structured INFO log with before/after/freed MB when NVML metrics are available."""
        with patch.object(cuda_runtime, "WHISPER_DEVICE", "cuda"):
            with patch.object(cuda_runtime, "get_gpu_memory_info", return_value=(1200.0, 11000.0, 12200.0)):
                with patch.object(cuda_runtime.logger, "info") as mock_info:
                    release_cuda_memory(before_mb=1500.0)
                    mock_info.assert_called_once_with(
                        "GPU memory flushed successfully: before=%.1f MB, after=%.1f MB (freed=%.1f MB)",
                        1500.0,
                        1200.0,
                        300.0,
                    )

    def test_structured_info_logging_without_nvml_metrics(self):
        """T010: Fallback confirmation INFO log when NVML metrics are unavailable."""
        with patch.object(cuda_runtime, "WHISPER_DEVICE", "cuda"):
            with patch.object(cuda_runtime, "get_gpu_memory_info", return_value=None):
                with patch.object(cuda_runtime.logger, "info") as mock_info:
                    release_cuda_memory(before_mb=None)
                    mock_info.assert_called_once_with("GPU memory flushed successfully.")

    def test_exception_handling_logs_warning_and_does_not_propagate(self):
        """T011: When an unexpected exception occurs, log WARNING and suppress error."""
        faulty_torch = MagicMock()
        faulty_torch.cuda.is_available.return_value = True
        faulty_torch.cuda.empty_cache.side_effect = RuntimeError("CUDA driver hardware fault")

        with patch.object(cuda_runtime, "WHISPER_DEVICE", "cuda"):
            with patch.dict(sys.modules, {"torch": faulty_torch}):
                with patch.object(cuda_runtime.logger, "warning") as mock_warn:
                    # Must not raise RuntimeError
                    release_cuda_memory()
                    mock_warn.assert_called_once()
                    self.assertIn("GPU memory cleanup failed", mock_warn.call_args[0][0])



if __name__ == "__main__":
    unittest.main()
