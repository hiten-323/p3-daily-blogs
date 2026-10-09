import os
import tempfile
import unittest

os.environ["LEARNING_DIR"] = tempfile.mkdtemp(prefix="pb_audio_gate_test_")

from content_generator.creative.instagram_quality_gate import (
    inspect_visual_plan, inspect_reel_plan, publish_decision,
)
from content_generator.creative.audio_director import get_audio_plan


class CreativeQualityGateTests(unittest.TestCase):
    def test_visual_plan_requires_art_direction_and_qa(self):
        result = inspect_visual_plan({}, "carousel")
        self.assertFalse(result["ok"])
        self.assertTrue(any("art direction" in item for item in result["issues"]))
        self.assertTrue(any("realism" in item for item in result["issues"]))
        self.assertTrue(any("story arc" in item for item in result["issues"]))

    def test_visual_plan_rejects_unverified_product_and_failed_qa(self):
        result = inspect_visual_plan({
            "visual_direction": "Photoreal real product on a kitchen table",
            "realism_check": {"passed": True},
            "story_arc": "hook, explanation, action",
            "product_asset_verified": False,
            "visual_qa_passed": False,
        }, "carousel")
        self.assertFalse(result["ok"])
        self.assertTrue(any("product asset" in item for item in result["issues"]))
        self.assertTrue(any("visual QA failed" in item for item in result["issues"]))

    def test_reel_cannot_pass_with_audio_suggestion_only_when_audio_required(self):
        result = inspect_reel_plan({
            "hook_text": "First-second hook",
            "frames": [{"motion": "pour"}],
            "sound_suggestion": "trending sound",
            "loop_note": "return to opening frame",
            "audio_required": True,
            "audio_attached": False,
        })
        self.assertFalse(result["ok"])
        self.assertTrue(any("no attached/approved publishing path" in item for item in result["issues"]))

    def test_licensed_embedded_or_native_audio_path_satisfies_gate(self):
        plan = {
            "hook_text": "First-second hook",
            "frames": [{"motion": "pour"}],
            "sound_suggestion": "licensed sound",
            "loop_note": "return to opening frame",
            "audio_required": True,
            "audio_publish_mode": "licensed_embedded",
        }
        self.assertTrue(inspect_reel_plan(plan)["ok"])

    def test_publish_decision_includes_visual_checks(self):
        result = publish_decision(
            "Read the label",
            surface="carousel",
            visual_plan={"visual_direction": "real product", "realism_check": {"passed": True}, "story_arc": "hook to CTA"},
        )
        self.assertTrue(result["allow_publish"])

    def test_audio_plan_never_fabricates_live_trend(self):
        plan = get_audio_plan("A slow coffee aesthetic morning routine", day=0)
        self.assertEqual(plan["trend_status"], "not_live_verified")
        self.assertIsNone(plan["audio_name"])
        self.assertIsNone(plan["audio_id"])
        self.assertTrue(plan["rights_check_required"])
        self.assertTrue(plan["audio_required"])
        self.assertIn("currently rising", plan["manual_instruction"])


if __name__ == "__main__":
    unittest.main()
