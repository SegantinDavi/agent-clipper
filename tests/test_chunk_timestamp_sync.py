import logging
import unittest
from unittest.mock import MagicMock, patch

from clipper.core.ingestion import apply_chunk_offset
from clipper.core.orchestrator import transcription_node


class TestChunkTimestampSyncScaffolding(unittest.TestCase):
    """Scaffold fixtures and mocks for chunk timestamp absolute sync tests."""

    def setUp(self):
        """Prepare reusable test fixtures for multi-chunk word timestamps."""
        self.sample_words_chunk_0 = [
            {"word": "Olá", "start": 0.50, "end": 1.20},
            {"word": "mundo", "start": 1.30, "end": 2.00},
        ]
        self.sample_words_chunk_1 = [
            {"word": "Segunda", "start": 0.10, "end": 0.80},
            {"word": "parte", "start": 0.90, "end": 1.50},
        ]
        self.sample_audio_chunks = [
            {"chunk_path": "/fake/audio_chunk_000.wav", "offset": 0.0},
            {"chunk_path": "/fake/audio_chunk_001.wav", "offset": 720.0},
        ]

    def test_scaffold_fixture_initialization(self):
        """Verify test scaffold fixtures are correctly configured."""
        self.assertEqual(len(self.sample_words_chunk_0), 2)
        self.assertEqual(len(self.sample_words_chunk_1), 2)
        self.assertEqual(len(self.sample_audio_chunks), 2)
        self.assertEqual(self.sample_audio_chunks[1]["offset"], 720.0)


class TestApplyChunkOffsetContract(unittest.TestCase):
    """Unit tests for apply_chunk_offset pure function contract (T005)."""

    def test_empty_list_returns_empty_list(self):
        """apply_chunk_offset with empty words returns a new empty list."""
        result = apply_chunk_offset([], offset=10.0, chunk_index=0)
        self.assertEqual(result, [])

    def test_zero_offset_returns_identical_values(self):
        """apply_chunk_offset with offset 0.0 returns equal timestamps."""
        words = [{"word": "teste", "start": 1.23, "end": 2.34}]
        result = apply_chunk_offset(words, offset=0.0, chunk_index=0)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["word"], "teste")
        self.assertEqual(result[0]["start"], 1.23)
        self.assertEqual(result[0]["end"], 2.34)

    def test_positive_offset_rounding(self):
        """apply_chunk_offset with positive offset shifts timestamps with 2 decimal rounding."""
        words = [{"word": "offset", "start": 0.101, "end": 0.809}]
        result = apply_chunk_offset(words, offset=720.0, chunk_index=1)
        self.assertEqual(result[0]["start"], 720.10)
        self.assertEqual(result[0]["end"], 720.81)

    def test_immutability_input_not_mutated(self):
        """apply_chunk_offset does not mutate input dictionaries or input list."""
        original_dict = {"word": "original", "start": 1.0, "end": 2.0}
        words = [original_dict]
        result = apply_chunk_offset(words, offset=100.0, chunk_index=2)

        self.assertIsNot(result, words)
        self.assertIsNot(result[0], original_dict)
        self.assertEqual(original_dict["start"], 1.0)
        self.assertEqual(original_dict["end"], 2.0)
        self.assertEqual(result[0]["start"], 101.0)
        self.assertEqual(result[0]["end"], 102.0)

    def test_preserves_additional_metadata_fields(self):
        """apply_chunk_offset preserves extra metadata keys from Whisper (FR-002)."""
        words = [
            {"word": "meta", "start": 1.0, "end": 2.0, "confidence": 0.98, "speaker": "A"}
        ]
        result = apply_chunk_offset(words, offset=10.0, chunk_index=0)
        self.assertEqual(result[0]["confidence"], 0.98)
        self.assertEqual(result[0]["speaker"], "A")
        self.assertEqual(result[0]["start"], 11.0)
        self.assertEqual(result[0]["end"], 12.0)

    def test_negative_offset_raises_value_error(self):
        """apply_chunk_offset raises ValueError if offset < 0.0."""
        with self.assertRaises(ValueError) as ctx:
            apply_chunk_offset([{"word": "a", "start": 1.0, "end": 2.0}], offset=-5.0, chunk_index=0)
        self.assertIn("offset", str(ctx.exception).lower())


class TestApplyChunkOffsetLogging(unittest.TestCase):
    """Unit tests for apply_chunk_offset structured INFO logging (T006)."""

    def test_structured_info_logging_format(self):
        """apply_chunk_offset emits formatted INFO log per contract."""
        words = [
            {"word": "um", "start": 0.1, "end": 0.5},
            {"word": "dois", "start": 0.6, "end": 1.0},
        ]
        with self.assertLogs("clipper.core.ingestion", level="INFO") as log_capture:
            apply_chunk_offset(words, offset=720.0, chunk_index=1)

        expected_msg = "Chunk 1 offset applied: +720.00s → 2 words remapped"
        self.assertTrue(
            any(expected_msg in record for record in log_capture.output),
            f"Expected '{expected_msg}' in logs: {log_capture.output}",
        )


