"""
Unit and integration test suite for Feature 019: HITL Review Delivery.
Tests cover:
- US1: Scene script inspection, metadata fallbacks, placeholders, and responsiveness.
- US2: Selective cut gating, decision.json validation, skip auditing, and zero-subprocess termination.
"""

import html
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import tests
from clipper.core.schemas import CorteVideo, Scene
from clipper.review.review import (
    ApprovalDecision,
    load_approval_decision,
    render_review_page,
    save_approval_decision,
    validate_approval,
)
from clipper.core.orchestrator import (
    VideoState,
    coder_node,
    execution_node,
    route_approval_outcome,
    create_graph,
    advance_cut_node,
)


class ReviewDeliveryFixtureMixin:
    """Shared fixtures and factories for Feature 019 tests."""

    def create_sample_scenes(self) -> list[Scene]:
        return [
            Scene(
                start_word="Bem-vindos",
                end_word="começar",
                visual_metaphor="Gráfico de barras ascendente",
                animation_trigger="zoom_in",
            ),
            Scene(
                start_word="Importante",
                end_word="lembrar",
                visual_metaphor="Sinal de alerta pulsante",
                animation_trigger="impact",
            ),
        ]

    def create_sample_cuts(self) -> list[CorteVideo]:
        return [
            CorteVideo(
                title="Corte 1 - Estratégia",
                description="Visão geral da estratégia",
                start_time=0.0,
                end_time=15.0,
                scenes=self.create_sample_scenes(),
            ),
            CorteVideo(
                title="Corte 2 - Sem Cenas",
                description="Trecho sem lista de cenas definida",
                start_time=20.0,
                end_time=35.0,
                scenes=[],
            ),
            CorteVideo(
                title="Corte 3 - Campos Vazios",
                description="Trecho com cenas contendo campos em branco",
                start_time=40.0,
                end_time=55.0,
                scenes=[
                    Scene(
                        start_word="palavra1",
                        end_word="palavra2",
                        visual_metaphor="   ",
                        animation_trigger="   ",
                    )
                ],
            ),
        ]

    def create_mock_review_dir(
        self,
        base_dir: Path,
        cuts: list[CorteVideo] | None = None,
        decision_data: dict | None = None,
    ) -> Path:
        rev_dir = base_dir / "review_019"
        rev_dir.mkdir(parents=True, exist_ok=True)
        cuts = cuts or self.create_sample_cuts()
        manifest_data = {
            "cuts": [cut.model_dump() for cut in cuts],
            "pause_plans": [],
        }
        (rev_dir / "review.json").write_text(
            json.dumps(manifest_data), encoding="utf-8"
        )
        if decision_data is not None:
            (rev_dir / "decision.json").write_text(
                json.dumps(decision_data), encoding="utf-8"
            )
        return rev_dir


