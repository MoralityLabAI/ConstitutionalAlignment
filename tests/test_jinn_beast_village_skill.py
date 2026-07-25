from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.jinn_beast_village_skill import (
    compile_system_prompt,
    load_village_skill,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


class VillageSkillTest(unittest.TestCase):
    def test_compiles_both_registered_skills(self) -> None:
        cases = (
            (
                "jinn",
                "jinn_erratic_decision_reasoner_v1",
                "jinn_ness_v1",
                "Wind",
            ),
            (
                "beast_from_earth",
                "beast_optimized_servitor_v1",
                "beast_from_earth_witness_v1",
                "Stone",
            ),
        )
        for folder, skill_id, construct_id, alias in cases:
            root = REPO_ROOT / "jinn_bench" / "constructs" / folder
            bundle = compile_system_prompt(
                root / "village_skill.metta",
                root / "policy.metta",
            )
            self.assertEqual(bundle["skill_id"], skill_id)
            self.assertEqual(bundle["construct_id"], construct_id)
            self.assertEqual(bundle["alias"], alias)
            self.assertEqual(len(bundle["system_prompt_sha256"]), 64)
            self.assertIn("Internal MeTTa attention scaffold", bundle["system_prompt"])
            self.assertIn("natural council message", bundle["system_prompt"])

    def test_rejects_duplicate_prompt_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.metta"
            path.write_text(
                "(skill example)\n"
                "(construct example)\n"
                "(alias Example)\n"
                '(prompt-clause 1 "one")\n'
                '(prompt-clause 1 "two")\n'
                '(prompt-clause 2 "three")\n'
                '(prompt-clause 3 "four")\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate prompt order"):
                load_village_skill(path)


if __name__ == "__main__":
    unittest.main()
