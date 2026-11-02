import unittest
from clipper.core.schemas import CorteVideo, Scene
from clipper.video.motion_engine import (
    SceneInterval,
    MotionPlan,
    build_motion_plan,
    normalize_word,
)


class TestMotionEngine(unittest.TestCase):
    def setUp(self):
        self.sample_words = [
            {"word": "Olá", "start": 10.0, "end": 10.5},
            {"word": "mundo,", "start": 10.6, "end": 11.0},
            {"word": "estamos", "start": 11.2, "end": 11.5},
            {"word": "aqui", "start": 11.6, "end": 11.8},
            {"word": "para", "start": 11.9, "end": 12.0},
            {"word": "revelar", "start": 12.1, "end": 12.5},
            {"word": "algo", "start": 12.6, "end": 12.8},
            {"word": "surpreendente.", "start": 12.9, "end": 13.5},
            {"word": "Prestem", "start": 13.6, "end": 14.0},
            {"word": "muita", "start": 14.1, "end": 14.3},
            {"word": "atenção", "start": 14.4, "end": 14.8},
            {"word": "nisso.", "start": 14.9, "end": 15.0},
        ]

        self.sample_scenes = [
            Scene(
                start_word="Olá",
                end_word="mundo",
                visual_metaphor="globo girando suavemente",
                animation_trigger="zoom_in",
            ),
            Scene(
                start_word="estamos",
                end_word="surpreendente",
                visual_metaphor="raio de luz atingindo o centro",
                animation_trigger="impact",
            ),
            Scene(
                start_word="Prestem",
                end_word="nisso",
                visual_metaphor="placa de exclamação vibrando",
                animation_trigger="cut_transition",
            ),
        ]

        self.corte_com_cenas = CorteVideo(
            id=1,
            title="Corte Revelador",
            description="Discussão de alto impacto",
            start_time=10.0,
            end_time=15.0,
            scenes=self.sample_scenes,
        )

        self.corte_sem_cenas = CorteVideo(
            id=2,
            title="Corte Simples",
            description="Sem cenas planejadas",
            start_time=20.0,
            end_time=25.0,
            scenes=[],
        )

    def test_normalize_word(self):
        self.assertEqual(normalize_word("Olá,"), "ola")
        self.assertEqual(normalize_word("Surpreendente!"), "surpreendente")
        self.assertEqual(normalize_word("...Uber?"), "uber")

    def test_build_motion_plan_with_scenes(self):
        plan = build_motion_plan(self.corte_com_cenas, self.sample_words, duration=5.0)
        self.assertIsInstance(plan, MotionPlan)
        self.assertEqual(plan.duration, 5.0)
        self.assertEqual(len(plan.intervals), 3)

        # First interval starts at 0.0
        self.assertEqual(plan.intervals[0].rel_start, 0.0)
        # Last interval ends at 5.0
        self.assertEqual(plan.intervals[-1].rel_end, 5.0)

        # Check contiguous coverage: rel_end of i == rel_start of i+1
        for i in range(len(plan.intervals) - 1):
            self.assertAlmostEqual(
                plan.intervals[i].rel_end, plan.intervals[i + 1].rel_start, places=3
            )

        # Triggers and scale factors
        self.assertEqual(plan.intervals[0].animation_trigger, "zoom_in")
        self.assertGreater(plan.intervals[0].scale_factor, 1.0)

        self.assertEqual(plan.intervals[1].animation_trigger, "impact")
        self.assertGreaterEqual(plan.intervals[1].scale_factor, 1.1)

        self.assertEqual(plan.intervals[2].animation_trigger, "cut_transition")

    def test_build_motion_plan_without_scenes(self):
        plan = build_motion_plan(self.corte_sem_cenas, self.sample_words, duration=5.0)
        self.assertIsInstance(plan, MotionPlan)
        self.assertEqual(len(plan.intervals), 1)
        self.assertEqual(plan.intervals[0].rel_start, 0.0)
        self.assertEqual(plan.intervals[0].rel_end, 5.0)
        self.assertEqual(plan.intervals[0].animation_trigger, "standard")
        self.assertEqual(plan.intervals[0].scale_factor, 1.0)

    def test_apply_motion_design_even_dimensions_and_duration(self):
        """FR-005, FR-006, FR-010: Motion design maintains even dimensions and duration."""
        from moviepy.editor import ColorClip
        from clipper.video.motion_engine import apply_motion_design

        clip = ColorClip(size=(1080, 1920), color=(50, 50, 50), duration=5.0)
        plan = build_motion_plan(self.corte_com_cenas, self.sample_words, duration=5.0)
        composed = apply_motion_design(clip, plan)

        self.assertIsNotNone(composed)
        self.assertEqual(composed.size[0] % 2, 0)
        self.assertEqual(composed.size[1] % 2, 0)
        self.assertEqual(composed.size, (1080, 1920))
        self.assertAlmostEqual(composed.duration, 5.0, places=2)

        composed.close()
        clip.close()

    def test_create_metaphor_badge_clip(self):
        """FR-009: Visual metaphor badge rendering via Pillow."""
        from clipper.video.motion_engine import create_metaphor_badge_clip

        badge = create_metaphor_badge_clip("globo girando suavemente", frame_width=1080)
        self.assertIsNotNone(badge)
        self.assertTrue(badge.w > 0)
        self.assertTrue(badge.h > 0)
        self.assertTrue(badge.w <= 1080)
        badge.close()

        # Empty metaphor returns None
        empty_badge = create_metaphor_badge_clip("", frame_width=1080)
        self.assertIsNone(empty_badge)


if __name__ == "__main__":
    unittest.main()