class TestReviewDeliverySetup(unittest.TestCase, ReviewDeliveryFixtureMixin):
    """Smoke test to verify fixture initialization and basic module integration."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_fixtures_initialization(self):
        cuts = self.create_sample_cuts()
        self.assertEqual(len(cuts), 3)
        self.assertEqual(len(cuts[0].scenes), 2)
        self.assertEqual(len(cuts[1].scenes), 0)
        self.assertEqual(len(cuts[2].scenes), 1)

        rev_dir = self.create_mock_review_dir(
            self.root,
            cuts,
            decision_data={"approved_ids": [1], "approved_cut_ids": [1]},
        )
        self.assertTrue((rev_dir / "review.json").exists())
        self.assertTrue((rev_dir / "decision.json").exists())


class TestFoundationalApprovalSynchronization(unittest.TestCase, ReviewDeliveryFixtureMixin):
    """Unit tests for Phase 2: bidirectional synchronization and validation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_video_state_approved_cut_ids_type(self):
        annotations = VideoState.__annotations__
        self.assertIn("approved_cut_ids", annotations)
        self.assertEqual(annotations["approved_cut_ids"], list[int | str])

    def test_approval_decision_bidirectional_sync(self):
        # Initialized with approved_cut_ids only
        d1 = ApprovalDecision(approved_cut_ids=["cut-0", "cut-2"])
        self.assertEqual(d1.approved_cut_ids, ["cut-0", "cut-2"])
        self.assertEqual(d1.approved_ids, ["cut-0", "cut-2"])

        # Initialized with approved_ids only
        d2 = ApprovalDecision(approved_ids=[1, 3])
        self.assertEqual(d2.approved_cut_ids, [1, 3])
        self.assertEqual(d2.approved_ids, [1, 3])

        # model_validate with approved_cut_ids only
        d3 = ApprovalDecision.model_validate({"approved_cut_ids": ["cut-1"]})
        self.assertEqual(d3.approved_cut_ids, ["cut-1"])
        self.assertEqual(d3.approved_ids, ["cut-1"])

        # model_validate with approved_ids only
        d4 = ApprovalDecision.model_validate({"approved_ids": [2]})
        self.assertEqual(d4.approved_cut_ids, [2])
        self.assertEqual(d4.approved_ids, [2])

        # Missing both keys in dict raises ValueError
        with self.assertRaises(ValueError):
            ApprovalDecision.model_validate({})

    def test_save_approval_decision_serializes_both_keys(self):
        # With list of strings
        p1 = save_approval_decision(self.root, ["cut-0", "cut-2"])
        raw1 = json.loads(p1.read_text(encoding="utf-8"))
        self.assertEqual(raw1["approved_ids"], ["cut-0", "cut-2"])
        self.assertEqual(raw1["approved_cut_ids"], ["cut-0", "cut-2"])

        # With list of ints
        p2 = save_approval_decision(self.root, [1, 2])
        raw2 = json.loads(p2.read_text(encoding="utf-8"))
        self.assertEqual(raw2["approved_ids"], [1, 2])
        self.assertEqual(raw2["approved_cut_ids"], [1, 2])

    def test_load_approval_decision_supports_strings_and_ints(self):
        # Integer IDs loaded
        save_approval_decision(self.root, [2, 1])
        loaded_ints = load_approval_decision(self.root)
        self.assertEqual(loaded_ints, [1, 2])

        # String IDs loaded without crash
        save_approval_decision(self.root, ["cut-2", "cut-0"])
        loaded_strs = load_approval_decision(self.root)
        self.assertEqual(loaded_strs, ["cut-0", "cut-2"])

        # Validate with cut_count
        save_approval_decision(self.root, [1])
        self.assertEqual(load_approval_decision(self.root, cut_count=2), [1])

        # Missing decision returns None
        empty_dir = self.root / "empty_dir"
        empty_dir.mkdir()
        self.assertIsNone(load_approval_decision(empty_dir))

    def test_validate_approval_string_and_int_rules(self):
        # Valid integers within cut_count
        self.assertEqual(validate_approval({"approved_cut_ids": [1, 2]}, 2), [1, 2])
        self.assertEqual(validate_approval({"approved_ids": [2]}, 2), [2])

        # Valid string identifiers
        self.assertEqual(validate_approval({"approved_cut_ids": ["cut-0", "cut-1"]}, 2), ["cut-0", "cut-1"])

        # Empty selection is valid (rejection of all cuts)
        self.assertEqual(validate_approval({"approved_cut_ids": []}, 2), [])

        # Invalid: out of bounds ints
        with self.assertRaises(ValueError):
            validate_approval({"approved_cut_ids": [0]}, 2)
        with self.assertRaises(ValueError):
            validate_approval({"approved_cut_ids": [3]}, 2)

        # Invalid: duplicates
        with self.assertRaises(ValueError):
            validate_approval({"approved_cut_ids": [1, 1]}, 2)
        with self.assertRaises(ValueError):
            validate_approval({"approved_cut_ids": ["cut-0", "cut-0"]}, 2)

        # Invalid: pure digit string (must be integer index)
        with self.assertRaises(ValueError):
            validate_approval({"approved_cut_ids": ["1"]}, 2)

        # Invalid: empty or whitespace string
        with self.assertRaises(ValueError):
            validate_approval({"approved_cut_ids": [""]}, 2)
        with self.assertRaises(ValueError):
            validate_approval({"approved_cut_ids": ["   "]}, 2)

        # Invalid: missing both keys / empty dict
        with self.assertRaises(ValueError):
            validate_approval({}, 2)


