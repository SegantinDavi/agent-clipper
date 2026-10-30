import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from clipper.core.ingestion import apply_chunk_offset
from clipper.core.orchestrator import transcription_node
from clipper.video.editor import group_caption_words
from clipper.video.pause_editing import (
    PausePlan,
    PauseSettings,
    TimeInterval,
    build_pause_plan,
    remap_word_groups,
    speech_intervals,
)


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


class TestPauseEditingMultiChunkIntegration(unittest.TestCase):
    """Integration tests for pause editing with multi-chunk absolute timestamps (US2, T011, T012)."""

    def test_speech_intervals_filters_multi_chunk_words_accurately(self):
        """speech_intervals correctly isolates words in multi-chunk cuts without chunk 0 bleeding (T011, FR-007)."""
        words = [
            # Chunk 0 words:
            {"word": "Inicio", "start": 5.0, "end": 6.0},
            {"word": "chunk0", "start": 10.0, "end": 12.0},
            # Chunk 1 words (offset +720.0s):
            {"word": "Fala1", "start": 725.0, "end": 728.0},
            {"word": "Fala2", "start": 735.0, "end": 740.0},
        ]
        # Cut located strictly in Chunk 1: [720.0s, 750.0s]
        cut_start = 720.0
        cut_end = 750.0

        intervals = speech_intervals(words, cut_start, cut_end)
        self.assertEqual(len(intervals), 2)
        # Verify intervals are mapped relative to cut_start:
        self.assertAlmostEqual(intervals[0].start, 5.0)  # 725.0 - 720.0
        self.assertAlmostEqual(intervals[0].end, 8.0)    # 728.0 - 720.0
        self.assertAlmostEqual(intervals[1].start, 15.0) # 735.0 - 720.0
        self.assertAlmostEqual(intervals[1].end, 20.0)   # 740.0 - 720.0

    @patch("clipper.video.pause_editing.detect_silences")
    def test_build_pause_plan_with_multi_chunk_absolute_cut(self, mock_detect_silences):
        """build_pause_plan creates valid PausePlan referencing absolute cut coordinates (T011, SC-004)."""
        words = [
            {"word": "Fala1", "start": 725.0, "end": 728.0},
            {"word": "Fala2", "start": 735.0, "end": 740.0},
        ]
        cut_start = 720.0
        cut_end = 750.0
        # Silence detected between 8.5s and 14.5s relative to cut start
        mock_detect_silences.return_value = [TimeInterval(start=8.5, end=14.5)]

        settings = PauseSettings(
            enabled=True,
            min_pause=0.6,
            keep_pause=0.2,
            speech_padding=0.1,
            threshold_db=-30.0,
        )
        plan = build_pause_plan("mock_video.mp4", cut_start, cut_end, words, settings)

        self.assertEqual(plan.source_start, 720.0)
        self.assertEqual(plan.source_end, 750.0)
        self.assertTrue(len(plan.kept) > 1)
        # Kept intervals should trim silence and plan.duration should be strictly less than cut duration
        self.assertLess(plan.duration, 30.0)
        # validate_cut against exact source boundaries should pass
        plan.validate_cut(720.0, 750.0)

    def test_pauses_json_serialization_and_restart_persistence(self):
        """PausePlan serialization to .pauses.json preserves multi-chunk absolute coordinates across restarts (T012, FR-007)."""
        settings = PauseSettings(
            enabled=True,
            min_pause=0.6,
            keep_pause=0.2,
            speech_padding=0.1,
            threshold_db=-30.0,
        )
        plan = PausePlan(
            source_start=720.0,
            source_end=760.0,
            settings=settings,
            kept=[
                TimeInterval(start=0.0, end=15.0),
                TimeInterval(start=20.0, end=40.0),
            ],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_mp4 = Path(tmp_dir) / "approved_cut_001.mp4"
            pauses_path = output_mp4.with_suffix(".pauses.json")

            # Emulate editor.py serialization
            pauses_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
            self.assertTrue(pauses_path.exists())

            # Emulate restart deserialization and validation
            reloaded_plan = PausePlan.model_validate_json(pauses_path.read_text(encoding="utf-8"))
            self.assertEqual(reloaded_plan.source_start, 720.0)
            self.assertEqual(reloaded_plan.source_end, 760.0)
            self.assertEqual(len(reloaded_plan.kept), 2)
            self.assertAlmostEqual(reloaded_plan.duration, 35.0)

            # Validates against original cut
            reloaded_plan.validate_cut(720.0, 760.0)

            # Mismatched cut restart fails explicitly
            with self.assertRaises(ValueError) as ctx:
                reloaded_plan.validate_cut(0.0, 40.0)
            self.assertIn("approved source cut", str(ctx.exception))


class TestCaptionGroupingContinuity(unittest.TestCase):
    """Unit tests for caption grouping continuity and drift across chunk boundaries (US3, T014, T015)."""

    def test_group_caption_words_across_chunk_boundary(self):
        """group_caption_words preserves chronological continuity across chunk transitions (T014, FR-005)."""
        words = [
            # Chunk 0 words:
            {"word": "final", "start": 718.5, "end": 719.8},
            # Chunk 1 words (offset 720.0s applied):
            {"word": "começo", "start": 720.2, "end": 721.0},
            {"word": "frase", "start": 721.2, "end": 722.5},
        ]
        cut_start = 715.0
        cut_end = 725.0
        groups = group_caption_words(words, cut_start, cut_end)

        self.assertTrue(len(groups) >= 1)
        for group in groups:
            self.assertGreaterEqual(group["start"], 0.0)
            self.assertGreater(group["end"], group["start"])

        # Successive groups must not have negative gaps
        for prev, foll in zip(groups, groups[1:]):
            self.assertGreaterEqual(foll["start"], prev["end"])

    def test_remap_word_groups_across_chunk_boundary(self):
        """remap_word_groups cleanly maps words across chunk transitions without backward jumps (T014)."""
        words = [
            {"word": "final", "start": 718.5, "end": 719.8},
            {"word": "começo", "start": 720.2, "end": 721.0},
            {"word": "frase", "start": 721.2, "end": 722.5},
        ]
        settings = PauseSettings(
            enabled=True, min_pause=0.6, keep_pause=0.2, speech_padding=0.1, threshold_db=-30.0
        )
        plan = PausePlan(
            source_start=715.0,
            source_end=725.0,
            settings=settings,
            kept=[TimeInterval(start=0.0, end=10.0)],
        )
        remapped_groups = remap_word_groups(words, plan)
        self.assertEqual(len(remapped_groups), 1)
        remapped_words = remapped_groups[0]
        self.assertEqual(len(remapped_words), 3)
        self.assertEqual(remapped_words[0]["word"], "final")
        self.assertEqual(remapped_words[1]["word"], "começo")
        self.assertEqual(remapped_words[2]["word"], "frase")

        # Chronological progression
        self.assertLess(remapped_words[0]["start"], remapped_words[1]["start"])
        self.assertLess(remapped_words[1]["start"], remapped_words[2]["start"])

    def test_caption_sync_drift_within_tolerance(self):
        """Word timestamp remapping drift across multiple chunk boundaries is <= 0.1s (T015, SC-002)."""
        chunk_boundaries = [
            (0, 0.0),       # Chunk 0
            (1, 720.0),     # Chunk 1
            (2, 1440.0),    # Chunk 2
            (3, 2160.0),    # Chunk 3
        ]
        relative_words = [
            {"word": "palavra_a", "start": 1.25, "end": 1.85},
            {"word": "palavra_b", "start": 5.40, "end": 6.10},
            {"word": "palavra_c", "start": 12.00, "end": 12.75},
        ]

        max_drift = 0.0
        for chunk_idx, offset in chunk_boundaries:
            remapped = apply_chunk_offset(relative_words, offset=offset, chunk_index=chunk_idx)
            for orig, rem in zip(relative_words, remapped):
                drift_start = abs((rem["start"] - offset) - orig["start"])
                drift_end = abs((rem["end"] - offset) - orig["end"])
                max_drift = max(max_drift, drift_start, drift_end)

        self.assertLessEqual(max_drift, 0.10, f"Max drift {max_drift}s exceeds 0.1s limit (SC-002)")
        self.assertLessEqual(max_drift, 0.01)


if __name__ == "__main__":
    unittest.main()
