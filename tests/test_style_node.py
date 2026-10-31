import json
import logging
import tempfile
import unittest
from pathlib import Path

from clipper.core.style_loader import (
    DEFAULT_VISUAL_IDENTITY,
    VisualIdentityConfig,
    load_visual_identity,
    validate_visual_identity_primitives,
)
from clipper.runtime import config


class TestVisualIdentityConfig(unittest.TestCase):
    """Unit tests for VisualIdentityConfig Pydantic model validation and defaults."""

    def test_default_values_match_config(self):
        model = VisualIdentityConfig()
        dumped = model.model_dump()
        self.assertEqual(dumped["caption_color"], config.CAPTION_COLOR)
        self.assertEqual(dumped["caption_stroke_color"], config.CAPTION_STROKE_COLOR)
        self.assertEqual(dumped["caption_font_size"], config.CAPTION_FONT_SIZE)
        self.assertEqual(dumped["caption_stroke_width"], config.CAPTION_STROKE_WIDTH)
        self.assertEqual(dumped["caption_reference_width"], config.CAPTION_REFERENCE_WIDTH)
        self.assertEqual(dumped["caption_center_x_ratio"], config.CAPTION_CENTER_X_RATIO)
        self.assertEqual(dumped["caption_center_y_ratio"], config.CAPTION_CENTER_Y_RATIO)
        self.assertEqual(dumped["caption_safe_width_ratio"], config.CAPTION_SAFE_WIDTH_RATIO)
        self.assertEqual(dumped["caption_max_words"], config.CAPTION_MAX_WORDS)
        self.assertEqual(dumped["caption_max_gap"], config.CAPTION_MAX_GAP)
        self.assertEqual(dumped["caption_max_duration"], config.CAPTION_MAX_DURATION)

    def test_valid_hex_color(self):
        model = VisualIdentityConfig(
            caption_color="#AABBCC",
            caption_stroke_color="#123456",
        )
        self.assertEqual(model.caption_color, "#AABBCC")
        self.assertEqual(model.caption_stroke_color, "#123456")

    def test_invalid_hex_color_falls_back_to_defaults(self):
        with self.assertLogs("clipper.core.style_loader", level="WARNING") as cm:
            model = VisualIdentityConfig(
                caption_color="#ZZZZZZ",
                caption_stroke_color="invalid-color",
            )
        self.assertEqual(model.caption_color, config.CAPTION_COLOR)
        self.assertEqual(model.caption_stroke_color, config.CAPTION_STROKE_COLOR)
        self.assertTrue(any("Invalid hex color" in msg for msg in cm.output))

    def test_positive_integers_fallback(self):
        with self.assertLogs("clipper.core.style_loader", level="WARNING") as cm:
            model = VisualIdentityConfig(
                caption_font_size=0,
                caption_stroke_width=-5,
                caption_reference_width="not-an-int",
                caption_max_words=-1,
            )
        self.assertEqual(model.caption_font_size, config.CAPTION_FONT_SIZE)
        self.assertEqual(model.caption_stroke_width, config.CAPTION_STROKE_WIDTH)
        self.assertEqual(model.caption_reference_width, config.CAPTION_REFERENCE_WIDTH)
        self.assertEqual(model.caption_max_words, config.CAPTION_MAX_WORDS)
        self.assertTrue(any("Invalid positive integer" in msg for msg in cm.output))

    def test_positive_floats_fallback(self):
        with self.assertLogs("clipper.core.style_loader", level="WARNING") as cm:
            model = VisualIdentityConfig(
                caption_max_gap=0.0,
                caption_max_duration=-2.5,
            )
        self.assertEqual(model.caption_max_gap, config.CAPTION_MAX_GAP)
        self.assertEqual(model.caption_max_duration, config.CAPTION_MAX_DURATION)
        self.assertTrue(any("Invalid positive number" in msg for msg in cm.output))

    def test_ratios_fallback(self):
        with self.assertLogs("clipper.core.style_loader", level="WARNING") as cm:
            model = VisualIdentityConfig(
                caption_center_x_ratio=-0.1,
                caption_center_y_ratio=1.5,
                caption_safe_width_ratio="bad_ratio",
            )
        self.assertEqual(model.caption_center_x_ratio, config.CAPTION_CENTER_X_RATIO)
        self.assertEqual(model.caption_center_y_ratio, config.CAPTION_CENTER_Y_RATIO)
        self.assertEqual(model.caption_safe_width_ratio, config.CAPTION_SAFE_WIDTH_RATIO)
        self.assertTrue(any("Invalid ratio" in msg for msg in cm.output))

    def test_extra_fields_ignored(self):
        model = VisualIdentityConfig.model_validate(
            {"extra_field_1": "value", "caption_font_size": 95}
        )
        self.assertEqual(model.caption_font_size, 95)
        self.assertNotIn("extra_field_1", model.model_dump())