class TestUserStory1SceneDisplayAndFallbacks(unittest.TestCase, ReviewDeliveryFixtureMixin):
    """
    T004 [US1]: Unit and contract tests for render_review_page scene display,
    'No scene script available' fallback, and '—' placeholders.
    """

    def setUp(self):
        self.cuts = self.create_sample_cuts()

    def test_render_review_page_complete_scenes_structure(self):
        """Verifies DOM structure and presentation for cuts with valid scenes."""
        cut = self.cuts[0]
        self.assertEqual(len(cut.scenes), 2)
        html_page = render_review_page([cut], "test-token")

        # Container & Title
        self.assertIn('<div class="scenes">', html_page)
        self.assertIn('<h3 class="scenes-title">Cenas Planejadas (2)</h3>', html_page)
        self.assertIn('<ol class="scenes-list">', html_page)

        # Scene items DOM contract
        self.assertIn('<span class="scene-words">"Bem-vindos … começar"</span>', html_page)
        self.assertIn('<span class="scene-metaphor">Metáfora: <em>Gráfico de barras ascendente</em></span>', html_page)
        self.assertIn('<span class="scene-trigger">Gatilho: <code>zoom_in</code></span>', html_page)

        self.assertIn('<span class="scene-words">"Importante … lembrar"</span>', html_page)
        self.assertIn('<span class="scene-metaphor">Metáfora: <em>Sinal de alerta pulsante</em></span>', html_page)
        self.assertIn('<span class="scene-trigger">Gatilho: <code>impact</code></span>', html_page)

        # Ordering: Scene 1 must appear before Scene 2
        idx1 = html_page.index("Bem-vindos")
        idx2 = html_page.index("Importante")
        self.assertLess(idx1, idx2)

    def test_render_review_page_escapes_xss_in_scenes(self):
        """Verifies that special characters in scenes are properly HTML escaped."""
        xss_cut = CorteVideo(
            title="XSS Cut",
            description="Testing XSS",
            start_time=0.0,
            end_time=10.0,
            scenes=[
                Scene(
                    start_word='<script>alert("1")</script>',
                    end_word='fim & teste "quotes"',
                    visual_metaphor='<b>Metáfora perigosa</b> & "mais"',
                    animation_trigger='trigger <script>',
                )
            ],
        )
        html_page = render_review_page([xss_cut], "test-token")

        # Raw HTML injection must not appear
        self.assertNotIn('<script>alert("1")</script>', html_page)
        self.assertNotIn('<b>Metáfora perigosa</b>', html_page)

        # Escaped versions must appear
        self.assertIn(html.escape('<script>alert("1")</script>'), html_page)
        self.assertIn(html.escape('fim & teste "quotes"'), html_page)
        self.assertIn(html.escape('<b>Metáfora perigosa</b> & "mais"'), html_page)
        self.assertIn(html.escape('trigger <script>'), html_page)

    def test_render_review_page_empty_scenes_fallback(self):
        """FR-004 / CTR-019-01: When cut.scenes is empty list, renders explicit fallback container."""
        empty_cut = CorteVideo(
            title="Empty Scenes Cut",
            description="Testing empty scenes list",
            start_time=0.0,
            end_time=10.0,
            scenes=[],
        )
        html_page = render_review_page([empty_cut], "test-token")

        # Fallback container and message required by contract
        self.assertIn('<div class="scenes scenes-empty">', html_page)
        self.assertIn('<h3 class="scenes-title">Cenas Planejadas</h3>', html_page)
        self.assertIn('<p class="scenes-fallback">No scene script available</p>', html_page)

        # Ordered list must NOT be rendered when empty
        self.assertNotIn('<ol class="scenes-list">', html_page)

    def test_render_review_page_null_scenes_fallback(self):
        """FR-004 / CTR-019-01: When cut.scenes is None, renders explicit fallback container."""
        null_cut = CorteVideo.model_construct(
            title="Null Scenes Cut",
            description="Testing None scenes",
            start_time=0.0,
            end_time=10.0,
            scenes=None,
        )
        html_page = render_review_page([null_cut], "test-token")

        self.assertIn('<div class="scenes scenes-empty">', html_page)
        self.assertIn('<h3 class="scenes-title">Cenas Planejadas</h3>', html_page)
        self.assertIn('<p class="scenes-fallback">No scene script available</p>', html_page)
        self.assertNotIn('<ol class="scenes-list">', html_page)

    def test_render_review_page_field_placeholders_for_empty_and_whitespace(self):
        """FR-005 / CTR-019-01: Fields with None, empty string, or whitespace are replaced by '—'."""
        placeholder_cut = CorteVideo.model_construct(
            title="Placeholder Cut",
            description="Testing em-dash placeholder substitution",
            start_time=0.0,
            end_time=10.0,
            scenes=[
                Scene.model_construct(
                    start_word="",
                    end_word="   ",
                    visual_metaphor=None,
                    animation_trigger="   ",
                )
            ],
        )
        html_page = render_review_page([placeholder_cut], "test-token")

        # Placeholders: literal em-dash U+2014 ("—")
        self.assertIn('<span class="scene-words">"— … —"</span>', html_page)
        self.assertIn('<span class="scene-metaphor">Metáfora: <em>—</em></span>', html_page)
        self.assertIn('<span class="scene-trigger">Gatilho: <code>—</code></span>', html_page)


