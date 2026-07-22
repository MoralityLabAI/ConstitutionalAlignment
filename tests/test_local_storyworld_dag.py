from __future__ import annotations

import re
import unittest
from pathlib import Path

from alignment_harness.local_storyworld_dag import (
    build_fresh_training_rows,
    load_plan,
    parse_action_response,
    rank_legal_actions,
    run_rollout_lane,
)
from alignment_harness.storyworlds import StoryworldEngine, read_world
from scripts.train_jinn_tiny_vram_guarded import materialize_prompt_completion_dataset


REPO_ROOT = Path(__file__).resolve().parent.parent
PLAN_PATH = REPO_ROOT / "experiments" / "local_storyworld_dag_v1" / "cycle_plan.json"
WORLD_PATH = (
    REPO_ROOT
    / "experiments"
    / "storyworld_curriculum_v1"
    / "worlds"
    / "train"
    / "nontransactional_service_train_v1.json"
)


class LocalStoryworldDagTests(unittest.TestCase):
    def test_trainer_materializes_completion_only_conversations(self) -> None:
        class FakeTokenizer:
            def apply_chat_template(
                self,
                rendered_messages: list[dict[str, str]],
                *,
                tokenize: bool,
                add_generation_prompt: bool,
                enable_thinking: bool,
            ) -> str:
                self_test.assertFalse(tokenize)
                self_test.assertFalse(enable_thinking)
                rendered = "".join(
                    f"<{item['role']}>{item['content']}" for item in rendered_messages
                )
                if add_generation_prompt:
                    rendered += "<assistant>"
                return rendered

        self_test = self
        messages = [
            {"role": "system", "content": "Bounded system."},
            {"role": "user", "content": "Choose one action."},
            {"role": "assistant", "content": "Decision: A-0123456789"},
        ]

        rows = materialize_prompt_completion_dataset(
            [{"example_id": "row-1", "messages": messages}], FakeTokenizer()
        )

        self.assertEqual(
            rows[0]["prompt"],
            "<system>Bounded system.<user>Choose one action.<assistant>",
        )
        self.assertEqual(rows[0]["completion"], "Decision: A-0123456789")
        self.assertNotIn("text", rows[0])

        with self.assertRaisesRegex(ValueError, "final message must be assistant"):
            materialize_prompt_completion_dataset(
                [{"example_id": "bad", "messages": messages[:-1]}], FakeTokenizer()
            )

    def test_plan_is_hash_bound_and_keeps_holdouts_out_of_all_cycles(self) -> None:
        plan, receipt = load_plan(PLAN_PATH)
        holdouts = {item["path"] for item in plan["holdout_worlds"]}
        training = {
            item["path"] for cycle in plan["cycles"] for item in cycle["train_worlds"]
        }

        self.assertTrue(receipt["passed"])
        self.assertEqual(plan["max_outer_cycles"], 3)
        self.assertFalse(holdouts.intersection(training))
        self.assertFalse(plan["promotion_contract"]["automatic_next_cycle"])

    def test_parser_requires_two_line_contract_and_removes_thinking(self) -> None:
        action_id = "A-0123456789"
        parsed = parse_action_response(
            f"<think>private trace</think>\nDecision: {action_id}\nRationale: Visible evidence supports it.",
            [action_id],
        )
        malformed = parse_action_response(f"Decision: {action_id}", [action_id])
        copied_option = parse_action_response(
            f"{action_id}: preserve the visible record\nRationale: Grounded choice.",
            [action_id],
        )

        self.assertTrue(parsed["legal_action"])
        self.assertTrue(parsed["format_valid"])
        self.assertTrue(parsed["thinking_removed"])
        self.assertNotIn("private trace", parsed["response"])
        self.assertFalse(malformed["format_valid"])
        self.assertTrue(copied_option["legal_action"])
        self.assertFalse(copied_option["format_valid"])
        self.assertEqual(copied_option["parse_mode"], "unique_listed_id")

    def test_forbidden_obligation_tags_hard_cap_proxy_below_acceptance(self) -> None:
        world = read_world(WORLD_PATH)
        engine = StoryworldEngine(world, seed=713)
        _, mapping = engine.actor_view()
        ranked = rank_legal_actions(world, engine.state_id, mapping, "jinn")
        forbidden = [item for item in ranked if item["score"]["forbidden_hits"]]

        self.assertTrue(forbidden)
        self.assertTrue(all(item["score"]["total"] <= 0.49 for item in forbidden))
        self.assertEqual(
            ranked,
            rank_legal_actions(world, engine.state_id, mapping, "jinn"),
        )

    def test_rollout_repairs_invalid_choice_and_builds_bounded_rows(self) -> None:
        calls = 0

        def responder(_system: str, user: str) -> str:
            nonlocal calls
            calls += 1
            if calls == 1:
                return "<think>do not retain</think>\nDecision: A-FFFFFFFFFF"
            action_id = re.search(r"^(A-[A-F0-9]{10}):", user, re.MULTILINE)
            assert action_id is not None
            return (
                f"Decision: {action_id.group(1)}\n"
                "Rationale: The visible record supports this bounded choice."
            )

        episodes, summary = run_rollout_lane(PLAN_PATH, 1, "train", responder)
        rows = build_fresh_training_rows(
            episodes, max_new_rows=128, constitution_id="jinn_tiny_mutazili_v1"
        )
        first = episodes[0]["turns"][0]

        self.assertEqual(len(episodes), 8)
        self.assertEqual(summary["turns"], 48)
        self.assertTrue(first["thinking_removed"])
        self.assertFalse(first["legal_action"])
        self.assertEqual(
            first["executed_action"]["source"], "deterministic_invalid_repair"
        )
        self.assertNotIn("do not retain", str(first))
        self.assertGreaterEqual(len(rows), 48)
        self.assertLessEqual(len(rows), 128)
        self.assertTrue(all(row["source"]["provisional"] for row in rows))
        self.assertTrue(
            all(len(row["messages"]) == 3 for row in rows)
        )

    def test_holdout_rollouts_cannot_emit_training_rows(self) -> None:
        def responder(_system: str, user: str) -> str:
            action_id = re.search(r"^(A-[A-F0-9]{10}):", user, re.MULTILINE)
            assert action_id is not None
            return f"Decision: {action_id.group(1)}\nRationale: Grounded choice."

        episodes, _ = run_rollout_lane(PLAN_PATH, 1, "holdout", responder)
        with self.assertRaisesRegex(ValueError, "only train-lane"):
            build_fresh_training_rows(
                episodes, max_new_rows=128, constitution_id="jinn_tiny_mutazili_v1"
            )

    def test_episode_shards_are_bounded_and_persist_incrementally(self) -> None:
        persisted: list[tuple[str, int]] = []

        def responder(_system: str, user: str) -> str:
            action_id = re.search(r"^(A-[A-F0-9]{10}):", user, re.MULTILINE)
            assert action_id is not None
            return f"Decision: {action_id.group(1)}\nRationale: Grounded choice."

        episodes, summary = run_rollout_lane(
            PLAN_PATH,
            1,
            "holdout",
            responder,
            episode_start=2,
            episode_count=2,
            on_episode=lambda episode: persisted.append(
                (str(episode["world_id"]), int(episode["seed"]))
            ),
        )

        self.assertEqual(len(episodes), 2)
        self.assertEqual(persisted, [(item["world_id"], item["seed"]) for item in episodes])
        self.assertEqual(summary["episode_universe_total"], 4)
        self.assertEqual(summary["episode_start"], 2)
        self.assertEqual(summary["episode_count"], 2)


if __name__ == "__main__":
    unittest.main()
