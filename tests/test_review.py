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
from langgraph.types import Command
from moviepy.editor import ColorClip, VideoFileClip

import clipper.core.orchestrator as orchestrator
from clipper.review.review import (
    ApprovalDecision, ReviewManifest, create_review_server, load_approval_decision,
    load_review_plans, prepare_review, render_review_page, save_approval_decision,
    validate_approval, wait_for_approval,
)
from clipper.core.schemas import CorteVideo, Scene
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

    def test_completed_run_exits_early_without_reprocessing(self):
        calls = []
        editor_calls = []
        thread_id = "test-completed-thread"
        graph_config = {"configurable": {"thread_id": thread_id}}
        database = str(self.root / "state_completed.db")
        state = self.build_test_state()

        with patch.object(orchestrator, "cut_and_format_video", return_value=[]):
            with SqliteSaver.from_conn_string(database) as saver:
                app = self.build_graph(upstream_calls=calls, editor_calls=editor_calls).compile(checkpointer=saver)
                with patch.object(orchestrator, "wait_for_approval", return_value=[1]):
                    first_run = orchestrator.run_with_review(app, state, graph_config)
                self.assertEqual(len(calls), 1)
                self.assertEqual(len(editor_calls), 1)
                self.assertTrue(first_run.get("approval_complete"))

                # Second run on completed thread without restart must exit immediately
                with patch.object(orchestrator, "wait_for_approval") as mock_wait:
                    second_run = orchestrator.run_with_review(app, state, graph_config, restart=False)
                    mock_wait.assert_not_called()
                self.assertEqual(len(calls), 1)
                self.assertEqual(len(editor_calls), 1)
                self.assertEqual(second_run.get("approved_cut_ids"), [1])

    def test_restart_purges_checkpoints_and_restarts_from_beginning(self):
        calls = []
        target_thread = "target-restart-thread"
        other_thread = "other-preserved-thread"
        database = str(self.root / "state_restart.db")
        state = self.build_test_state()
        state["review_session"] = "old-session"

        with patch.object(orchestrator, "cut_and_format_video", return_value=[]):
            with SqliteSaver.from_conn_string(database) as saver:
                saver.setup()
                # Populate other_thread
                with saver.conn:
                    saver.conn.execute(
                        "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, type) VALUES (?, '', 'other-chk', 'test')",
                        (other_thread,)
                    )
                app = self.build_graph(upstream_calls=calls).compile(checkpointer=saver)

                # Run target_thread to completion
                with patch.object(orchestrator, "wait_for_approval", return_value=[1]):
                    orchestrator.run_with_review(app, state, {"configurable": {"thread_id": target_thread}})
                self.assertEqual(len(calls), 1)
                chk_count, _ = self.get_sqlite_checkpoint_count(database, target_thread)
                self.assertGreater(chk_count, 0)

                # Now run with restart=True
                with patch.object(orchestrator, "purge_thread_checkpoints", wraps=orchestrator.purge_thread_checkpoints) as spy_purge:
                    with patch.object(orchestrator, "wait_for_approval", return_value=[2]):
                        result = orchestrator.run_with_review(app, state, {"configurable": {"thread_id": target_thread}}, restart=True)
                    spy_purge.assert_called_once_with(app.checkpointer, target_thread)

                # Upstream must have run again (count 2)
                self.assertEqual(len(calls), 2)
                self.assertEqual(result.get("approved_cut_ids"), [2])
                self.assertNotEqual(state["review_session"], "old-session")
                # other_thread must remain untouched
                other_chk, _ = self.get_sqlite_checkpoint_count(database, other_thread)
                self.assertEqual(other_chk, 1)

    def test_crash_safe_resumption_after_interrupt_without_restart(self):
        calls = []
        editor_calls = []
        thread_id = "crash-resume-thread"
        graph_config = {"configurable": {"thread_id": thread_id}}
        database = str(self.root / "state_crash.db")
        state = self.build_test_state()

        with patch.object(orchestrator, "cut_and_format_video", return_value=[]):
            # Phase 1: Initial run crashes while waiting for approval
            with SqliteSaver.from_conn_string(database) as saver:
                app = self.build_graph(upstream_calls=calls, editor_calls=editor_calls).compile(checkpointer=saver)
                with patch.object(orchestrator, "wait_for_approval", side_effect=KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        orchestrator.run_with_review(app, state, graph_config, restart=False)

                self.assertEqual(len(calls), 1)
                self.assertEqual(len(editor_calls), 0)
                snapshot = app.get_state(graph_config)
                self.assertTrue(any(task.interrupts for task in snapshot.tasks))

            # Phase 2: Relaunch container / new run_with_review call with same thread_id and restart=False
            with SqliteSaver.from_conn_string(database) as saver:
                app = self.build_graph(upstream_calls=calls, editor_calls=editor_calls).compile(checkpointer=saver)
                with patch.object(orchestrator, "wait_for_approval", return_value=[2]):
                    result = orchestrator.run_with_review(app, state, graph_config, restart=False)

                # Upstream must NOT have been re-executed
                self.assertEqual(len(calls), 1)
                # Editor must have executed
                self.assertEqual(len(editor_calls), 1)
                self.assertEqual(result.get("approved_cut_ids"), [2])
                self.assertTrue(result.get("approval_complete"))

    def test_approval_node_interrupt_payload_and_state_commitment(self):
        """T010: Verify approval_node calls interrupt() with structured payload and commits interrupt snapshot."""
        db_path = str(self.root / "state_t010.db")
        thread_id = "test-t010-thread"
        graph_config = {"configurable": {"thread_id": thread_id}}
        state = self.build_test_state()

        with SqliteSaver.from_conn_string(db_path) as saver:
            app = self.build_graph().compile(checkpointer=saver)

            result = app.invoke(state, config=graph_config)
            self.assertTrue(result.get("__interrupt__"))

            snapshot = app.get_state(graph_config)
            self.assertEqual(len(snapshot.tasks), 1)
            task = snapshot.tasks[0]
            self.assertEqual(task.name, "approval")
            self.assertEqual(len(task.interrupts), 1)

            payload = task.interrupts[0].value
            self.assertEqual(payload, {"review_directory": str(self.root), "cut_count": len(self.cuts)})

            # Checkpoint snapshot must NOT have committed approval_complete or approved_cut_ids
            self.assertFalse(snapshot.values.get("approval_complete"))
            self.assertEqual(snapshot.values.get("approved_cut_ids"), [])

            # Check SQLite tables directly to verify durability
            chk_count, write_count = self.get_sqlite_checkpoint_count(db_path, thread_id)
            self.assertGreater(chk_count, 0)

            # Test resumption with invalid cut ID raises ValueError without mutating state
            with self.assertRaises(ValueError):
                app.invoke(Command(resume={"approved_ids": [99]}), config=graph_config)

        # Empty candidate cuts must bypass interrupt
        state_empty = self.build_test_state(cortes_finais=[])
        with SqliteSaver.from_conn_string(str(self.root / "state_t010_empty.db")) as saver:
            app = self.build_graph().compile(checkpointer=saver)
            res_empty = app.invoke(state_empty, config={"configurable": {"thread_id": "empty-cuts"}})
            self.assertFalse(res_empty.get("__interrupt__"))
            self.assertTrue(res_empty.get("approval_complete"))
            self.assertEqual(res_empty.get("approved_cut_ids"), [])

    def test_run_with_review_manages_server_and_resumes_with_command(self):
        """T011: Verify run_with_review drives external server and resumes with Command(resume=...)."""
        db_path = str(self.root / "state_t011.db")
        thread_id = "test-t011-thread"
        graph_config = {"configurable": {"thread_id": thread_id}}
        state = self.build_test_state()
        editor_calls = []

        with patch.object(orchestrator, "cut_and_format_video", return_value=[str(self.root / "out.mp4")]) as mock_cut:
            with SqliteSaver.from_conn_string(db_path) as saver:
                app = self.build_graph(editor_calls=editor_calls).compile(checkpointer=saver)

                with patch.object(orchestrator, "wait_for_approval", return_value=[2]) as mock_wait:
                    result = orchestrator.run_with_review(app, state, graph_config, review_port=9123)

                    mock_wait.assert_called_once_with(str(self.root), port=9123)
                    mock_cut.assert_called_once()
                    self.assertEqual(len(editor_calls), 1)
                    self.assertTrue(result.get("approval_complete"))
                    self.assertEqual(result.get("approved_cut_ids"), [2])

                # Server abort (e.g. KeyboardInterrupt) leaves interrupt state in checkpointer
                thread_id_abort = "test-t011-abort"
                config_abort = {"configurable": {"thread_id": thread_id_abort}}
                with patch.object(orchestrator, "wait_for_approval", side_effect=KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        orchestrator.run_with_review(app, state, config_abort)

                snap_abort = app.get_state(config_abort)
                self.assertTrue(any(t.interrupts for t in snap_abort.tasks))

    def test_resuming_with_valid_decision_bypasses_http_server(self):
        """T014: Verify resuming with pre-existing valid decision.json bypasses HTTP server."""
        db_path = str(self.root / "state_t014.db")
        thread_id = "test-t014-thread"
        graph_config = {"configurable": {"thread_id": thread_id}}
        state = self.build_test_state()
        editor_calls = []

        save_approval_decision(self.root, [1])

        with patch.object(orchestrator, "cut_and_format_video", return_value=[str(self.root / "out.mp4")]) as mock_cut:
            with SqliteSaver.from_conn_string(db_path) as saver:
                app = self.build_graph(editor_calls=editor_calls).compile(checkpointer=saver)

                with patch.object(orchestrator, "wait_for_approval") as mock_wait:
                    result = orchestrator.run_with_review(app, state, graph_config, restart=False)

                    mock_wait.assert_not_called()
                    mock_cut.assert_called_once()
                    self.assertEqual(len(editor_calls), 1)
                    self.assertTrue(result.get("approval_complete"))
                    self.assertEqual(result.get("approved_cut_ids"), [1])

                thread_id_resume = "test-t014-resume"
                config_resume = {"configurable": {"thread_id": thread_id_resume}}
                rev_dir_resume = self.root / "rev_resume"
                rev_dir_resume.mkdir()
                (rev_dir_resume / "review.json").write_text((self.root / "review.json").read_text(encoding="utf-8"), encoding="utf-8")
                state_resume = self.build_test_state(review_directory=str(rev_dir_resume))

                app.invoke(state_resume, config=config_resume)
                snap = app.get_state(config_resume)
                self.assertTrue(any(t.interrupts for t in snap.tasks))

                save_approval_decision(rev_dir_resume, [2])

                with patch.object(orchestrator, "wait_for_approval") as mock_wait_resume:
                    res_resume = orchestrator.run_with_review(app, state_resume, config_resume, restart=False)
                    mock_wait_resume.assert_not_called()
                    self.assertTrue(res_resume.get("approval_complete"))
                    self.assertEqual(res_resume.get("approved_cut_ids"), [2])

    def test_corrupted_or_missing_decision_triggers_fallback_to_server(self):
        """T015: Verify corrupted or missing decision.json triggers fallback to review server."""
        db_path = str(self.root / "state_t015.db")
        thread_id_missing = "test-t015-missing"
        config_missing = {"configurable": {"thread_id": thread_id_missing}}
        state_missing = self.build_test_state()

        with patch.object(orchestrator, "cut_and_format_video", return_value=[]):
            with SqliteSaver.from_conn_string(db_path) as saver:
                app = self.build_graph().compile(checkpointer=saver)

                # Scenario 1: Missing decision.json -> falls back to wait_for_approval
                self.assertFalse((self.root / "decision.json").exists())
                with patch.object(orchestrator, "wait_for_approval", return_value=[1]) as mock_wait:
                    res1 = orchestrator.run_with_review(app, state_missing, config_missing, restart=False)
                    mock_wait.assert_called_once_with(str(self.root), port=8765)
                    self.assertEqual(res1.get("approved_cut_ids"), [1])

                # Scenario 2: Corrupted decision.json (invalid JSON) -> falls back to wait_for_approval
                thread_id_corrupt1 = "test-t015-corrupt1"
                config_corrupt1 = {"configurable": {"thread_id": thread_id_corrupt1}}
                rev_dir_corrupt = self.root / "rev_corrupt"
                rev_dir_corrupt.mkdir()
                (rev_dir_corrupt / "review.json").write_text((self.root / "review.json").read_text(encoding="utf-8"), encoding="utf-8")
                (rev_dir_corrupt / "decision.json").write_text("invalid json content {{{", encoding="utf-8")
                state_corrupt = self.build_test_state(review_directory=str(rev_dir_corrupt))

                with patch.object(orchestrator, "wait_for_approval", return_value=[2]) as mock_wait_corrupt:
                    res2 = orchestrator.run_with_review(app, state_corrupt, config_corrupt1, restart=False)
                    mock_wait_corrupt.assert_called_once_with(str(rev_dir_corrupt), port=8765)
                    self.assertEqual(res2.get("approved_cut_ids"), [2])

                # Scenario 3: Invalid decision.json content (out of range cut IDs) -> falls back to wait_for_approval
                thread_id_corrupt2 = "test-t015-corrupt2"
                config_corrupt2 = {"configurable": {"thread_id": thread_id_corrupt2}}
                rev_dir_invalid = self.root / "rev_invalid"
                rev_dir_invalid.mkdir()
                (rev_dir_invalid / "review.json").write_text((self.root / "review.json").read_text(encoding="utf-8"), encoding="utf-8")
                (rev_dir_invalid / "decision.json").write_text('{"approved_ids": [999]}', encoding="utf-8")
                state_invalid = self.build_test_state(review_directory=str(rev_dir_invalid))

                with patch.object(orchestrator, "wait_for_approval", return_value=[1]) as mock_wait_invalid:
                    res3 = orchestrator.run_with_review(app, state_invalid, config_corrupt2, restart=False)
                    mock_wait_invalid.assert_called_once_with(str(rev_dir_invalid), port=8765)
                    self.assertEqual(res3.get("approved_cut_ids"), [1])


class ReviewSceneScriptingTests(unittest.TestCase):
    """User Story 3: Cenas persistidas e visíveis na revisão humana (T016, T017, T020)."""

    def setUp(self):
        Path("output").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir="output")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

        self.cuts_with_scenes = [
            CorteVideo(
                title="Corte com Cenas",
                description="Descrição detalhada",
                start_time=10.0,
                end_time=25.0,
                scenes=[
                    Scene(
                        start_word="Comecei",
                        end_word="projeto",
                        visual_metaphor="mesa de trabalho",
                        animation_trigger="zoom_in",
                    ),
                    Scene(
                        start_word="Depois",
                        end_word="sucesso",
                        visual_metaphor="gráfico subindo",
                        animation_trigger="cut_transition",
                    ),
                ],
            )
        ]

    def test_t016_review_manifest_serialization_deserialization_with_scenes(self):
        """T016: ReviewManifest serialization and deserialization of cuts with scenes into review.json."""
        manifest = ReviewManifest(
            cuts=self.cuts_with_scenes,
            pause_plans=[
                identity_plan(c.start_time, c.end_time, PauseSettings(enabled=False))
                for c in self.cuts_with_scenes
            ],
        )
        json_str = manifest.model_dump_json()
        review_file = self.root / "review.json"
        review_file.write_text(json_str, encoding="utf-8")

        loaded_manifest = ReviewManifest.model_validate_json(review_file.read_text(encoding="utf-8"))
        self.assertEqual(len(loaded_manifest.cuts), 1)
        loaded_cut = loaded_manifest.cuts[0]
        self.assertEqual(loaded_cut.title, "Corte com Cenas")
        self.assertEqual(len(loaded_cut.scenes), 2)
        self.assertEqual(loaded_cut.scenes[0].start_word, "Comecei")
        self.assertEqual(loaded_cut.scenes[0].end_word, "projeto")
        self.assertEqual(loaded_cut.scenes[0].visual_metaphor, "mesa de trabalho")
        self.assertEqual(loaded_cut.scenes[0].animation_trigger, "zoom_in")
        self.assertEqual(loaded_cut.scenes[1].start_word, "Depois")
        self.assertEqual(loaded_cut.scenes[1].end_word, "sucesso")
        self.assertEqual(loaded_cut.scenes[1].visual_metaphor, "gráfico subindo")
        self.assertEqual(loaded_cut.scenes[1].animation_trigger, "cut_transition")

        plans = load_review_plans(str(self.root), self.cuts_with_scenes)
        self.assertEqual(len(plans), 1)

    def test_t017_render_review_page_displays_scenes_when_present(self):
        """T017: render_review_page includes scene breakdown details when scenes are present."""
        page = render_review_page(self.cuts_with_scenes, "token-123")
        self.assertIn('<div class="scenes">', page)
        self.assertIn("Comecei", page)
        self.assertIn("projeto", page)
        self.assertIn("mesa de trabalho", page)
        self.assertIn("zoom_in", page)
        self.assertIn("gráfico subindo", page)
        self.assertIn("cut_transition", page)

    def test_t017_render_review_page_omits_scenes_when_empty(self):
        """T017: render_review_page omits scene breakdown when scenes list is empty."""
        cuts_without_scenes = [
            CorteVideo(
                title="Corte Legado",
                description="Sem cenas",
                start_time=0.0,
                end_time=10.0,
                scenes=[],
            )
        ]
        page = render_review_page(cuts_without_scenes, "token-123")
        self.assertNotIn('<div class="scenes">', page)
        self.assertNotIn('class="scenes-title"', page)

    def test_t017_render_review_page_escapes_special_characters_in_scenes(self):
        """T017: render_review_page safely HTML escapes scene fields."""
        cuts_with_xss = [
            CorteVideo(
                title="Corte XSS",
                description="Desc",
                start_time=0.0,
                end_time=10.0,
                scenes=[
                    Scene(
                        start_word="<script>alert(1)</script>",
                        end_word="fim & teste",
                        visual_metaphor='imagem "especial" & bonita',
                        animation_trigger="<custom_anim>",
                    )
                ],
            )
        ]
        page = render_review_page(cuts_with_xss, "token-123")
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertIn("fim &amp; teste", page)
        self.assertIn("imagem &quot;especial&quot; &amp; bonita", page)
        self.assertIn("&lt;custom_anim&gt;", page)

    def test_t020_review_server_serves_scene_cards_end_to_end(self):
        """T020: Verify review server serves scene breakdown HTML and accepts approval decision."""
        manifest = ReviewManifest(
            cuts=self.cuts_with_scenes,
            pause_plans=[
                identity_plan(c.start_time, c.end_time, PauseSettings(enabled=False))
                for c in self.cuts_with_scenes
            ],
        )
        (self.root / "review.json").write_text(manifest.model_dump_json(), encoding="utf-8")
        (self.root / "preview-1.mp4").write_bytes(b"dummy-video-data")

        with create_review_server(str(self.root), port=0) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}"
                with urlopen(url, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    body = response.read().decode("utf-8")
                    self.assertIn('<div class="scenes">', body)
                    self.assertIn("mesa de trabalho", body)
                    parser = TokenParser()
                    parser.feed(body)
                    self.assertIsNotNone(parser.token)

                form = {"token": parser.token, "action": "approve", "cut_id": 1}
                with urlopen(Request(url + "/approve", data=urlencode(form).encode()), timeout=5) as response:
                    self.assertEqual(response.status, 200)
                self.assertEqual(server.decision, [1])
            finally:
                server.shutdown()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