class TestUserStory1ViewportResponsiveness(unittest.TestCase, ReviewDeliveryFixtureMixin):
    """
    T005 [US1]: Unit tests for viewport responsiveness CSS (meta viewport,
    word-break, mobile max-width 480px rules).
    """

    def setUp(self):
        self.cuts = self.create_sample_cuts()
        self.html_page = render_review_page(self.cuts, "test-token")

    def test_meta_viewport_tag_present(self):
        """FR-003 / CTR-019-01: Meta viewport tag must be present for mobile responsiveness."""
        self.assertIn(
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            self.html_page,
        )

    def test_box_sizing_border_box_present(self):
        """FR-003: Box sizing border-box applied globally."""
        self.assertIn("box-sizing:border-box", self.html_page.replace(" ", ""))

    def test_word_break_and_overflow_wrap_present(self):
        """CTR-019-01: Word break and overflow wrap rules present to prevent horizontal scroll."""
        clean_page = self.html_page.replace(" ", "")
        self.assertTrue(
            "word-break:break-word" in clean_page or "overflow-wrap:anywhere" in clean_page or "overflow-wrap:break-word" in clean_page,
            "CSS should include word-break or overflow-wrap for scene content wrapping.",
        )

    def test_mobile_media_query_for_viewports_down_to_320px(self):
        """FR-003 / SC-005 / CTR-019-01: CSS must include @media (max-width: 480px) mobile rules."""
        clean_page = self.html_page.replace(" ", "")
        self.assertIn("@media(max-width:480px)", clean_page)


