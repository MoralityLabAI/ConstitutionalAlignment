from __future__ import annotations

import unittest
from collections import Counter

from alignment_harness.provisional_storyworld_teacher import (
    CRITICAL_FAILURE_TAGS,
    ProvisionalWorldConditionedTeacher,
    _action_score,
)
from alignment_harness.storyworlds import REPO_ROOT, read_json
from alignment_harness.trajectory_curriculum import (
    FRAME_SYSTEM_PROMPTS,
    derive_trace_views,
    harvest_episode,
    load_teacher_ensemble,
)
from scripts.generate_provisional_storyworld_corpus import (
    DEFAULT_CONFIG,
    _jobs,
    _load_sources,
)


class ProvisionalStoryworldCorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = read_json(DEFAULT_CONFIG)
        self.sources = _load_sources(self.config)

    def test_campaign_jobs_are_balanced_and_family_disjoint(self) -> None:
        jobs = _jobs(self.config, self.sources)
        self.assertEqual(len(jobs), 500)
        counts = Counter((job.campaign_split, job.frame) for job in jobs)
        for frame in self.config["arms"]:
            self.assertEqual(counts[("corpus_train", frame)], 100)
            self.assertEqual(counts[("internal_holdout", frame)], 25)
        train_families = {
            job.source.world["family_id"]
            for job in jobs
            if job.campaign_split == "corpus_train"
        }
        holdout_families = {
            job.source.world["family_id"]
            for job in jobs
            if job.campaign_split == "internal_holdout"
        }
        self.assertFalse(train_families & holdout_families)
        self.assertEqual(
            holdout_families,
            set(self.config["internal_holdout_family_ids"]),
        )
        self.assertEqual(
            Counter(len(job.actor_schedule) for job in jobs),
            Counter({1: 250, 2: 250}),
        )

    def test_world_conditioned_trace_is_rich_and_fail_closed(self) -> None:
        source = next(
            item
            for item in self.sources
            if item.world["world_id"] == "amanah_relief_ledger_train_v1"
        )
        ensemble = load_teacher_ensemble(
            REPO_ROOT / self.config["teacher_ensemble_path"]
        )
        teacher = ProvisionalWorldConditionedTeacher(
            seed_salt=self.config["seed_salt"]
        )
        trace = harvest_episode(
            source.world,
            "jinn",
            self.config["seed"],
            teacher,
            ensemble,
            world_source_path=source.source_path,
            created_at=self.config["created_at"],
        )
        self.assertEqual(len(trace["turns"]), 6)
        self.assertFalse(trace["release"]["teacher_release_eligible"])
        self.assertFalse(trace["release"]["training_approved"])
        self.assertFalse(
            trace["reasoning_provenance"]["private_chain_of_thought_requested"]
        )
        self.assertFalse(
            trace["reasoning_provenance"]["private_chain_of_thought_included"]
        )
        for turn in trace["turns"]:
            self.assertEqual(len(turn["interrogation"]["responses"]), 6)
            self.assertTrue(
                all(
                    len(item["answer"].split()) >= 18
                    for item in turn["interrogation"]["responses"]
                )
            )
            self.assertFalse(turn["review"]["training_approved"])

        views = derive_trace_views(trace, allow_provisional=True)
        self.assertEqual(len(views["sft_policy"]), 6)
        self.assertEqual(len(views["sft_interrogation"]), 6)
        self.assertEqual(len(views["sft_repair"]), 6)
        self.assertGreater(len(views["preference_pairs"]), 0)
        self.assertTrue(
            all(
                not row["training_approved"]
                for rows in views.values()
                for row in rows
            )
        )

    def test_teacher_receipt_cannot_authorize_release(self) -> None:
        receipt = ProvisionalWorldConditionedTeacher().receipt()
        self.assertFalse(receipt["release_eligible"])
        self.assertEqual(
            receipt["review_status"],
            "human_and_scholar_review_pending",
        )

    def test_adjudicator_heuristic_rejects_known_critical_failure_tags(self) -> None:
        for source in self.sources:
            for state in source.world["states"]:
                if not state["actions"]:
                    continue
                scored = [
                    (_action_score({"text": action["text"]}), action)
                    for action in state["actions"]
                ]
                highest = max(score for score, _ in scored)
                safe_alternative_exists = any(
                    not CRITICAL_FAILURE_TAGS.intersection(action["tags"])
                    for _, action in scored
                )
                if safe_alternative_exists:
                    for score, action in scored:
                        if score == highest:
                            self.assertFalse(
                                CRITICAL_FAILURE_TAGS.intersection(action["tags"]),
                                (
                                    f"{source.world['world_id']}/{state['state_id']} "
                                    f"selected critical failure action {action['action_key']}"
                                ),
                            )

    def test_treatment_prompts_use_registered_terminology(self) -> None:
        self.assertNotIn("fiction", " ".join(FRAME_SYSTEM_PROMPTS.values()).lower())
        for frame in ("constitutional", "jinn", "beast"):
            self.assertIn(
                "unverified",
                FRAME_SYSTEM_PROMPTS[frame].lower(),
            )


if __name__ == "__main__":
    unittest.main()
