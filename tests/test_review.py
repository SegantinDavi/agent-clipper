import tests
from html.parser import HTMLParser
from pathlib import Path
import sqlite3
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, START, END
from moviepy.editor import ColorClip, VideoFileClip

import clipper.core.orchestrator as orchestrator
from clipper.review.review import (
    ApprovalDecision, ReviewManifest, create_review_server, load_approval_decision,
    prepare_review, render_review_page, save_approval_decision, validate_approval,
    wait_for_approval,
)
from clipper.core.schemas import CorteVideo
from clipper.video.pause_editing import PauseSettings, identity_plan


class TokenParser(HTMLParser):
    token = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("name") == "token":
            self.token = attrs.get("value")


class ReviewTests(unittest.TestCase):
    def setUp(self):
        Path("output").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir="output")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.cuts = [
            CorteVideo(title="First <script>", description="Topic & context", start_time=0, end_time=1),
            CorteVideo(title="Second", description="Another topic", start_time=1, end_time=2),
        ]
        (self.root / "review.json").write_text(
            ReviewManifest(cuts=self.cuts, pause_plans=[
                identity_plan(cut.start_time, cut.end_time, PauseSettings(enabled=False))
                for cut in self.cuts
            ]).model_dump_json(), encoding="utf-8",
        )

    def test_page_escapes_metadata_and_starts_unselected(self):
        page = render_review_page(self.cuts, "test-token")
        self.assertIn("First &lt;script&gt;", page)
        self.assertIn("Topic &amp; context", page)
        self.assertIn('src="preview-2.mp4"', page)
        self.assertNotIn("checked", page)
        parser = TokenParser()
        parser.feed(page)
        self.assertEqual(parser.token, "test-token")

    def test_invalid_decisions_are_rejected(self):
        for value in ({}, {"approved_ids": [0]}, {"approved_ids": [3]},
                      {"approved_ids": [1, 1]}, {"approved_ids": [True]},
                      {"approved_ids": ["1"]}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_approval(value, len(self.cuts))

    def test_browser_submission_is_persisted_and_private_files_are_not_served(self):
        with create_review_server(str(self.root), port=0) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}"
                with urlopen(url, timeout=5) as response:
                    parser = TokenParser()
                    parser.feed(response.read().decode())
                for route in ("/review.json", "/../config.py", "/decision.json"):
                    with self.assertRaises(HTTPError) as error:
                        urlopen(url + route, timeout=5)
                    self.assertEqual(error.exception.code, 404)
                    error.exception.close()
                for form, code in (({"token": "wrong", "action": "approve", "cut_id": 1}, 403),
                                   ({"token": parser.token, "action": "approve", "cut_id": 99}, 400),
                                   ({"token": parser.token, "action": "approve"}, 400)):
                    with self.assertRaises(HTTPError) as error:
                        urlopen(Request(url + "/approve", data=urlencode(form).encode()), timeout=5)
                    self.assertEqual(error.exception.code, code)
                    error.exception.close()
                    self.assertIsNone(server.decision)
                form = {"token": parser.token, "action": "approve", "cut_id": 2}
                with urlopen(Request(url + "/approve", data=urlencode(form).encode()), timeout=5) as response:
                    self.assertEqual(response.status, 200)
                self.assertEqual(server.decision, [2])
            finally:
                server.shutdown()
                thread.join(timeout=5)
        self.assertEqual(wait_for_approval(str(self.root), port=0), [2])

    def test_previews_are_playable_and_invalid_intervals_fail(self):
        source_path = self.root / "source.mp4"
        with ColorClip((320, 240), color=(20, 60, 90), duration=2) as source:
            source.write_videofile(str(source_path), fps=10, codec="libx264", audio=False, logger=None)
        directory = Path(prepare_review(str(source_path), self.cuts, str(self.root)))
        for index in (1, 2):
            with VideoFileClip(str(directory / f"preview-{index}.mp4")) as preview:
                self.assertAlmostEqual(preview.duration, 1, delta=0.15)
                self.assertLessEqual(preview.w, 640)
                self.assertEqual(preview.w % 2, 0)
                self.assertEqual(preview.h % 2, 0)
        with self.assertRaises(ValueError):
            prepare_review(str(source_path), [CorteVideo(title="Bad", start_time=-1, end_time=9)], str(self.root))

    def create_test_checkpointer(self, db_filename="state.db"):
        return SqliteSaver.from_conn_string(str(self.root / db_filename))

    def get_sqlite_checkpoint_count(self, db_path: str, thread_id: str) -> tuple[int, int]:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='checkpoints'")
            if not cursor.fetchone():
                return 0, 0
            cursor.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (thread_id,))
            checkpoints_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM writes WHERE thread_id = ?", (thread_id,))
            writes_count = cursor.fetchone()[0]
            return checkpoints_count, writes_count

    def build_test_state(self, **overrides) -> dict:
        source_path = self.root / "source.mp4"
        if not source_path.exists():
            source_path.touch()
        state = {
            "video_url": "https://www.youtube.com/watch?v=mock",
            "video_path": str(source_path),
            "audio_chunks": [],
            "transcript_grouped": "Mock transcription",
            "word_timestamps": [],
            "raciocinio_bruto": "Mock reasoning",
            "cortes_finais": [cut.model_dump() for cut in self.cuts],
            "review_directory": str(self.root),
            "review_session": "test-session-token",
            "approved_cut_ids": [],
            "approval_complete": False,
        }
        state.update(overrides)
        return state

    def build_graph(self, upstream_calls=None, editor_calls=None, custom_approval=None):
        def upstream(state):
            if upstream_calls is not None:
                upstream_calls.append(True)
            return state

        def editor(state):
            if editor_calls is not None:
                editor_calls.append(True)
            return orchestrator.editor_node(state)

        graph = StateGraph(orchestrator.VideoState)
        graph.add_node("upstream", upstream)
        graph.add_node("approval", custom_approval or orchestrator.approval_node)
        graph.add_node("editor", editor if editor_calls is not None else orchestrator.editor_node)
        graph.add_edge(START, "upstream")
        graph.add_edge("upstream", "approval")
        graph.add_edge("approval", "editor")
        graph.add_edge("editor", END)
        return graph

    def test_sqlite_restart_requires_approval_and_edits_only_selection(self):
        calls = []
        graph_config = {"configurable": {"thread_id": "review-test"}}
        database = str(self.root / "state.db")
        source = self.root / "source.mp4"
        source.touch()
        state = {
            "video_path": str(source), "cortes_finais": [cut.model_dump() for cut in self.cuts],
            "review_directory": str(self.root), "approval_complete": False,
            "approved_cut_ids": [], "word_timestamps": [],
        }
        with patch.object(orchestrator, "cut_and_format_video", return_value=[]) as render:
            with SqliteSaver.from_conn_string(database) as saver:
                app = self.build_graph(calls).compile(checkpointer=saver)
                result = app.invoke(state, graph_config)
                self.assertTrue(result["__interrupt__"])
                render.assert_not_called()
            with SqliteSaver.from_conn_string(database) as saver:
                app = self.build_graph(calls).compile(checkpointer=saver)
                with patch.object(orchestrator, "wait_for_approval", return_value=[2]):
                    result = orchestrator.run_with_review(app, state, graph_config)
                self.assertEqual(result["approved_cut_ids"], [2])
                self.assertEqual(len(calls), 1)
                self.assertEqual(render.call_args.kwargs["cortes_validados"], [self.cuts[1]])
                self.assertEqual(render.call_args.kwargs["pause_plans"][0].source_start, 1)

    def test_reject_all_skips_editor(self):
        (self.root / "decision.json").write_text(ApprovalDecision(approved_ids=[]).model_dump_json())
        self.assertEqual(wait_for_approval(str(self.root), port=0), [])
        with patch.object(orchestrator, "cut_and_format_video") as render:
            orchestrator.editor_node({"approval_complete": True, "approved_cut_ids": [],
                                      "cortes_finais": [cut.model_dump() for cut in self.cuts]})
            render.assert_not_called()

    def test_editor_cannot_bypass_approval(self):
        with self.assertRaisesRegex(ValueError, "approval"):
            orchestrator.editor_node({"cortes_finais": [self.cuts[0].model_dump()]})

    def test_atomic_decision_serialization_and_loading(self):
        rev_dir = self.root / "atomic_rev"
        rev_dir.mkdir()
        self.assertIsNone(load_approval_decision(rev_dir))
        dest = save_approval_decision(rev_dir, [1, 2])
        self.assertTrue(dest.exists())
        self.assertFalse((rev_dir / "decision.partial.json").exists())
        self.assertEqual(load_approval_decision(rev_dir, cut_count=2), [1, 2])
        # Corrupted decision returns None
        dest.write_text("not json", encoding="utf-8")
        self.assertIsNone(load_approval_decision(rev_dir, cut_count=2))

    def test_purge_thread_checkpoints_clears_only_target_thread(self):
        db_path = str(self.root / "test_purge.db")
        with SqliteSaver.from_conn_string(db_path) as saver:
            saver.setup()
            target_thread = "target-thread"
            other_thread = "other-thread"
            with saver.conn:
                saver.conn.execute(
                    "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, type) VALUES (?, '', 'chk-1', 'test')",
                    (target_thread,)
                )
                saver.conn.execute(
                    "INSERT INTO writes (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, type) VALUES (?, '', 'chk-1', 'task-1', 0, 'c', 't')",
                    (target_thread,)
                )
                saver.conn.execute(
                    "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, type) VALUES (?, '', 'chk-2', 'test')",
                    (other_thread,)
                )
            self.assertEqual(self.get_sqlite_checkpoint_count(db_path, target_thread), (1, 1))
            self.assertEqual(self.get_sqlite_checkpoint_count(db_path, other_thread), (1, 0))

            orchestrator.purge_thread_checkpoints(saver, target_thread)

            self.assertEqual(self.get_sqlite_checkpoint_count(db_path, target_thread), (0, 0))
            self.assertEqual(self.get_sqlite_checkpoint_count(db_path, other_thread), (1, 0))


if __name__ == "__main__":
    unittest.main()