class TestTranscriptionNodeAggregation(unittest.TestCase):
    """Unit tests for transcription_node aggregation and retrocompatibility (T007)."""

    @patch("clipper.core.orchestrator.transcribe_audio_chunk")
    def test_single_chunk_retrocompatibility(self, mock_transcribe):
        """Single-chunk videos retain offset 0.0s and produce identical word timestamps (FR-008, SC-003)."""
        mock_transcribe.return_value = {
            "status": "success",
            "transcript": "[0.50 - 2.00] Olá mundo",
            "word_timestamps": [
                {"word": "Olá", "start": 0.50, "end": 1.20},
                {"word": "mundo", "start": 1.30, "end": 2.00},
            ],
        }
        state = {
            "video_path": "video.mp4",
            "audio_chunks": [{"chunk_path": "chunk_0.wav", "offset": 0.0}],
        }
        output = transcription_node(state)
        mock_transcribe.assert_called_once_with("chunk_0.wav")
        self.assertEqual(
            output["word_timestamps"],
            [
                {"word": "Olá", "start": 0.50, "end": 1.20},
                {"word": "mundo", "start": 1.30, "end": 2.00},
            ],
        )

    @patch("clipper.core.orchestrator.transcribe_audio_chunk")
    def test_multi_chunk_timestamp_offset_aggregation(self, mock_transcribe):
        """Multi-chunk videos aggregate words with absolute offsets applied (FR-001, FR-003, SC-001)."""
        mock_transcribe.side_effect = [
            {
                "status": "success",
                "transcript": "[0.50 - 2.00] Olá mundo",
                "word_timestamps": [
                    {"word": "Olá", "start": 0.50, "end": 1.20},
                    {"word": "mundo", "start": 1.30, "end": 2.00},
                ],
            },
            {
                "status": "success",
                "transcript": "[0.10 - 1.50] Segunda parte",
                "word_timestamps": [
                    {"word": "Segunda", "start": 0.10, "end": 0.80},
                    {"word": "parte", "start": 0.90, "end": 1.50},
                ],
            },
        ]
        state = {
            "video_path": "video.mp4",
            "audio_chunks": [
                {"chunk_path": "chunk_0.wav", "offset": 0.0},
                {"chunk_path": "chunk_1.wav", "offset": 720.0},
            ],
        }
        output = transcription_node(state)
        self.assertEqual(mock_transcribe.call_count, 2)
        words = output["word_timestamps"]
        self.assertEqual(len(words), 4)
        # Chunk 0 words:
        self.assertEqual(words[0]["word"], "Olá")
        self.assertEqual(words[0]["start"], 0.50)
        self.assertEqual(words[0]["end"], 1.20)
        # Chunk 1 words:
        self.assertEqual(words[2]["word"], "Segunda")
        self.assertEqual(words[2]["start"], 720.10)
        self.assertEqual(words[2]["end"], 720.80)
        self.assertEqual(words[3]["word"], "parte")
        self.assertEqual(words[3]["start"], 720.90)
        self.assertEqual(words[3]["end"], 721.50)


class TestTranscriptionNodeValidation(unittest.TestCase):
    """Unit tests for transcription_node fail-fast validation (T008, FR-010)."""

    def test_non_dict_chunk_raises_value_error(self):
        """transcription_node raises ValueError when chunk is not a dict."""
        state = {
            "video_path": "video.mp4",
            "audio_chunks": ["not_a_dict.wav"],
        }
        with self.assertRaises(ValueError) as ctx:
            transcription_node(state)
        self.assertIn("dict", str(ctx.exception).lower())

    def test_missing_offset_raises_value_error(self):
        """transcription_node raises ValueError when chunk dict lacks 'offset'."""
        state = {
            "video_path": "video.mp4",
            "audio_chunks": [{"chunk_path": "chunk_0.wav"}],
        }
        with self.assertRaises(ValueError) as ctx:
            transcription_node(state)
        self.assertIn("offset", str(ctx.exception).lower())

    def test_negative_offset_raises_value_error(self):
        """transcription_node raises ValueError when chunk offset < 0.0."""
        state = {
            "video_path": "video.mp4",
            "audio_chunks": [{"chunk_path": "chunk_0.wav", "offset": -10.0}],
        }
        with self.assertRaises(ValueError) as ctx:
            transcription_node(state)
        self.assertIn("offset", str(ctx.exception).lower())

    def test_missing_chunk_path_raises_value_error(self):
        """transcription_node raises ValueError when chunk dict lacks 'chunk_path'."""
        state = {
            "video_path": "video.mp4",
            "audio_chunks": [{"offset": 0.0}],
        }
        with self.assertRaises(ValueError) as ctx:
            transcription_node(state)
        self.assertIn("chunk_path", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
