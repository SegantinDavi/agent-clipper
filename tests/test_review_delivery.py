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
from clipper.core.orchestrator import VideoState


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


if __name__ == "__main__":
    unittest.main()