class TestLoadVisualIdentity(unittest.TestCase):
    """Scaffolded unit and integration tests for load_visual_identity."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_absent_file_returns_defaults_with_warning(self):
        nonexistent = self.temp_dir_path / "absent_estilo.json"
        with self.assertLogs("clipper.core.style_loader", level="WARNING") as cm:
            loaded = load_visual_identity(nonexistent)

        self.assertEqual(loaded, DEFAULT_VISUAL_IDENTITY)
        self.assertTrue(any("Style file not found" in msg for msg in cm.output))

    def test_load_corrupted_json_syntax_returns_defaults_with_warning(self):
        corrupt_file = self.temp_dir_path / "corrupt_estilo.json"
        corrupt_file.write_text("{ unclosed json: ", encoding="utf-8")

        with self.assertLogs("clipper.core.style_loader", level="WARNING") as cm:
            loaded = load_visual_identity(corrupt_file)

        self.assertEqual(loaded, DEFAULT_VISUAL_IDENTITY)
        self.assertTrue(any("Failed to parse style file" in msg for msg in cm.output))

    def test_load_non_dict_root_returns_defaults_with_warning(self):
        list_file = self.temp_dir_path / "list_estilo.json"
        list_file.write_text(json.dumps(["item1", "item2"]), encoding="utf-8")

        with self.assertLogs("clipper.core.style_loader", level="WARNING") as cm:
            loaded = load_visual_identity(list_file)

        self.assertEqual(loaded, DEFAULT_VISUAL_IDENTITY)
        self.assertTrue(any("root is not a dictionary" in msg for msg in cm.output))

    def test_load_nested_valid_file_flattens_and_applies_styles(self):
        valid_file = self.temp_dir_path / "valid_estilo.json"
        style_payload = {
            "palette": {
                "caption_color": "#FF5500",
                "caption_stroke_color": "#111111",
            },
            "typography": {
                "caption_font_size": 96,
                "caption_stroke_width": 10,
                "caption_reference_width": 1920,
            },
            "layout": {
                "caption_center_x_ratio": 0.48,
                "caption_center_y_ratio": 0.82,
                "caption_safe_width_ratio": 0.85,
            },
            "motion": {
                "caption_max_words": 4,
                "caption_max_gap": 0.4,
                "caption_max_duration": 1.8,
            },
        }
        valid_file.write_text(json.dumps(style_payload), encoding="utf-8")

        with self.assertLogs("clipper.core.style_loader", level="INFO") as cm:
            loaded = load_visual_identity(valid_file)

        self.assertEqual(loaded["caption_color"], "#FF5500")
        self.assertEqual(loaded["caption_stroke_color"], "#111111")
        self.assertEqual(loaded["caption_font_size"], 96)
        self.assertEqual(loaded["caption_stroke_width"], 10)
        self.assertEqual(loaded["caption_reference_width"], 1920)
        self.assertEqual(loaded["caption_center_x_ratio"], 0.48)
        self.assertEqual(loaded["caption_center_y_ratio"], 0.82)
        self.assertEqual(loaded["caption_safe_width_ratio"], 0.85)
        self.assertEqual(loaded["caption_max_words"], 4)
        self.assertEqual(loaded["caption_max_gap"], 0.4)
        self.assertEqual(loaded["caption_max_duration"], 1.8)
        self.assertTrue(any("Loaded visual identity from" in msg for msg in cm.output))

    def test_load_partial_file_uses_defaults_for_missing_keys_with_warning(self):
        partial_file = self.temp_dir_path / "partial_estilo.json"
        style_payload = {
            "palette": {
                "caption_color": "#336699",
            }
        }
        partial_file.write_text(json.dumps(style_payload), encoding="utf-8")

        with self.assertLogs("clipper.core.style_loader", level="WARNING") as cm:
            loaded = load_visual_identity(partial_file)

        self.assertEqual(loaded["caption_color"], "#336699")
        self.assertEqual(loaded["caption_stroke_color"], config.CAPTION_STROKE_COLOR)
        self.assertEqual(loaded["caption_font_size"], config.CAPTION_FONT_SIZE)
        self.assertTrue(any("Missing field 'caption_font_size'" in msg for msg in cm.output))

    def test_load_file_with_invalid_values_reverts_per_field(self):
        invalid_val_file = self.temp_dir_path / "invalid_vals.json"
        style_payload = {
            "palette": {
                "caption_color": "#INVALID",
                "caption_stroke_color": "#222222",
            },
            "typography": {
                "caption_font_size": -50,
            },
        }
        invalid_val_file.write_text(json.dumps(style_payload), encoding="utf-8")

        with self.assertLogs("clipper.core.style_loader", level="WARNING") as cm:
            loaded = load_visual_identity(invalid_val_file)

        self.assertEqual(loaded["caption_color"], config.CAPTION_COLOR)
        self.assertEqual(loaded["caption_stroke_color"], "#222222")
        self.assertEqual(loaded["caption_font_size"], config.CAPTION_FONT_SIZE)
        self.assertTrue(any("Invalid hex color" in msg for msg in cm.output))
        self.assertTrue(any("Invalid positive integer" in msg for msg in cm.output))

    def test_json_primitive_serializability(self):
        valid_file = self.temp_dir_path / "primitives.json"
        valid_file.write_text(json.dumps({"caption_color": "#123456"}), encoding="utf-8")

        with self.assertLogs("clipper.core.style_loader", level="WARNING"):
            loaded = load_visual_identity(valid_file)
        # Verify json dumps succeeds and all values are primitive
        serialized = json.dumps(loaded)
        deserialized = json.loads(serialized)
        self.assertEqual(loaded, deserialized)
        for k, v in loaded.items():
            self.assertIsInstance(v, (str, int, float, bool))

    def test_validate_visual_identity_primitives_reverts_non_primitives_with_warning(self):
        payload = {
            "caption_color": "#AABBCC",
            "caption_font_size": 95,
            "invalid_fn": lambda x: x,
            "invalid_obj": object(),
            "caption_max_words": [1, 2, 3],
        }
        with self.assertLogs("clipper.core.style_loader", level="WARNING") as cm:
            cleaned = validate_visual_identity_primitives(payload)

        self.assertEqual(cleaned["caption_color"], "#AABBCC")
        self.assertEqual(cleaned["caption_font_size"], 95)
        self.assertEqual(cleaned["caption_max_words"], config.CAPTION_MAX_WORDS)
        self.assertNotIn("invalid_fn", cleaned)
        self.assertNotIn("invalid_obj", cleaned)
        # Verify JSON serializability
        serialized = json.dumps(cleaned)
        self.assertIn("AABBCC", serialized)
        self.assertTrue(any("Non-primitive value" in msg for msg in cm.output))


class TestStyleNode(unittest.TestCase):
    """Unit tests for style_node LangGraph node execution (T007)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_style_node_is_strictly_synchronous(self):
        import inspect
        from clipper.core.orchestrator import style_node

        self.assertFalse(inspect.iscoroutinefunction(style_node))

    def test_t023_style_node_wall_clock_execution_overhead_under_100ms(self):
        """T023 / SC-005: Verify style_node execution overhead is strictly under 100ms wall-clock."""
        import time
        from clipper.core.orchestrator import style_node

        style_file = self.temp_dir_path / "estilo.json"
        style_file.write_text(
            json.dumps({
                "palette": {"caption_color": "#123456", "caption_stroke_color": "#654321"},
                "typography": {"caption_font_size": 85, "caption_stroke_width": 7, "caption_reference_width": 1080},
                "layout": {"caption_center_x_ratio": 0.5, "caption_center_y_ratio": 0.8, "caption_safe_width_ratio": 0.9},
                "motion": {"caption_max_words": 3, "caption_max_gap": 0.5, "caption_max_duration": 2.0},
            }),
            encoding="utf-8",
        )
        state = {"video_url": "https://example.com/test", "style_path": str(style_file)}

        start_time = time.perf_counter()
        result = style_node(state)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        self.assertIn("visual_identity", result)
        self.assertLess(elapsed_ms, 100.0, f"Execution overhead {elapsed_ms:.2f}ms exceeds 100ms budget")

    def test_style_node_with_custom_file_populates_visual_identity(self):
        from clipper.core.orchestrator import style_node

        style_file = self.temp_dir_path / "estilo.json"
        style_file.write_text(
            json.dumps({"palette": {"caption_color": "#AABBCC"}}),
            encoding="utf-8",
        )

        state = {"video_url": "https://youtu.be/dummy", "style_path": str(style_file)}
        result = style_node(state)
        self.assertIn("visual_identity", result)
        self.assertEqual(result["visual_identity"]["caption_color"], "#AABBCC")
        self.assertEqual(
            result["visual_identity"]["caption_stroke_color"],
            config.CAPTION_STROKE_COLOR,
        )

    def test_style_node_with_absent_file_returns_all_defaults(self):
        from clipper.core.orchestrator import style_node

        nonexistent = self.temp_dir_path / "nonexistent.json"
        state = {"video_url": "https://youtu.be/dummy", "style_path": str(nonexistent)}
        result = style_node(state)
        self.assertIn("visual_identity", result)
        self.assertEqual(result["visual_identity"], DEFAULT_VISUAL_IDENTITY)

    def test_editor_node_passes_visual_identity_to_cut_and_format_video(self):
        from unittest.mock import patch, MagicMock
        from clipper.core.orchestrator import editor_node

        state = {
            "approval_complete": True,
            "video_path": "/fake/video.mp4",
            "cortes_finais": [{"title": "Cut 1", "start_time": 0.0, "end_time": 5.0}],
            "approved_cut_ids": [1],
            "word_timestamps": [],
            "review_directory": "/fake/review",
            "visual_identity": {"caption_color": "#112233"},
        }

        with patch("os.path.exists", return_value=True), \
             patch("clipper.core.orchestrator.load_review_plans", return_value=[MagicMock()]), \
             patch("clipper.core.orchestrator.cut_and_format_video", return_value=["/fake/cut1.mp4"]) as mock_cut:
            editor_node(state)
            mock_cut.assert_called_once()
            _, kwargs = mock_cut.call_args
            self.assertEqual(kwargs.get("visual_identity"), {"caption_color": "#112233"})



