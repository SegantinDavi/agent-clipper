from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from moviepy.editor import AudioClip, VideoClip, VideoFileClip

from editor import cut_and_format_video
from schemas import CorteVideo
from speaker_focus import (
    FaceTracker, FramingPlan, SpeakerSelector, face_crop,
    intersection_over_union, lock_static_crops, portrait_size,
)


class SpeakerFocusTests(unittest.TestCase):
    def test_crop_stays_in_bounds_with_even_output_dimensions(self):
        for frame in ((1920, 1080), (1080, 1920), (640, 360), (401, 721)):
            width, height = portrait_size(frame)
            self.assertEqual(width % 2, 0)
            self.assertEqual(height % 2, 0)
            for face in (None, [0, 0, 80, 100], [frame[0] - 90, frame[1] - 100, 80, 100]):
                x, y, crop_width, crop_height = face_crop(frame, face)
                self.assertGreaterEqual(x, 0)
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(x + crop_width, frame[0] + 0.001)
                self.assertLessEqual(y + crop_height, frame[1] + 0.001)
                self.assertAlmostEqual(crop_width / crop_height, width / height)

    def test_face_tracking_matches_positions_and_resets_at_camera_cuts(self):
        tracker = FaceTracker()
        tracker.update([[10, 20, 50, 60], [200, 20, 50, 60]], 0)
        tracker.update([[202, 20, 50, 60], [12, 20, 50, 60]], 0.2)
        self.assertEqual([face["id"] for face in tracker.visible(0.2)], [0, 1])
        self.assertEqual(tracker.tracks[0]["box"][0], 12)
        tracker.update([[12, 20, 50, 60]], 0.3)
        self.assertEqual([face["id"] for face in tracker.visible(0.3)], [0])
        tracker.update([[12, 20, 50, 60]], 0.4, scene_cut=True)
        self.assertEqual(tracker.visible(0.4)[0]["id"], 2)
        self.assertEqual(tracker.visible(1), [])
        self.assertEqual(intersection_over_union([0, 0, 1, 1], [2, 2, 1, 1]), 0)

    def test_static_crop_does_not_follow_motion_or_temporary_face_loss(self):
        boxes = [[500, 300, 125, 176], [530, 310, 130, 180], None,
                 [550, 320, 140, 190]]
        samples = [{"face_box": box, "reset": index == 0}
                   for index, box in enumerate(boxes)]
        locked = lock_static_crops((1920, 1080), samples)
        self.assertTrue(all(sample["rect"] == locked[0]["rect"] for sample in locked))
        x, y, width, height = locked[0]["rect"]
        for box in boxes:
            if box:
                self.assertLessEqual(x, box[0])
                self.assertGreaterEqual(x + width, box[0] + box[2])
                self.assertLessEqual(y, box[1])
                self.assertGreaterEqual(y + height, box[1] + box[3])

    def test_static_crop_changes_only_at_speaker_or_source_shot_boundaries(self):
        samples = [
            {"face_box": [100, 200, 100, 150], "reset": True},
            {"face_box": [120, 210, 105, 150], "reset": False},
            {"face_box": [1300, 200, 100, 150], "reset": True},
            {"face_box": [1310, 210, 100, 150], "reset": False},
            {"face_box": [700, 100, 200, 250], "reset": True},
        ]
        locked = lock_static_crops((1920, 1080), samples)
        self.assertEqual(locked[0]["rect"], locked[1]["rect"])
        self.assertEqual(locked[2]["rect"], locked[3]["rect"])
        self.assertNotEqual(locked[1]["rect"], locked[2]["rect"])
        self.assertNotEqual(locked[3]["rect"], locked[4]["rect"])

    def test_smaller_active_speaker_wins_over_larger_listener(self):
        selector = SpeakerSelector()
        faces = [{"id": 0, "box": [0, 0, 300, 300], "score": -2},
                 {"id": 1, "box": [400, 0, 100, 100], "score": 3}]
        self.assertEqual(selector.choose(faces, 0)["id"], 1)
        silent = [{**face, "score": -3} for face in faces]
        self.assertEqual(selector.choose(silent, 1)["id"], 1)
        self.assertIsNone(selector.choose([], 2))

    def test_speaker_switch_requires_confirmation_but_camera_cut_resets(self):
        selector = SpeakerSelector()
        first = {"id": 0, "box": [0, 0, 100, 100], "score": 3}
        second = {"id": 1, "box": [400, 0, 100, 100], "score": -1}
        self.assertEqual(selector.choose([first, second], 0)["id"], 0)
        changed = [{**first, "score": -1}, {**second, "score": 3}]
        self.assertEqual(selector.choose(changed, 0.1)["id"], 0)
        self.assertEqual(selector.choose(changed, 0.2)["id"], 0)
        self.assertEqual(selector.choose(changed, 0.5)["id"], 1)
        self.assertEqual(selector.choose([first, second], 0.6, scene_cut=True)["id"], 0)

    def test_framing_uses_direct_cuts_without_interpolation(self):
        samples = [{"rect": [0, 0, 100, 200], "reset": True},
                   {"rect": [100, 0, 100, 200], "reset": False}]
        plan = FramingPlan((640, 360), samples)
        self.assertEqual(plan.rectangle_at(0.02)[0], 0)
        samples[1]["reset"] = True
        self.assertEqual(plan.rectangle_at(0.02)[0], 0)
        self.assertEqual(plan.rectangle_at(0.04)[0], 100)

    def test_dynamic_export_preserves_audio_and_moves_between_people(self):
        Path("output").mkdir(exist_ok=True)
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        frame[:, :320] = [230, 20, 20]
        frame[:, 320:] = [20, 20, 230]
        samples = []
        for index in range(50):
            face = [70, 90, 80, 100] if index < 25 else [470, 90, 80, 100]
            samples.append({"rect": face_crop((640, 360), face), "reset": index in (0, 25)})
        plan = FramingPlan((640, 360), samples)
        with tempfile.TemporaryDirectory(dir="output") as directory:
            source_path = str(Path(directory) / "source.mp4")
            audio = AudioClip(lambda time: 0.1 * np.sin(2 * np.pi * 220 * time),
                              duration=2, fps=16000)
            with VideoClip(lambda time: frame, duration=2).set_audio(audio) as source:
                source.write_videofile(source_path, fps=25, codec="libx264", audio_codec="aac", logger=None)
            with patch("editor.SPEAKER_FOCUS_ENABLED", True), \
                 patch("speaker_focus.build_framing_plan", return_value=plan):
                outputs = cut_and_format_video(
                    source_path, [CorteVideo(title="Focus test", start_time=0, end_time=2)],
                    [{"word": "Pessoa,", "start": 0.1, "end": 0.7}], directory,
                )
            with VideoFileClip(outputs[0]) as result:
                self.assertEqual(tuple(result.size), (202, 360))
                self.assertAlmostEqual(result.duration, 2, delta=0.1)
                self.assertIsNotNone(result.audio)
                first = result.get_frame(0.5)[:100].mean(axis=(0, 1))
                second = result.get_frame(1.5)[:100].mean(axis=(0, 1))
                self.assertGreater(first[0], first[2] + 100)
                self.assertGreater(second[2], second[0] + 100)
                self.assertGreater(np.max(np.abs(result.audio.get_frame(0.531))), 0.01)


if __name__ == "__main__":
    unittest.main()
