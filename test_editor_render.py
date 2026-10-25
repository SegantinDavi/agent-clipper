import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from moviepy.editor import ColorClip, VideoFileClip

from editor import (
    create_caption_clip, cut_and_format_video, group_caption_words,
    position_caption_clip,
)
from schemas import CorteVideo


class EditorRenderTests(unittest.TestCase):
    def test_caption_has_transparency_fill_and_outline_without_imagemagick(self):
        # Only font discovery may spawn a process; text rendering must stay in Pillow.
        from editor import load_caption_font

        load_caption_font()
        with patch("subprocess.run", side_effect=AssertionError("Unexpected subprocess")):
            with create_caption_clip("Olá @teste 100% ação!") as clip:
                frame = clip.get_frame(0)
                mask = clip.mask.get_frame(0)
                self.assertTrue(np.any(mask == 0))
                self.assertTrue(np.any(mask == 1))
                self.assertTrue(np.any(np.all(frame == [37, 230, 0], axis=-1)))
                self.assertTrue(np.any(np.all(frame == [0, 0, 0], axis=-1) & (mask > 0)))

    def test_phrase_grouping_respects_words_pauses_and_sentence_endings(self):
        words = [
            {"word": " pra", "start": 0, "end": 0.2},
            {"word": " maior", "start": 0.2, "end": 0.4},
            {"word": " parte", "start": 0.4, "end": 0.6},
            {"word": " funciona.", "start": 0.6, "end": 0.8},
            {"word": " Outra", "start": 0.8, "end": 1.0},
            {"word": " ideia", "start": 2.0, "end": 2.2},
        ]
        groups = group_caption_words(words, 0, 3)
        self.assertEqual([group["text"] for group in groups], [
            "pra maior parte", "funciona.", "Outra", "ideia",
        ])
        self.assertEqual(groups[0], {"text": "pra maior parte", "start": 0, "end": 0.6})

    def test_phrase_times_are_clipped_to_cut_boundaries_and_duration(self):
        words = [
            {"word": "fora", "start": 8, "end": 9},
            {"word": "primeira", "start": 9.8, "end": 10.3},
            {"word": "segunda", "start": 10.3, "end": 11.7},
            {"word": "terceira", "start": 11.7, "end": 12.4},
            {"word": "última", "start": 12.4, "end": 14},
            {"word": "fora", "start": 14, "end": 15},
        ]
        groups = group_caption_words(words, 10, 13)
        self.assertEqual([group["text"] for group in groups], [
            "primeira segunda", "terceira última",
        ])
        self.assertEqual(groups[0]["start"], 0)
        self.assertEqual(groups[-1]["end"], 3)
        self.assertTrue(all(group["end"] - group["start"] <= 2 for group in groups))

    def test_caption_fits_safe_width_and_keeps_reference_position(self):
        for width, height in ((270, 480), (1080, 1920)):
            with self.subTest(width=width), create_caption_clip(
                "Extraordinariamente compreensível", frame_width=width,
            ) as caption:
                self.assertLessEqual(caption.w, int(width * 0.9))
                positioned = position_caption_clip(caption, (width, height))
                x, y = positioned.pos(0)
                self.assertAlmostEqual(x + caption.w / 2, width * 0.5, delta=1)
                self.assertAlmostEqual(y + caption.h / 2, height * 0.79, delta=1)
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(y + caption.h, height)

    def test_short_video_exports_with_captions(self):
        Path("output").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir="output") as directory:
            source_path = os.path.join(directory, "source.mp4")
            with ColorClip((320, 240), color=(30, 40, 50), duration=1) as source:
                source.write_videofile(source_path, fps=10, codec="libx264", audio=False, logger=None)
            paths = cut_and_format_video(
                source_path,
                [CorteVideo(title="Caption test", start_time=0, end_time=1)],
                [{"word": "pra", "start": 0.1, "end": 0.3},
                 {"word": "maior", "start": 0.3, "end": 0.5},
                 {"word": "parte", "start": 0.5, "end": 0.8}],
                output_dir=directory,
            )
            self.assertEqual(len(paths), 1)
            with VideoFileClip(paths[0]) as result:
                self.assertEqual(result.w % 2, 0)
                self.assertEqual(result.h % 2, 0)
                frame = result.get_frame(0.3)
                green = ((frame[:, :, 1] > 150) & (frame[:, :, 0] < 110)
                         & (frame[:, :, 2] < 110))
                rows, columns = np.where(green)
                self.assertGreater(len(rows), 0)
                self.assertAlmostEqual(rows.mean() / result.h, 0.79, delta=0.04)
                self.assertAlmostEqual(columns.mean() / result.w, 0.5, delta=0.08)
                before_caption = result.get_frame(0)
                self.assertFalse(np.any((before_caption[:, :, 1] > 150)
                                        & (before_caption[:, :, 0] < 110)))


if __name__ == "__main__":
    unittest.main()