class TestUserStory2DecisionFailFastValidation(unittest.TestCase, ReviewDeliveryFixtureMixin):
    """
    T010 [US2]: Unit and contract tests for decision.json fail-fast validation
    (missing, malformed) in coder_node.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.cuts = self.create_sample_cuts()

    def test_missing_decision_file_raises_value_error(self):
        """FR-009 / CTR-019-02: If review_directory is present but decision.json is missing, raise ValueError."""
        empty_review_dir = self.root / "empty_review"
        empty_review_dir.mkdir(parents=True)
        state: VideoState = {
            "cortes_finais": [c.model_dump() for c in self.cuts],
            "review_directory": str(empty_review_dir),
            "approval_complete": True,
            "approved_cut_ids": [1],
            "current_cut_index": 0,
            "render_attempts": 0,
        }
        with self.assertRaises(ValueError) as ctx:
            coder_node(state)
        self.assertIn("decision.json not found in review directory", str(ctx.exception))

    def test_corrupted_decision_file_raises_value_error(self):
        """FR-009 / CTR-019-02: If decision.json is malformed/unreadable, raise ValueError."""
        corrupted_dir = self.root / "corrupted_review"
        corrupted_dir.mkdir(parents=True)
        (corrupted_dir / "decision.json").write_text("{not-valid-json", encoding="utf-8")

        state: VideoState = {
            "cortes_finais": [c.model_dump() for c in self.cuts],
            "review_directory": str(corrupted_dir),
            "approval_complete": True,
            "approved_cut_ids": [1],
            "current_cut_index": 0,
            "render_attempts": 0,
        }
        with self.assertRaises(ValueError) as ctx:
            coder_node(state)
        self.assertIn("decision.json is unreadable or structurally invalid", str(ctx.exception))

    def test_structurally_invalid_decision_file_raises_value_error(self):
        """FR-009 / CTR-019-02: If decision.json lacks both approved_ids and approved_cut_ids, raise ValueError."""
        invalid_dir = self.root / "invalid_review"
        invalid_dir.mkdir(parents=True)
        (invalid_dir / "decision.json").write_text(json.dumps({"some_key": 123}), encoding="utf-8")

        state: VideoState = {
            "cortes_finais": [c.model_dump() for c in self.cuts],
            "review_directory": str(invalid_dir),
            "approval_complete": True,
            "approved_cut_ids": [1],
            "current_cut_index": 0,
            "render_attempts": 0,
        }
        with self.assertRaises(ValueError) as ctx:
            coder_node(state)
        self.assertIn("decision.json is unreadable or structurally invalid", str(ctx.exception))

    @patch("clipper.core.orchestrator.create_llm_client")
    def test_missing_review_directory_falls_back_to_state(self, mock_client_factory):
        """CTR-019-02: Isolated unit tests with omitted/empty review_directory fall back to state."""
        mock_raw = MagicMock()
        mock_client_factory.return_value = mock_raw
        mock_instructor = MagicMock()
        mock_payload = MagicMock()
        mock_payload.script_code = "print('mock script')"
        mock_instructor.chat.completions.create.return_value = mock_payload

        with patch("instructor.from_openai", return_value=mock_instructor):
            state: VideoState = {
                "cortes_finais": [c.model_dump() for c in self.cuts],
                "review_directory": "",
                "approval_complete": True,
                "approved_cut_ids": [1],
                "current_cut_index": 0,
                "render_attempts": 0,
                "video_path": "/fake/video.mp4",
                "word_timestamps": [],
                "visual_identity": {},
            }
            # Should not raise ValueError for missing decision.json
            result = coder_node(state)
            self.assertIn("render_script_path", result)
            self.assertTrue(result["render_script_path"].endswith("render_script.py"))


class TestUserStory2CutGatingAndSkipLogging(unittest.TestCase, ReviewDeliveryFixtureMixin):
    """
    T011 [US2]: Unit and integration tests for cut gating, skip logging (INFO),
    unmatched cut ID handling (WARNING), and 0% subprocesses for unapproved cuts.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.cuts = self.create_sample_cuts()

    @patch("clipper.core.orchestrator.create_llm_client")
    def test_skip_logging_emits_info_for_unapproved_cuts_on_initial_pass(self, mock_client_factory):
        """FR-007 / CTR-019-02: Single-pass INFO log emitted for each unapproved cut."""
        mock_raw = MagicMock()
        mock_client_factory.return_value = mock_raw
        mock_instructor = MagicMock()
        mock_payload = MagicMock()
        mock_payload.script_code = "print('approved cut script')"
        mock_instructor.chat.completions.create.return_value = mock_payload

        with patch("instructor.from_openai", return_value=mock_instructor):
            with self.assertLogs("clipper.core.orchestrator", level="INFO") as log_capture:
                state: VideoState = {
                    "cortes_finais": [c.model_dump() for c in self.cuts],  # 3 cuts
                    "review_directory": "",
                    "approval_complete": True,
                    "approved_cut_ids": [2],  # Only cut 2 is approved
                    "current_cut_index": 0,
                    "render_attempts": 0,
                    "video_path": "/fake/video.mp4",
                    "word_timestamps": [],
                    "visual_identity": {},
                }
                coder_node(state)

                # Cuts 1 and 3 must be logged as skipped at INFO level
                output_logs = "\n".join(log_capture.output)
                self.assertIn("Cut '1' is not in approved_cut_ids. Skipping rendering.", output_logs)
                self.assertIn("Cut '3' is not in approved_cut_ids. Skipping rendering.", output_logs)

    @patch("clipper.core.orchestrator.create_llm_client")
    def test_skip_logging_does_not_repeat_on_retry_or_subsequent_cuts(self, mock_client_factory):
        """CTR-019-02: Skip audit is only emitted when current_cut_index == 0 and render_attempts == 0."""
        mock_raw = MagicMock()
        mock_client_factory.return_value = mock_raw
        mock_instructor = MagicMock()
        mock_payload = MagicMock()
        mock_payload.script_code = "print('retry script')"
        mock_instructor.chat.completions.create.return_value = mock_payload

        with patch("instructor.from_openai", return_value=mock_instructor):
            # Attempt > 0
            with self.assertLogs("clipper.core.orchestrator", level="INFO") as log_capture:
                state: VideoState = {
                    "cortes_finais": [c.model_dump() for c in self.cuts],
                    "review_directory": "",
                    "approval_complete": True,
                    "approved_cut_ids": [2],
                    "current_cut_index": 0,
                    "render_attempts": 1,
                    "render_error": "Some previous error",
                    "video_path": "/fake/video.mp4",
                    "word_timestamps": [],
                    "visual_identity": {},
                }
                coder_node(state)
                output_logs = "\n".join(log_capture.output)
                self.assertNotIn("is not in approved_cut_ids. Skipping rendering.", output_logs)

    @patch("subprocess.run")
    def test_zero_subprocesses_for_unapproved_cuts(self, mock_subprocess):
        """SC-002: Zero subprocesses launched for unapproved or empty cut selections."""
        state: VideoState = {
            "approved_cut_ids": [],
            "current_cut_index": 0,
            "render_script_path": "",
            "render_attempts": 0,
        }
        res = execution_node(state)
        mock_subprocess.assert_not_called()
        self.assertEqual(res["render_exit_code"], 0)

    @patch("clipper.core.orchestrator.create_llm_client")
    def test_deterministic_resolution_dict_id(self, mock_client_factory):
        """CTR-019-02 Rule 1: Explicit dictionary 'id' matching."""
        mock_raw = MagicMock()
        mock_client_factory.return_value = mock_raw
        mock_instructor = MagicMock()
        mock_payload = MagicMock()
        mock_payload.script_code = "print('dict id')"
        mock_instructor.chat.completions.create.return_value = mock_payload

        cuts_with_ids = [
            {"id": "cut_alpha", "title": "Alpha", "scenes": []},
            {"id": "cut_beta", "title": "Beta", "scenes": []},
        ]
        with patch("instructor.from_openai", return_value=mock_instructor):
            state: VideoState = {
                "cortes_finais": cuts_with_ids,
                "review_directory": "",
                "approval_complete": True,
                "approved_cut_ids": ["cut_beta"],
                "current_cut_index": 0,
                "render_attempts": 0,
                "video_path": "/fake/video.mp4",
                "word_timestamps": [],
                "visual_identity": {},
            }
            res = coder_node(state)
            self.assertEqual(res["render_error"], "")
            self.assertTrue(res["render_script_path"].endswith("render_script.py"))

    @patch("clipper.core.orchestrator.create_llm_client")
    def test_deterministic_resolution_cut_pattern(self, mock_client_factory):
        r"""CTR-019-02 Rule 2: Positional regex ^cut[-_]?(\d+)$ (0-based)."""
        mock_raw = MagicMock()
        mock_client_factory.return_value = mock_raw
        mock_instructor = MagicMock()
        mock_payload = MagicMock()
        mock_payload.script_code = "print('pattern')"
        mock_instructor.chat.completions.create.return_value = mock_payload

        with patch("instructor.from_openai", return_value=mock_instructor):
            state: VideoState = {
                "cortes_finais": [c.model_dump() for c in self.cuts],
                "review_directory": "",
                "approval_complete": True,
                "approved_cut_ids": ["cut-1"],  # 0-based index 1 -> second cut
                "current_cut_index": 0,
                "render_attempts": 0,
                "video_path": "/fake/video.mp4",
                "word_timestamps": [],
                "visual_identity": {},
            }
            res = coder_node(state)
            self.assertEqual(res["render_error"], "")

    def test_unmatched_cut_id_emits_warning_and_does_not_crash(self):
        """CTR-019-02 Section 3.3 / 3.4: Unmatched cut ID logs warning and skips without crash."""
        state: VideoState = {
            "cortes_finais": [c.model_dump() for c in self.cuts],
            "review_directory": "",
            "approval_complete": True,
            "approved_cut_ids": ["cut-999"],  # Out of range / unmatched
            "current_cut_index": 0,
            "render_attempts": 0,
            "video_path": "/fake/video.mp4",
            "word_timestamps": [],
            "visual_identity": {},
        }
        with self.assertLogs("clipper.core.orchestrator", level="WARNING") as log_capture:
            res = coder_node(state)
            output_logs = "\n".join(log_capture.output)
            self.assertIn("Approved cut ID 'cut-999' does not match any cut in VideoState.", output_logs)
            self.assertEqual(res["render_script_path"], "")
            self.assertEqual(res.get("render_exit_code"), 0)


