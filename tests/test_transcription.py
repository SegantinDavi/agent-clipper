import tests
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import clipper.core.ingestion as ingestion


class TranscriptionTests(unittest.TestCase):
    def run_transcription(self, fail=False):
        iterator_closed = []

        def segments():
            try:
                yield SimpleNamespace(
                    start=1.0, end=2.0, text="Example",
                    words=[SimpleNamespace(word="Example", start=1.0, end=2.0)],
                )
                if fail:
                    raise RuntimeError("Decoding failed")
            finally:
                iterator_closed.append(True)

        model = MagicMock()
        model.transcribe.return_value = (segments(), None)
        with patch.object(ingestion, "WHISPER_DEVICE", "cuda"):
            with patch.object(ingestion, "WHISPER_COMPUTE_TYPE", "float16"):
                with patch.object(ingestion, "WhisperModel", return_value=model) as constructor:
                    with patch.object(ingestion.gc, "collect") as collect:
                        result = ingestion.transcribe_audio_chunk("example.wav")
                        constructor.assert_called_once_with(
                            "small", device="cuda", compute_type="float16"
                        )
                        collect.assert_called_once()
        self.assertEqual(iterator_closed, [True])
        return result

    def test_gpu_transcription_preserves_segment_and_word_timestamps(self):
        result = self.run_transcription()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["transcript"], "[1.00 - 2.00] Example ")
        self.assertEqual(result["word_timestamps"], [
            {"word": "Example", "start": 1.0, "end": 2.0},
        ])

    def test_failed_decode_cleans_up(self):
        result = self.run_transcription(fail=True)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["message"], "Decoding failed")

    def test_explicit_cpu_configuration_remains_available(self):
        model = MagicMock()
        model.transcribe.return_value = ((segment for segment in []), None)
        with patch.object(ingestion, "WHISPER_DEVICE", "cpu"), \
             patch.object(ingestion, "WHISPER_COMPUTE_TYPE", "int8"), \
             patch.object(ingestion, "WhisperModel", return_value=model) as constructor:
            result = ingestion.transcribe_audio_chunk("example.wav")
        self.assertEqual(result["status"], "success")
        constructor.assert_called_once_with("small", device="cpu", compute_type="int8")

    def test_lazy_generator_safe_closure_and_ctranslate2_model_unload(self):
        """T006: In finally block, safe closure of lazy generator and unload_model call on CTranslate2 model."""
        ct2_model = MagicMock()
        model = MagicMock()
        model.model = ct2_model

        closed = []

        def failing_gen():
            try:
                yield MagicMock(start=0.0, end=1.0, text="hi", words=[])
                raise RuntimeError("Abrupt fail")
            finally:
                closed.append(True)

        model.transcribe.return_value = (failing_gen(), None)

        with patch.object(ingestion, "WHISPER_DEVICE", "cuda"), \
             patch.object(ingestion, "WhisperModel", return_value=model), \
             patch.object(ingestion, "release_cuda_memory") as mock_release, \
             patch.object(ingestion, "get_gpu_memory_info", return_value=(500.0, 11500.0, 12000.0)):
            result = ingestion.transcribe_audio_chunk("example.wav")

        self.assertEqual(result["status"], "error")
        self.assertEqual(closed, [True])
        ct2_model.unload_model.assert_called_once()
        mock_release.assert_called_once_with(before_mb=500.0)

    def test_non_generator_segments_does_not_raise_attribute_error(self):
        """T006: If segments is not a generator (no close method), does not raise AttributeError."""
        model = MagicMock()
        model.model = MagicMock()
        # segments is a plain list, which does not have .close()
        model.transcribe.return_value = ([], None)

        with patch.object(ingestion, "WHISPER_DEVICE", "cuda"), \
             patch.object(ingestion, "WhisperModel", return_value=model), \
             patch.object(ingestion, "release_cuda_memory"):
            result = ingestion.transcribe_audio_chunk("example.wav")

        self.assertEqual(result["status"], "success")
        model.model.unload_model.assert_called_once()


if __name__ == "__main__":
    unittest.main()
