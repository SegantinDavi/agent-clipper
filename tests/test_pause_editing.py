import tests
import math
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from moviepy.editor import AudioClip, VideoClip, VideoFileClip

from clipper.video.editor import cut_and_format_video, group_caption_words
from clipper.video.pause_editing import (
    PausePlan, PauseSettings, TimeInterval, build_pause_plan, detect_silences,
    identity_plan, parse_silences, plan_from_silences, remap_word_groups, speech_intervals,
)
from clipper.review.review import ReviewManifest, load_review_plans, prepare_review, render_review_page
from clipper.core.schemas import CorteVideo
from clipper.video.speaker_focus import FramingPlan, face_crop
import clipper.core.orchestrator as orchestrator


class PauseMathTests(unittest.TestCase):
    def setUp(self):
        self.settings = PauseSettings()
        self.words = [{"word": "First", "start": 10, "end": 11},
                      {"word": "Second", "start": 12.5, "end": 13.5},
                      {"word": "Third", "start": 15, "end": 16}]

    def test_only_confirmed_gaps_are_shortened_and_clip_edges_survive(self):
        speech = speech_intervals(self.words, 9, 17)
        plan = plan_from_silences(9, 17, speech, [TimeInterval(start=2, end=3.5)], self.settings)
        self.assertAlmostEqual(plan.removed_seconds, 1.3)
        self.assertEqual(plan.kept[0].start, 0)
        self.assertEqual(plan.kept[-1].end, 8)
        self.assertAlmostEqual(plan.kept[0].end, 2.1)
        self.assertAlmostEqual(plan.kept[1].start, 3.4)
        self.assertEqual(plan, PausePlan.model_validate_json(plan.model_dump_json()))

    def test_short_pauses_and_loud_untranscribed_events_remain(self):
        speech = [TimeInterval(start=0, end=1), TimeInterval(start=1.5, end=2)]
        plan = plan_from_silences(0, 3, speech, [TimeInterval(start=1, end=1.5)], self.settings)
        self.assertEqual(plan.removed_seconds, 0)
        speech = [TimeInterval(start=0, end=1), TimeInterval(start=3, end=4)]
        plan = plan_from_silences(0, 4, speech, [], self.settings)
        self.assertEqual(plan.removed_seconds, 0)

    def test_multiple_edits_remap_caption_words_without_crossing_jumps(self):
        speech = speech_intervals(self.words, 10, 16)
        plan = plan_from_silences(10, 16, speech, [TimeInterval(start=1, end=2.5),
                                                              TimeInterval(start=3.5, end=5)], self.settings)
        groups = remap_word_groups(self.words, plan)
        self.assertEqual(len(groups), 3)
        self.assertAlmostEqual(plan.duration, 3.4)
        self.assertAlmostEqual(groups[1][0]["start"], 1.2)
        self.assertAlmostEqual(groups[2][0]["start"], 2.4)
        captions = [group for words in groups for group in group_caption_words(words, 0, plan.duration)]
        self.assertEqual([group["text"] for group in captions], ["First", "Second", "Third"])

    def test_overlapping_speakers_merge_and_protect_quiet_words(self):
        words = [{"word": "A", "start": 0, "end": 1.5},
                 {"word": "B", "start": 1, "end": 2},
                 {"word": "quiet", "start": 2.3, "end": 2.7},
                 {"word": "C", "start": 4, "end": 5}]
        speech = speech_intervals(words, 0, 5)
        self.assertEqual(speech[0], TimeInterval(start=0, end=2))
        plan = plan_from_silences(0, 5, speech, [TimeInterval(start=2, end=4)], self.settings)
        mapped = [word for group in remap_word_groups(words, plan) for word in group]
        quiet = next(word for word in mapped if word["word"] == "quiet")
        self.assertAlmostEqual(quiet["end"] - quiet["start"], 0.4)
        self.assertAlmostEqual(plan.kept[0].end, 2.8)

    def test_boundaries_padding_and_partial_silence(self):
        settings = PauseSettings(min_pause=0.6, keep_pause=0.3, speech_padding=0.2)
        speech = [TimeInterval(start=0, end=1), TimeInterval(start=1.6, end=2)]
        plan = plan_from_silences(0, 2, speech, [TimeInterval(start=1, end=1.6)], settings)
        self.assertAlmostEqual(plan.removed_seconds, 0.2)
        plan = plan_from_silences(0, 2, speech, [TimeInterval(start=1.25, end=1.35)], settings)
        self.assertAlmostEqual(plan.removed_seconds, 0.1)

    def test_invalid_missing_words_and_disabled_mode_skip_ffmpeg(self):
        for words, enabled in [([], True), ([{"word": "bad", "start": math.nan, "end": 1}], True),
                               ([{"word": "bad"}], True), (self.words, False)]:
            with self.subTest(words=words), patch("clipper.video.pause_editing.detect_silences") as detect:
                plan = build_pause_plan("unused", 9, 17, words, PauseSettings(enabled=enabled))
                detect.assert_not_called()
                self.assertEqual(plan.duration, 8)

    def test_zero_length_words_outside_cut_do_not_disable_valid_pauses(self):
        words = [{"word": "outside", "start": 0, "end": 0}, *self.words,
                 {"word": "outside", "start": 100, "end": 99}]
        self.assertEqual(speech_intervals(words, 10, 16), speech_intervals(self.words, 10, 16))
        self.assertEqual(speech_intervals([*self.words, {"word": "uncertain", "start": 12, "end": 12}], 10, 16), [])

    def test_settings_and_malformed_saved_plans_are_rejected(self):
        for values in [{"min_pause": 0}, {"keep_pause": 0.6}, {"speech_padding": 0.3},
                       {"threshold_db": math.nan}, {"min_pause": math.inf}, {"threshold_db": 0}]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                PauseSettings(**values)
        for intervals in [[(1, 3)], [(0, 2), (1, 3)], [(0, 4)]]:
            with self.subTest(intervals=intervals), self.assertRaises(ValueError):
                PausePlan(source_start=0, source_end=3, settings=self.settings,
                          kept=[TimeInterval(start=start, end=end) for start, end in intervals])
        with self.assertRaisesRegex(ValueError, "approved source cut"):
            identity_plan(0, 2, self.settings).validate_cut(0, 3)

    def test_trailing_silence_and_nonzero_cut_offsets_parse(self):
        intervals = parse_silences("silence_start: -0.01\nsilence_end: 0.4\n"
                                  "silence_start: 1.8\nsilence_end: 2.5\nsilence_start: 3.2", 4)
        self.assertEqual([(part.start, part.end) for part in intervals], [(0, 0.4), (1.8, 2.5), (3.2, 4)])
        self.assertEqual(parse_silences("silence_start: 6.25e-05\nsilence_end: 1", 2)[0].start, 0.0000625)

    def test_ffmpeg_failures_do_not_silently_change_editing_policy(self):
        with patch("clipper.video.pause_editing.has_audio", return_value=True), \
             patch("clipper.video.pause_editing.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "decode failed")):
            with self.assertRaisesRegex(RuntimeError, "decode failed"):
                detect_silences("source", 0, 5, self.settings)

    def test_settings_are_part_of_checkpoint_identity(self):
        before = orchestrator.checkpoint_thread_id("video")
        self.assertEqual(len(before), 16)
        self.assertRegex(before, r"^[0-9a-f]{16}$")
        with patch.object(orchestrator, "PauseSettings", return_value=PauseSettings(enabled=False)):
            after = orchestrator.checkpoint_thread_id("video")
            self.assertEqual(len(after), 16)
            self.assertRegex(after, r"^[0-9a-f]{16}$")
            self.assertNotEqual(before, after)


class PauseMediaTests(unittest.TestCase):
    def setUp(self):
        Path("output").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir="output")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source_path = str(self.root / "source.mp4")
        self.cut = CorteVideo(title="Pause test", start_time=1, end_time=5)
        self.words = [{"word": "First.", "start": 1.2, "end": 2},
                      {"word": "Second.", "start": 3.5, "end": 4.3}]

        def audio_frame(time):
            time = np.asarray(time)
            active = ((time >= 1) & (time < 2)) | ((time >= 3.5) & (time < 4.5))
            return 0.3 * np.sin(2 * np.pi * 220 * time) * active

        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[:, :160] = [230, 20, 20]
        frame[:, 160:] = [20, 20, 230]
        audio = AudioClip(audio_frame, duration=6, fps=16000)
        try:
            with VideoClip(lambda time: frame, duration=6).set_audio(audio) as source:
                source.write_videofile(self.source_path, fps=25, codec="libx264", audio_codec="aac", logger=None)
        finally:
            audio.close()

    def test_real_detection_preview_and_focused_render_share_plan_and_timing(self):
        directory = prepare_review(self.source_path, [self.cut], str(self.root), word_timestamps=self.words)
        plans = load_review_plans(directory, [self.cut])
        plan = plans[0]
        self.assertAlmostEqual(plan.duration, 2.7, delta=0.04)
        self.assertEqual(len(plan.kept), 2)
        self.assertIn("Após cortes de silêncio: 2.7s", render_review_page([self.cut], "token", plans))
        samples = [{"rect": face_crop((320, 240), [20 if index < 50 else 240, 50, 40, 60]),
                    "reset": index in (0, 50)} for index in range(100)]
        focus = FramingPlan((320, 240), samples)
        with patch("clipper.video.editor.SPEAKER_FOCUS_ENABLED", True), \
             patch("clipper.video.speaker_focus.build_framing_plan", return_value=focus), \
             patch("clipper.video.pause_editing.detect_silences", side_effect=AssertionError("Approved plan must be reused")):
            outputs = cut_and_format_video(self.source_path, [self.cut], self.words, str(self.root), pause_plans=plans)
        with VideoFileClip(str(Path(directory) / "preview-1.mp4")) as preview, VideoFileClip(outputs[0]) as result:
            self.assertAlmostEqual(preview.duration, plan.duration, delta=0.12)
            self.assertAlmostEqual(result.duration, plan.duration, delta=0.08)
            self.assertAlmostEqual(preview.duration, result.duration, delta=0.12)
            self.assertIsNotNone(result.audio)
            for clip in (preview, result):
                for time in (0.43, 1.33):
                    self.assertGreater(np.max(np.abs(clip.audio.get_frame(time))), 0.02)
                self.assertAlmostEqual(clip.audio.duration, clip.duration, delta=0.08)
            first = result.get_frame(0.4)[:70].mean(axis=(0, 1))
            second = result.get_frame(1.4)[:70].mean(axis=(0, 1))
            self.assertGreater(first[0], first[2] + 100)
            self.assertGreater(second[2], second[0] + 100)
            frame = result.get_frame(1.4)
            self.assertTrue(np.any((frame[:, :, 1] > 150) & (frame[:, :, 0] < 110) & (frame[:, :, 2] < 110)))
        saved = PausePlan.model_validate_json(Path(outputs[0]).with_suffix(".pauses.json").read_text())
        self.assertEqual(saved, plan)

    def test_disabled_preview_preserves_duration_and_review_identity_changes(self):
        with patch("clipper.video.pause_editing.detect_silences", side_effect=AssertionError("Disabled")):
            disabled = prepare_review(self.source_path, [self.cut], str(self.root),
                word_timestamps=self.words, pause_settings=PauseSettings(enabled=False))
        enabled = prepare_review(self.source_path, [self.cut], str(self.root), word_timestamps=self.words)
        self.assertNotEqual(enabled, disabled)
        with VideoFileClip(str(Path(disabled) / "preview-1.mp4")) as preview:
            self.assertAlmostEqual(preview.duration, 4, delta=0.1)

    def test_review_plans_are_required_and_selection_is_preserved(self):
        directory = prepare_review(self.source_path, [self.cut], str(self.root), word_timestamps=self.words)
        state = {"approval_complete": True, "approved_cut_ids": [1], "video_path": self.source_path,
                 "cortes_finais": [self.cut.model_dump()], "word_timestamps": self.words,
                 "review_directory": directory}
        with patch.object(orchestrator, "cut_and_format_video", return_value=[]) as render:
            orchestrator.editor_node(state)
        self.assertEqual(render.call_args.kwargs["pause_plans"], load_review_plans(directory, [self.cut]))
        (Path(directory) / "review.json").write_text(ReviewManifest(cuts=[self.cut]).model_dump_json())
        with self.assertRaisesRegex(ValueError, "missing"):
            orchestrator.editor_node(state)

    def test_two_final_clips_share_source_reader_safely(self):
        cuts = [self.cut, self.cut.model_copy(update={"title": "Second export"})]
        plan = build_pause_plan(self.source_path, 1, 5, self.words, PauseSettings())
        with patch("clipper.video.editor.SPEAKER_FOCUS_ENABLED", False):
            outputs = cut_and_format_video(self.source_path, cuts, self.words, str(self.root),
                                          pause_plans=[plan, plan])
        self.assertEqual(len(outputs), 2)
        for path in outputs:
            with VideoFileClip(path) as result:
                self.assertAlmostEqual(result.duration, plan.duration, delta=0.08)

    def test_missing_audio_keeps_the_original_timeline(self):
        silent_path = str(self.root / "no-audio.mp4")
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", self.source_path,
                        "-an", "-c:v", "copy", silent_path], check=True)
        plan = build_pause_plan(silent_path, 1, 5, self.words, PauseSettings())
        self.assertEqual(plan.duration, 4)

    def test_many_pauses_do_not_accumulate_preview_audio_video_drift(self):
        duration = 12
        words = [{"word": f"word{index}", "start": index * 1.5, "end": index * 1.5 + 0.5}
                 for index in range(8)]

        def audio_frame(time):
            time = np.asarray(time)
            return 0.3 * np.sin(2 * np.pi * 220 * time) * ((time % 1.5) < 0.5)

        source_path = str(self.root / "many-pauses.mp4")
        audio = AudioClip(audio_frame, duration=duration, fps=16000)
        try:
            with VideoClip(lambda time: np.full((120, 160, 3), 70, dtype=np.uint8), duration=duration).set_audio(audio) as source:
                source.write_videofile(source_path, fps=25, codec="libx264", audio_codec="aac", logger=None)
        finally:
            audio.close()
        cut = CorteVideo(title="Many pauses", start_time=0, end_time=duration)
        directory = prepare_review(source_path, [cut], str(self.root), word_timestamps=words)
        plan = load_review_plans(directory, [cut])[0]
        self.assertEqual(len(plan.kept), 8)
        self.assertAlmostEqual(plan.duration, 6.4, delta=0.1)
        with patch("clipper.video.editor.SPEAKER_FOCUS_ENABLED", False):
            paths = cut_and_format_video(source_path, [cut], words, str(self.root), pause_plans=[plan])
        with VideoFileClip(str(Path(directory) / "preview-1.mp4")) as preview, VideoFileClip(paths[0]) as final:
            self.assertAlmostEqual(preview.duration, plan.duration, delta=0.08)
            self.assertAlmostEqual(final.duration, plan.duration, delta=0.08)
            for word in [group[0] for group in remap_word_groups(words, plan) if group]:
                center = word["start"] + 0.213
                for clip in (preview, final):
                    self.assertGreater(np.max(np.abs(clip.audio.get_frame(center))), 0.02)


if __name__ == "__main__":
    unittest.main()