class TestUserStory2RouteApprovalOutcome(unittest.TestCase, ReviewDeliveryFixtureMixin):
    """
    T012 [US2]: Unit and integration tests for route_approval_outcome empty approval
    routing to END with zero subprocesses.
    """

    def test_route_approval_outcome_empty_approved_ids_routes_to_end(self):
        """FR-008 / SC-003 / CTR-019-02: Empty approved cuts routes to end with warning."""
        state: VideoState = {
            "approved_cut_ids": [],
            "approval_complete": True,
        }
        with self.assertLogs("clipper.core.orchestrator", level="WARNING") as log_capture:
            dest = route_approval_outcome(state)
            self.assertEqual(dest, "end")
            output_logs = "\n".join(log_capture.output)
            self.assertIn("No cuts approved in decision. Skipping all rendering.", output_logs)

    def test_route_approval_outcome_with_approved_ids_routes_to_coder(self):
        """CTR-019-02: Non-empty approved cuts routes to coder node."""
        state: VideoState = {
            "approved_cut_ids": [1],
            "approval_complete": True,
        }
        dest = route_approval_outcome(state)
        self.assertEqual(dest, "coder")

    def test_graph_wires_route_approval_outcome_conditional_edge(self):
        """Verifies create_graph() binds route_approval_outcome to approval node branching."""
        graph = create_graph()
        # Ensure approval node has conditional edges configured in StateGraph
        branches = graph.branches.get("approval", {})
        self.assertTrue(len(branches) > 0)
        branch = list(branches.values())[0]
        self.assertIn("coder", branch.ends)
        self.assertIn("end", branch.ends)
        self.assertEqual(branch.ends["end"], "__end__")


