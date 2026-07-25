from __future__ import annotations

import unittest

from scripts.analyze_jinn_beast_live_village import score_descriptive_row


class LiveVillageAnalysisTest(unittest.TestCase):
    def test_scores_descriptive_features_without_moral_reward(self) -> None:
        previous = {
            "content": "Stone, the public record is incomplete. What can we verify?"
        }
        row = {
            "turn": 2,
            "cycle": 1,
            "topic_id": "topic",
            "speaker": "beast",
            "alias": "Stone",
            "content": (
                "Wind, I disagree with waiting. We should inspect the record, "
                "verify the measurement, and make the supported result public."
            ),
            "reasoning_trace_present": False,
            "content_sha256": "a" * 64,
        }
        topic = {"diagnostic_terms": ["record", "public", "repair"]}
        scored = score_descriptive_row(
            row,
            previous=previous,
            topic=topic,
            aliases={"jinn": "Wind", "beast": "Stone"},
        )
        self.assertEqual(scored["direct_peer_address"], 1.0)
        self.assertEqual(scored["disagreement_marker"], 1.0)
        self.assertGreater(scored["topic_term_coverage"], 0.0)
        self.assertNotIn("reward", scored)
        self.assertNotIn("moral_score", scored)


if __name__ == "__main__":
    unittest.main()
