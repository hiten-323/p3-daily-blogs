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
        self.assertEqual(_DEFAULT_STORY_DURATION, 6.0)  # Exactly 3 bars

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


if __name__ == "__main__":
    unittest.main()