class TestCreateGraphStyleNodeContract(unittest.TestCase):
    """Contract tests for create_graph DAG edges and synchronous node compliance (T008)."""

    def test_create_graph_includes_style_node_between_fatiamento_and_transcricao(self):
        from clipper.core.orchestrator import create_graph

        workflow = create_graph()
        self.assertIn("style", workflow.nodes)

        # Check edges fatiamento -> style -> transcricao
        # In langgraph, edges can be inspected via workflow.builder.edges or workflow.edges
        edge_pairs = set()
        for edge in workflow.edges:
            # edge may be a tuple (start, end)
            if isinstance(edge, tuple):
                edge_pairs.add((edge[0], edge[1]))

        self.assertIn(("fatiamento", "style"), edge_pairs)
        self.assertIn(("style", "transcricao"), edge_pairs)
        self.assertNotIn(("fatiamento", "transcricao"), edge_pairs)


class TestEditorCaptionCustomStyle(unittest.TestCase):
    """Unit tests for create_caption_clip, position_caption_clip, and group_caption_words with visual_identity (T009)."""

    def test_create_caption_clip_applies_custom_color_and_size(self):
        import numpy as np
        from src.clipper.video.editor import create_caption_clip

        custom_style = {
            "caption_color": "#FF0000",
            "caption_stroke_color": "#00FF00",
            "caption_font_size": 90,
        }
        with create_caption_clip("TEST", frame_width=1080, visual_identity=custom_style) as clip:
            frame = clip.get_frame(0)
            mask = clip.mask.get_frame(0)
            # Check presence of red (#FF0000 -> [255, 0, 0])
            self.assertTrue(np.any(np.all(frame == [255, 0, 0], axis=-1)))
            # Check presence of green stroke (#00FF00 -> [0, 255, 0])
            self.assertTrue(np.any(np.all(frame == [0, 255, 0], axis=-1) & (mask > 0)))

    def test_create_caption_clip_fallback_when_none_or_missing(self):
        import numpy as np
        from src.clipper.video.editor import create_caption_clip

        with create_caption_clip("TEST", frame_width=1080, visual_identity=None) as clip:
            frame = clip.get_frame(0)
            # Default is #25E600 -> [37, 230, 0]
            self.assertTrue(np.any(np.all(frame == [37, 230, 0], axis=-1)))

    def test_position_caption_clip_applies_custom_ratios(self):
        from moviepy.editor import ColorClip
        from src.clipper.video.editor import position_caption_clip

        custom_style = {
            "caption_center_x_ratio": 0.3,
            "caption_center_y_ratio": 0.6,
        }
        with ColorClip((100, 50), color=(255, 255, 255)) as clip:
            positioned = position_caption_clip(clip, (1000, 1000), visual_identity=custom_style)
            x, y = positioned.pos(0)
            # x = round(1000 * 0.3 - 100 / 2) = 300 - 50 = 250
            # y = round(1000 * 0.6 - 50 / 2) = 600 - 25 = 575
            self.assertEqual(x, 250)
            self.assertEqual(y, 575)

    def test_group_caption_words_applies_custom_motion_rules(self):
        from src.clipper.video.editor import group_caption_words

        words = [
            {"word": "word1", "start": 0.0, "end": 0.3},
            {"word": "word2", "start": 0.3, "end": 0.6},
            {"word": "word3", "start": 0.6, "end": 0.9},
            {"word": "word4", "start": 0.9, "end": 1.2},
        ]
        # Default caption_max_words = 3 -> groups of 3 and 1
        default_groups = group_caption_words(words, 0.0, 2.0, visual_identity=None)
        self.assertEqual(len(default_groups), 2)
        self.assertEqual(default_groups[0]["text"], "word1 word2 word3")
        self.assertEqual(default_groups[1]["text"], "word4")

        # Custom caption_max_words = 2 -> groups of 2 and 2
        custom_style = {"caption_max_words": 2}
        custom_groups = group_caption_words(words, 0.0, 2.0, visual_identity=custom_style)
        self.assertEqual(len(custom_groups), 2)
        self.assertEqual(custom_groups[0]["text"], "word1 word2")
        self.assertEqual(custom_groups[1]["text"], "word3 word4")

    def test_cut_and_format_video_applies_custom_visual_identity(self):
        import os
        from unittest.mock import patch
        import numpy as np
        from moviepy.editor import ColorClip, VideoFileClip
        from src.clipper.core.schemas import CorteVideo
        from src.clipper.video import editor

        with tempfile.TemporaryDirectory() as directory:
            source_path = os.path.join(directory, "source.mp4")
            with ColorClip((320, 240), color=(30, 40, 50), duration=1) as source:
                source.write_videofile(source_path, fps=10, codec="libx264", audio=False, logger=None)
            with patch.object(editor, "SPEAKER_FOCUS_ENABLED", False):
                paths = editor.cut_and_format_video(
                    source_path,
                    [CorteVideo(title="Custom color test", start_time=0, end_time=1)],
                    [{"word": "teste", "start": 0.1, "end": 0.8}],
                    output_dir=directory,
                    visual_identity={"caption_color": "#FF0000"},
                )
            self.assertEqual(len(paths), 1)
            with VideoFileClip(paths[0]) as result:
                frame = result.get_frame(0.3)
                red = (frame[:, :, 0] > 200) & (frame[:, :, 1] < 50) & (frame[:, :, 2] < 50)
                rows, _ = np.where(red)
                self.assertGreater(len(rows), 0)




