import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from clipper.core.orchestrator import (
    create_graph,
    editor_node,
    route_approval_outcome,
)
from clipper.core.schemas import CorteVideo


class TestEditorNode(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.test_dir, "test_video.mp4")
        with open(self.video_path, "wb") as f:
            f.write(b"\x00" * 1024)

        self.cortes = [
            CorteVideo(
                id=1,
                title="Corte Um",
                description="Desc 1",
                start_time=0.0,
                end_time=10.0,
                scenes=[],
            ),
            CorteVideo(
                id=2,
                title="Corte Dois",
                description="Desc 2",
                start_time=15.0,
                end_time=25.0,
                scenes=[],
            ),
        ]

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_editor_node_requires_approval_complete(self):
        state = {"approval_complete": False}
        with self.assertRaises(ValueError) as ctx:
            editor_node(state)
        self.assertIn("Cut approval is required", str(ctx.exception))

    def test_editor_node_corrupted_decision_file_raises_error(self):
        rev_dir = os.path.join(self.test_dir, "rev_corrupt")
        os.makedirs(rev_dir, exist_ok=True)
        with open(os.path.join(rev_dir, "decision.json"), "w") as f:
            f.write("invalid json content {{{")
        state = {
            "approval_complete": True,
            "review_directory": rev_dir,
        }
        with self.assertRaises(ValueError) as ctx:
            editor_node(state)
        self.assertIn("decision.json is unreadable or structurally invalid", str(ctx.exception))

    def test_editor_node_empty_approval_skips_rendering(self):
        state = {
            "approval_complete": True,
            "approved_cut_ids": [],
            "cortes_finais": self.cortes,
            "video_path": self.video_path,
        }
        result = editor_node(state)
        self.assertEqual(result, {})

    @patch("clipper.core.orchestrator.cut_and_format_video")
    @patch("clipper.core.orchestrator.release_cuda_memory")
    def test_editor_node_renders_only_approved_cuts(self, mock_vram, mock_cut_and_format):
        mock_cut_and_format.return_value = ["/path/to/cut_2.mp4"]
        state = {
            "approval_complete": True,
            "approved_cut_ids": [2],
            "cortes_finais": self.cortes,
            "video_path": self.video_path,
            "word_timestamps": [{"word": "teste", "start": 15.0, "end": 16.0}],
            "visual_identity": {},
        }

        with self.assertLogs("clipper.core.orchestrator", level="INFO") as log_capture:
            result = editor_node(state)
            self.assertEqual(result, {"rendered_video_paths": ["/path/to/cut_2.mp4"]})
            mock_cut_and_format.assert_called_once()
            called_cuts = mock_cut_and_format.call_args[1]["cortes_validados"]
            self.assertEqual(len(called_cuts), 1)
            self.assertEqual(called_cuts[0].title, "Corte Dois")

            logs = "\n".join(log_capture.output)
            self.assertIn("Cut '1' is not in approved_cut_ids. Skipping rendering.", logs)

        mock_vram.assert_called()

    def test_route_approval_outcome(self):
        # Empty approved cuts routes to end
        state_empty = {"approved_cut_ids": [], "approval_complete": True}
        self.assertEqual(route_approval_outcome(state_empty), "end")

        # Non-empty approved cuts routes to editor
        state_approved = {"approved_cut_ids": [1], "approval_complete": True}
        self.assertEqual(route_approval_outcome(state_approved), "editor")

    def test_graph_wires_approval_to_editor(self):
        graph = create_graph()
        branches = graph.branches.get("approval", {})
        self.assertTrue(len(branches) > 0)
        branch = list(branches.values())[0]
        self.assertIn("editor", branch.ends)
        self.assertIn("end", branch.ends)
        self.assertEqual(branch.ends["end"], "__end__")


    def test_subtitles_for_long_cuts_with_more_than_100_words(self):
        """FR-003 / SC-002: Word timestamps are not truncated at 100 words."""
        from clipper.video.editor import group_caption_words

        words_150 = [
            {"word": f"palavra_{i}", "start": float(i * 0.3), "end": float(i * 0.3 + 0.25)}
            for i in range(150)
        ]
        duration = 150 * 0.3
        groups = group_caption_words(words_150, 0.0, duration)

        self.assertTrue(len(groups) > 30)
        # Verify first group starts near 0.0
        self.assertAlmostEqual(groups[0]["start"], 0.0, delta=0.1)
        # Verify last group covers the end of the 150 words (not stopping at word 100)
        self.assertIn("palavra149", groups[-1]["text"])
        self.assertAlmostEqual(groups[-1]["end"], 150 * 0.3, delta=0.5)

    def test_caption_styling_with_visual_identity(self):
        """FR-004: Visual identity styling applied to caption clip."""
        from clipper.video.editor import create_caption_clip, position_caption_clip

        custom_style = {
            "caption_color": "#FF5500",
            "caption_stroke_color": "#FFFFFF",
            "caption_font_size": 90,
            "caption_stroke_width": 10,
            "caption_center_y_ratio": 0.85,
        }
        clip = create_caption_clip("Texto estilizado", frame_width=1080, visual_identity=custom_style)
        self.assertIsNotNone(clip)
        self.assertTrue(clip.w > 0)
        self.assertTrue(clip.h > 0)

        positioned = position_caption_clip(clip, (1080, 1920), visual_identity=custom_style)
        pos = positioned.pos(0)
        expected_y = round(1920 * 0.85 - clip.h / 2)
        self.assertEqual(pos[1], expected_y)
        clip.close()
        positioned.close()


if __name__ == "__main__":
    unittest.main()
