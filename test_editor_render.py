import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from moviepy.editor import ColorClip, VideoFileClip

from editor import create_caption_clip, cut_and_format_video
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
                self.assertTrue(np.any(np.all(frame == [255, 255, 0], axis=-1)))
                self.assertTrue(np.any(np.all(frame == [0, 0, 0], axis=-1) & (mask > 0)))

    def test_short_video_exports_with_captions(self):
        Path("output").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir="output") as directory:
            source_path = os.path.join(directory, "source.mp4")
            with ColorClip((320, 240), color=(30, 40, 50), duration=1) as source:
                source.write_videofile(source_path, fps=10, codec="libx264", audio=False, logger=None)
            paths = cut_and_format_video(
                source_path,
                [CorteVideo(title="Caption test", start_time=0, end_time=1)],
                [{"word": "Olá!", "start": 0, "end": 0.8}],
                output_dir=directory,
            )
            self.assertEqual(len(paths), 1)
            with VideoFileClip(paths[0]) as result:
                self.assertEqual(result.w % 2, 0)
                self.assertEqual(result.h % 2, 0)
                frame = result.get_frame(0.3)
                self.assertTrue(np.any((frame[:, :, 0] > 180) & (frame[:, :, 1] > 180)))


if __name__ == "__main__":
    unittest.main()