class TestStyleCheckpointRecovery(unittest.TestCase):
    """Integration tests for User Story 2: Checkpoint Persistence and State Recovery (T016, T017)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_t016_checkpoint_persistence_and_recovery_survives_interruption(self):
        """T016: visual_identity persists in SQLite checkpoint and recovers identically without reading disk."""
        from langgraph.checkpoint.sqlite import SqliteSaver
        from langgraph.graph import StateGraph
        from src.clipper.core.orchestrator import VideoState, style_node

        db_path = str(self.temp_path / "test_recovery.db")
        style_file = self.temp_path / "estilo.json"
        style_file.write_text(json.dumps({"palette": {"caption_color": "#00E5FF"}}), encoding="utf-8")

        thread_id = "recovery-thread-123"
        graph_config = {"configurable": {"thread_id": thread_id}}

        builder = StateGraph(VideoState)
        builder.add_node("style", style_node)
        builder.set_entry_point("style")
        builder.set_finish_point("style")

        # Session 1: Run style_node and record checkpoint
        with SqliteSaver.from_conn_string(db_path) as checkpointer:
            checkpointer.setup()
            app = builder.compile(checkpointer=checkpointer)
            initial_state = {"video_url": "https://example.com/test", "style_path": str(style_file)}
            result = app.invoke(initial_state, config=graph_config)
            self.assertEqual(result["visual_identity"]["caption_color"], "#00E5FF")

        # Simulate interruption & delete estilo.json to prove disk is not re-read
        style_file.unlink()
        self.assertFalse(style_file.exists())

        # Session 2: Reload state from SQLite checkpoint
        with SqliteSaver.from_conn_string(db_path) as checkpointer:
            checkpointer.setup()
            app = builder.compile(checkpointer=checkpointer)
            snapshot = app.get_state(graph_config)
            self.assertIsNotNone(snapshot)
            self.assertIn("visual_identity", snapshot.values)
            recovered_identity = snapshot.values["visual_identity"]
            # SC-003: byte-for-byte / identical values restored
            self.assertEqual(recovered_identity["caption_color"], "#00E5FF")
            self.assertEqual(recovered_identity, result["visual_identity"])

    def test_t017_restart_purges_checkpoints_and_rereads_estilo(self):
        """T017: --restart purges checkpoints and re-executes style_node to load updated estilo.json."""
        from langgraph.checkpoint.sqlite import SqliteSaver
        from langgraph.graph import StateGraph
        from src.clipper.core.orchestrator import VideoState, style_node, purge_thread_checkpoints

        db_path = str(self.temp_path / "test_restart.db")
        style_file = self.temp_path / "estilo.json"
        style_file.write_text(json.dumps({"palette": {"caption_color": "#111111"}}), encoding="utf-8")

        thread_id = "restart-thread-456"
        graph_config = {"configurable": {"thread_id": thread_id}}

        builder = StateGraph(VideoState)
        builder.add_node("style", style_node)
        builder.set_entry_point("style")
        builder.set_finish_point("style")

        # Session 1: First run with initial style
        with SqliteSaver.from_conn_string(db_path) as checkpointer:
            checkpointer.setup()
            app = builder.compile(checkpointer=checkpointer)
            initial_state = {"video_url": "https://example.com/test", "style_path": str(style_file)}
            res1 = app.invoke(initial_state, config=graph_config)
            self.assertEqual(res1["visual_identity"]["caption_color"], "#111111")

        # Operator edits estilo.json on disk
        style_file.write_text(json.dumps({"palette": {"caption_color": "#990099"}}), encoding="utf-8")

        # Session 2: Resume with --restart (purges thread checkpoints)
        with SqliteSaver.from_conn_string(db_path) as checkpointer:
            checkpointer.setup()
            purge_thread_checkpoints(checkpointer, thread_id)
            app = builder.compile(checkpointer=checkpointer)

            # Checkpoint snapshot should now be empty for this thread
            snapshot = app.get_state(graph_config)
            self.assertFalse(snapshot.values)

            # Re-executing invokes style_node again and loads new style
            initial_state = {"video_url": "https://example.com/test", "style_path": str(style_file)}
            res2 = app.invoke(initial_state, config=graph_config)
            self.assertEqual(res2["visual_identity"]["caption_color"], "#990099")


class TestStyleObservabilityLogging(unittest.TestCase):
    """Unit tests for User Story 3: Operator Inspects Loaded Style at Runtime (T019, T020)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_t019_info_log_on_successful_estilo_loading(self):
        """T019: Assert INFO log emitted listing all loaded style keys and values with style_node prefix."""
        style_file = self.temp_path / "estilo.json"
        style_payload = {
            "palette": {
                "caption_color": "#FFAA00",
                "caption_stroke_color": "#222222",
            },
            "typography": {
                "caption_font_size": 92,
                "caption_stroke_width": 9,
                "caption_reference_width": 1080,
            },
            "layout": {
                "caption_center_x_ratio": 0.52,
                "caption_center_y_ratio": 0.78,
                "caption_safe_width_ratio": 0.88,
            },
            "motion": {
                "caption_max_words": 4,
                "caption_max_gap": 0.45,
                "caption_max_duration": 1.75,
            },
        }
        style_file.write_text(json.dumps(style_payload), encoding="utf-8")

        # 1. Test via load_visual_identity
        with self.assertLogs("clipper.core.style_loader", level="INFO") as cm:
            loaded = load_visual_identity(style_file)

        info_entries = [m for m in cm.output if "INFO" in m and "style_node: Loaded visual identity from" in m]
        self.assertEqual(len(info_entries), 1)
        logged_text = info_entries[0]
        self.assertIn(str(style_file), logged_text)
        # Ensure all recognized style keys and their loaded values appear in the log
        for key, value in loaded.items():
            self.assertIn(f"'{key}': {repr(value)}", logged_text)

        # 2. Test via style_node execution
        from clipper.core.orchestrator import style_node
        with self.assertLogs("clipper.core.style_loader", level="INFO") as cm_node:
            node_state = {"video_url": "https://example.com/test", "style_path": str(style_file)}
            node_result = style_node(node_state)

        node_info_entries = [m for m in cm_node.output if "INFO" in m and "style_node: Loaded visual identity from" in m]
        self.assertEqual(len(node_info_entries), 1)
        self.assertEqual(node_result["visual_identity"], loaded)

    def test_t020_warning_log_on_absent_estilo_file(self):
        """T020: Assert WARNING log emitted when estilo.json is absent, stating fallback to defaults."""
        from clipper.core.orchestrator import style_node

        absent_path = self.temp_path / "nonexistent_estilo.json"
        with self.assertLogs("clipper.core.style_loader", level="WARNING") as cm:
            result = style_node({"style_path": str(absent_path)})

        self.assertEqual(result["visual_identity"], DEFAULT_VISUAL_IDENTITY)
        warning_entries = [m for m in cm.output if "WARNING" in m and "style_node: Style file not found at" in m]
        self.assertEqual(len(warning_entries), 1)
        self.assertIn("Using default visual identity", warning_entries[0])

    def test_t020_warning_log_on_corrupted_json_syntax(self):
        """T020: Assert WARNING log emitted when estilo.json has corrupt syntax."""
        from clipper.core.orchestrator import style_node

        corrupted_file = self.temp_path / "corrupted_estilo.json"
        corrupted_file.write_text("{ unclosed invalid json : [", encoding="utf-8")

        with self.assertLogs("clipper.core.style_loader", level="WARNING") as cm:
            result = style_node({"style_path": str(corrupted_file)})

        self.assertEqual(result["visual_identity"], DEFAULT_VISUAL_IDENTITY)
        warning_entries = [m for m in cm.output if "WARNING" in m and "style_node: Failed to parse style file" in m]
        self.assertEqual(len(warning_entries), 1)
        self.assertIn("Using default visual identity", warning_entries[0])

    def test_t020_warning_log_on_missing_fields_in_partial_file(self):
        """T020: Assert WARNING log emitted for each missing field with style_node prefix and default value."""
        from clipper.core.orchestrator import style_node

        partial_file = self.temp_path / "partial_estilo.json"
        partial_file.write_text(json.dumps({"palette": {"caption_color": "#112233"}}), encoding="utf-8")

        with self.assertLogs("clipper.core.style_loader", level="WARNING") as cm:
            result = style_node({"style_path": str(partial_file)})

        # 10 missing fields out of 11 total
        missing_warnings = [m for m in cm.output if "WARNING" in m and "style_node: Missing field" in m]
        self.assertEqual(len(missing_warnings), 10)
        self.assertNotIn("Missing field 'caption_color'", "\n".join(missing_warnings))
        for key in DEFAULT_VISUAL_IDENTITY:
            if key != "caption_color":
                self.assertTrue(
                    any(f"Missing field '{key}' in style file. Using default '{DEFAULT_VISUAL_IDENTITY[key]}'." in m for m in missing_warnings),
                    f"Expected warning for missing field {key}",
                )

    def test_t020_warning_log_on_invalid_hex_and_numeric_constraints(self):
        """T020: Assert WARNING log emitted when invalid hex, non-positive numbers, or bad ratios fall back."""
        invalid_file = self.temp_path / "invalid_constraints.json"
        payload = {
            "palette": {
                "caption_color": "#BADHEXCOLOR",
            },
            "typography": {
                "caption_font_size": -10,
            },
            "layout": {
                "caption_center_x_ratio": 2.5,
            },
            "motion": {
                "caption_max_gap": -0.5,
            },
        }
        invalid_file.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertLogs("clipper.core.style_loader", level="WARNING") as cm:
            loaded = load_visual_identity(invalid_file)

        self.assertEqual(loaded["caption_color"], DEFAULT_VISUAL_IDENTITY["caption_color"])
        self.assertEqual(loaded["caption_font_size"], DEFAULT_VISUAL_IDENTITY["caption_font_size"])
        self.assertEqual(loaded["caption_center_x_ratio"], DEFAULT_VISUAL_IDENTITY["caption_center_x_ratio"])
        self.assertEqual(loaded["caption_max_gap"], DEFAULT_VISUAL_IDENTITY["caption_max_gap"])

        warnings = "\n".join(cm.output)
        self.assertIn("style_node: Invalid hex color '#BADHEXCOLOR' for field 'caption_color'", warnings)
        self.assertIn("style_node: Invalid positive integer '-10' for field 'caption_font_size'", warnings)
        self.assertIn("style_node: Invalid ratio '2.5' for field 'caption_center_x_ratio'", warnings)
        self.assertIn("style_node: Invalid positive number '-0.5' for field 'caption_max_gap'", warnings)


if __name__ == "__main__":
    unittest.main()
