from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import ingestion


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

    def test_cuda_transcription_preserves_segment_and_word_timestamps(self):
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


if __name__ == "__main__":
    unittest.main()
