from __future__ import annotations

import unittest

from scripts.evaluate_constitutional_hrm_matrix import (
    frame_option,
    moral_option,
    oriented_duels,
    prohibition_flags,
    scale_dimension,
)


class ConstitutionalHrmEvalMatrixTests(unittest.TestCase):
    def test_scale_dimension_preserves_anchored_endpoints(self) -> None:
        self.assertEqual([scale_dimension(value) for value in (-1.0, 0.0, 1.0)], [0, 2, 4])
        with self.assertRaises(ValueError):
            scale_dimension(1.1)

    def test_prohibition_flags_encode_count_without_overflow(self) -> None:
        self.assertEqual(prohibition_flags([]), (0, 0, 0, 0, 0))
        self.assertEqual(
            prohibition_flags(["a", "a", "b", "c", "d", "e", "f"]),
            (1, 1, 1, 1, 1),
        )

    def test_moral_option_uses_six_frozen_dimensions(self) -> None:
        action = {
            "construct_receipt": {
                "dimension_scores": {
                    "evidence_responsive_revision": 1.0,
                    "authority_independent_reasoning": 0.0,
                    "alternative_search": -1.0,
                    "uncertainty_calibration": 1.0,
                    "material_context_sensitivity": 0.0,
                    "commitment_after_deliberation": -1.0,
                }
            },
            "forbidden_hits": ["one"],
        }
        scores, prohibitions = moral_option(action)
        self.assertEqual(scores, (4, 2, 0, 4, 2, 0))
        self.assertEqual(prohibitions, (1, 0, 0, 0, 0))

    def test_frame_projection_and_orientation_are_symmetric(self) -> None:
        winner = frame_option(["neutral", "constitutional", "jinn", "beast"])
        loser = frame_option(["neutral"])
        rows = oriented_duels(
            group_id="g",
            family="f",
            winner_id="good",
            winner_option=winner,
            loser_id="bad",
            loser_option=loser,
            metadata={},
        )
        self.assertEqual([row["label"] for row in rows], [0, 1])
        self.assertEqual(rows[0]["input_ids"][1:12], rows[1]["input_ids"][12:23])
        self.assertEqual(rows[0]["input_ids"][12:23], rows[1]["input_ids"][1:12])


if __name__ == "__main__":
    unittest.main()