class TestUserStory2CheckpointResumption(unittest.TestCase, ReviewDeliveryFixtureMixin):
    """
    T013 [US2]: Resumption test verifying checkpoint reload re-applies decision.json
    from review directory.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.cuts = self.create_sample_cuts()

    @patch("clipper.core.orchestrator.create_llm_client")
    def test_resumed_coder_node_reads_decision_from_disk(self, mock_client_factory):
        """FR-010 / CTR-019-02: coder_node reads decision.json from disk and re-applies approved_cut_ids gate."""
        mock_raw = MagicMock()
        mock_client_factory.return_value = mock_raw
        mock_instructor = MagicMock()
        mock_payload = MagicMock()
        mock_payload.script_code = "print('resumed script')"
        mock_instructor.chat.completions.create.return_value = mock_payload

        # Mock review directory containing decision.json with only cut 2 approved
        rev_dir = self.create_mock_review_dir(
            self.root,
            cuts=self.cuts,
            decision_data={"approved_ids": [2], "approved_cut_ids": [2]},
        )

        with patch("instructor.from_openai", return_value=mock_instructor):
            with self.assertLogs("clipper.core.orchestrator", level="INFO") as log_capture:
                # VideoState has old state (e.g. approved_cut_ids [1, 2, 3])
                state: VideoState = {
                    "cortes_finais": [c.model_dump() for c in self.cuts],
                    "review_directory": str(rev_dir),
                    "approval_complete": True,
                    "approved_cut_ids": [1, 2, 3],  # Old or broader state
                    "current_cut_index": 0,
                    "render_attempts": 0,
                    "video_path": "/fake/video.mp4",
                    "word_timestamps": [],
                    "visual_identity": {},
                }
                coder_node(state)

                # Must use decision.json from disk ([2]), skipping cuts 1 and 3
                output_logs = "\n".join(log_capture.output)
                self.assertIn("Cut '1' is not in approved_cut_ids. Skipping rendering.", output_logs)
                self.assertIn("Cut '3' is not in approved_cut_ids. Skipping rendering.", output_logs)
                self.assertNotIn("Cut '2' is not in approved_cut_ids", output_logs)


if __name__ == "__main__":
    unittest.main()

