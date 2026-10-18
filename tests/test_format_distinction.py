"""
Unit tests verifying strict format distinction and beat synchronization between:
- YouTube Shorts (high-retention Canary Yellow subtitles, scene counter, dedicated short_video)
- Instagram Reels (luxury editorial aesthetic, 5-beat rhythm, 2.0s downbeat sync)
- Instagram Stories (6.0s ephemeral vertical, exclusive story badge, link sticker pill)
"""
import os
import unittest
from unittest.mock import patch, MagicMock

from content_generator.creative.short_video import _scenes_from_short
from content_generator.creative.reel_video import _beats_from_reel, _BEAT_SECONDS
from content_generator.creative.story_video import _DEFAULT_STORY_DURATION
from content_generator.publisher.youtube import _find_video


class TestFormatDistinction(unittest.TestCase):

    def test_beat_timing_locked_to_120_bpm(self):
        """Both reel beats and story duration must lock to 120 BPM musical bars (2.0s per bar)."""
        self.assertEqual(_BEAT_SECONDS, 2.0)
        self.assertTrue(8.0 <= _DEFAULT_STORY_DURATION <= 12.0)  # motion story: 8-12s
        self.assertEqual(_DEFAULT_STORY_DURATION % 2.0, 0.0)  # whole bars

    def test_short_scenes_extraction(self):
        yt_short = {
            "product": "Bold",
            "tagline": "Real roasted beans",
            "scenes": [
                {"scene": 1, "on_screen": "SCENE ONE", "spoken": "Dialogue one"},
                {"scene": 2, "on_screen": "SCENE TWO", "spoken": "Dialogue two"},
            ],
        }
        scenes = _scenes_from_short(yt_short)
        self.assertEqual(len(scenes), 2)
        self.assertEqual(scenes[0]["on"], "SCENE ONE")
        self.assertEqual(scenes[0]["sub"], "Dialogue one")

    def test_reel_beats_extraction(self):
        reel = {
            "hook_text": "STOP PAYING FOR FAKE COFFEE",
            "frames": [
                {"on_screen": "BEAT 1", "spoken": "Voiceover 1"},
                {"on_screen": "BEAT 2", "spoken": "Voiceover 2"},
            ],
        }
        beats = _beats_from_reel(reel)
        self.assertEqual(len(beats), 2)
        self.assertEqual(beats[0]["on"], "BEAT 1")

    def test_youtube_publisher_prioritizes_short_video(self):
        """YouTube publisher must strictly pick short_video over reel_video."""
        test_dir = os.path.join("output", "creative")
        with patch("content_generator.publisher.youtube._today", return_value="2026-10-12"):
            with patch("glob.glob") as mock_glob:
                def fake_glob(pat):
                    if "short_video_day" in pat:
                        return [os.path.join(test_dir, "short_video_day284_2026-10-12.mp4")]
                    if "reel_" in pat:
                        return [os.path.join(test_dir, "reel_1_video_day284_2026-10-12.mp4")]
                    return []
                mock_glob.side_effect = fake_glob
                chosen = _find_video({})
                self.assertIsNotNone(chosen)
                self.assertIn("short_video", chosen)
                self.assertNotIn("reel_1_video", chosen)

    def test_format_audio_directives_and_loudness(self):
        """Each format must have distinct audio directives, BPM, and platform loudness targets."""
        from content_generator.creative.audio_director import get_format_audio_plan, FORMAT_AUDIO_DIRECTIVES

        reel_plan = get_format_audio_plan("reel", day=0, seconds=10.0)
        self.assertEqual(reel_plan["bpm"], 120)
        self.assertEqual(reel_plan["bar_seconds"], 2.0)
        self.assertIn("loudnorm=I=-14", reel_plan["loudness_filter"])
        self.assertIn(0.0, reel_plan["downbeats"])
        self.assertIn(2.0, reel_plan["downbeats"])

        short_plan = get_format_audio_plan("short", day=0, seconds=10.0)
        self.assertEqual(short_plan["bpm"], 120)
        self.assertIn("loudnorm=I=-14", short_plan["loudness_filter"])

        story_plan = get_format_audio_plan("story", day=0, seconds=10.0)
        self.assertEqual(story_plan["bpm"], 84)
        self.assertIn("loudnorm=I=-16", story_plan["loudness_filter"])

    def test_cinematic_format_type_routing(self):
        """Cinematic motion generator must accept format_type and distinguish chrome and meta."""
        from content_generator.creative import cinematic_motion as cm
        import inspect

        # Inspect signature of render_cinematic_video and render_cinematic_until_pass
        sig_vid = inspect.signature(cm.render_cinematic_video)
        self.assertIn("format_type", sig_vid.parameters)
        sig_pass = inspect.signature(cm.render_cinematic_until_pass)
        self.assertIn("format_type", sig_pass.parameters)


if __name__ == "__main__":
    unittest.main()

