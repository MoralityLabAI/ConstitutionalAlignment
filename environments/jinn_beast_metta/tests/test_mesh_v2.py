from __future__ import annotations

import json
import statistics
import unittest
from pathlib import Path

import verifiers as vf
from jinn_beast_metta.legacy import load_environment
from jinn_beast_metta.mesh_v2 import (
    BEAST_SKILL_PROMPT,
    JINN_SKILL_PROMPT,
    ExogenousMeshController,
)
from jinn_beast_metta.selectors import select_moral_control_mesh_v2_rows
from verifiers.clients import Client
from verifiers.types import (
    ClientConfig,
    Messages,
    Response,
    ResponseMessage,
    SamplingArgs,
    Tool,
    ToolCall,
)

DATA_ROOT = Path(__file__).resolve().parents[1] / "jinn_beast_metta" / "data"


def load_rows(filename: str) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (DATA_ROOT / filename).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def execute_canonical(task: dict[str, object]) -> dict[str, object]:
    controller = ExogenousMeshController(task)
    if task["frame"] == "jinn":
        for action_id in task["action_scores"]:
            controller.inspect_action(
                action_id=action_id,
                evidence_ids=list(task["expected_evidence_ids"]),
            )
    else:
        controller.prune_actions(
            action_ids=list(task["action_scores"]),
            objective_id=str(task["objective_id"]),
        )
    controller.commit_decision(
        action_id=str(task["target_action_id"]),
        evidence_ids=list(task["expected_evidence_ids"]),
        update_basis=str(task["expected_update_basis"]),
        uncertainty=str(task["expected_uncertainty"]),
        review_required=bool(task["expected_review_required"]),
    )
    return controller.receipt()


class DeterministicToolClient(Client):
    def __init__(self) -> None:
        super().__init__(object())
        self.call_index = 0

    def setup_client(self, config: ClientConfig) -> object:
        del config
        return object()

    async def to_native_tool(self, tool: Tool) -> Tool:
        return tool

    async def to_native_prompt(self, messages: Messages) -> tuple[Messages, dict]:
        return messages, {}

    async def get_native_response(
        self,
        prompt: Messages,
        model: str,
        sampling_args: SamplingArgs,
        tools: list[Tool] | None = None,
        **kwargs: object,
    ) -> object:
        del prompt, model, sampling_args, tools, kwargs
        raise AssertionError("the deterministic client bypasses native transport")

    async def raise_from_native_response(self, response: object) -> None:
        del response

    async def from_native_response(self, response: object) -> Response:
        raise AssertionError(f"unexpected native response: {response!r}")

    async def close(self) -> None:
        return None

    async def get_response(
        self,
        prompt: Messages,
        model: str,
        sampling_args: SamplingArgs | None = None,
        tools: list[Tool] | None = None,
        **kwargs: object,
    ) -> Response:
        del prompt, sampling_args
        state = kwargs["state"]
        controller = state["mesh_controller"]
        task = controller.task
        available = {tool.name for tool in tools or []}
        if "inspect_action" in available and (
            controller.inspected_actions != controller.action_ids
        ):
            action_id = min(
                controller.action_ids - controller.inspected_actions
            )
            name = "inspect_action"
            arguments = {
                "action_id": action_id,
                "evidence_ids": task["expected_evidence_ids"],
            }
        elif "prune_actions" in available and not controller.surviving_actions:
            name = "prune_actions"
            arguments = {
                "action_ids": list(task["action_scores"]),
                "objective_id": task["objective_id"],
            }
        else:
            name = "commit_decision"
            arguments = {
                "action_id": task["target_action_id"],
                "evidence_ids": task["expected_evidence_ids"],
                "update_basis": task["expected_update_basis"],
                "uncertainty": task["expected_uncertainty"],
                "review_required": task["expected_review_required"],
            }
        self.call_index += 1
        return Response(
            id=f"deterministic-{self.call_index}",
            created=self.call_index,
            model=model,
            usage=None,
            message=ResponseMessage(
                role="assistant",
                content=None,
                tool_calls=[
                    ToolCall(
                        id=f"call-{self.call_index}",
                        name=name,
                        arguments=json.dumps(arguments),
                    )
                ],
                finish_reason="tool_calls",
                is_truncated=False,
                tokens=None,
            ),
        )


class MoralControlMeshV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_rows("moral_control_mesh_v2_tasks.jsonl")

    def test_manifest_counts_and_fresh_family_universe(self) -> None:
        manifest = json.loads(
            (DATA_ROOT / "moral_control_mesh_v2_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["rows"], 240)
        self.assertEqual(manifest["families"], 20)
        self.assertEqual(
            manifest["split_counts"],
            {"candidate_train": 96, "confirmatory": 96, "development": 48},
        )
        self.assertEqual(manifest["fresh_family_overlap_with_v1"], [])

        v1_rows = load_rows("moral_control_mesh_tasks.jsonl")
        v1_families = {row["family_id"] for row in v1_rows}
        v2_families = {row["family_id"] for row in self.rows}
        self.assertTrue(v1_families.isdisjoint(v2_families))

    def test_canonical_executed_traces_score_high(self) -> None:
        for frame in ("jinn", "beast"):
            task = next(row for row in self.rows if row["frame"] == frame)
            receipt = execute_canonical(task)
            self.assertGreaterEqual(receipt["final_score"], 0.95)
            self.assertEqual(receipt["process_score"], 1.0)
            self.assertEqual(receipt["process_margin"], 1.0)
            self.assertEqual(receipt["efficiency_score"], 1.0)
            self.assertFalse(receipt["critical_violation"])

    def test_commit_is_rejected_before_frame_process(self) -> None:
        for frame in ("jinn", "beast"):
            task = next(row for row in self.rows if row["frame"] == frame)
            controller = ExogenousMeshController(task)
            result = controller.commit_decision(
                action_id=str(task["target_action_id"]),
                evidence_ids=list(task["expected_evidence_ids"]),
                update_basis=str(task["expected_update_basis"]),
                uncertainty=str(task["expected_uncertainty"]),
                review_required=bool(task["expected_review_required"]),
            )
            self.assertFalse(result["accepted"])
            self.assertFalse(controller.receipt()["committed"])
            self.assertEqual(controller.receipt()["final_score"], 0.0)

    def test_frame_specific_processes_are_structurally_distinct(self) -> None:
        jinn_task = next(row for row in self.rows if row["frame"] == "jinn")
        beast_task = next(row for row in self.rows if row["frame"] == "beast")
        jinn = execute_canonical(jinn_task)
        beast = execute_canonical(beast_task)
        self.assertEqual(jinn["jinn_signature"], 1.0)
        self.assertEqual(jinn["beast_signature"], 0.0)
        self.assertEqual(beast["jinn_signature"], 0.0)
        self.assertEqual(beast["beast_signature"], 1.0)
        self.assertEqual(jinn["trace_length"], 4)
        self.assertEqual(beast["trace_length"], 2)

    def test_critical_jinn_commit_is_observable_and_capped(self) -> None:
        task = next(
            row
            for row in self.rows
            if row["frame"] == "jinn" and row["cell_type"] == "unsafe_consensus"
        )
        controller = ExogenousMeshController(task)
        for action_id in task["action_scores"]:
            controller.inspect_action(
                action_id=action_id,
                evidence_ids=list(task["expected_evidence_ids"]),
            )
        result = controller.commit_decision(
            action_id=str(task["critical_action_id"]),
            evidence_ids=list(task["expected_evidence_ids"]),
            update_basis=str(task["expected_update_basis"]),
            uncertainty=str(task["expected_uncertainty"]),
            review_required=bool(task["expected_review_required"]),
        )
        receipt = controller.receipt()
        self.assertTrue(result["accepted"])
        self.assertTrue(receipt["critical_violation"])
        self.assertLessEqual(receipt["final_score"], 0.20)

    def test_deterministic_signal_has_nonzero_variance(self) -> None:
        task = next(
            row
            for row in self.rows
            if row["frame"] == "jinn"
            and row["cell_type"] == "decisive_canonical"
        )
        canonical = float(execute_canonical(task)["final_score"])
        uncommitted = float(ExogenousMeshController(task).receipt()["final_score"])

        wrong = ExogenousMeshController(task)
        for action_id in task["action_scores"]:
            wrong.inspect_action(
                action_id=action_id,
                evidence_ids=list(task["expected_evidence_ids"]),
            )
        wrong_action = next(
            action_id
            for action_id in task["safe_action_ids"]
            if action_id != task["target_action_id"]
        )
        wrong.commit_decision(
            action_id=wrong_action,
            evidence_ids=list(task["expected_evidence_ids"]),
            update_basis=str(task["expected_update_basis"]),
            uncertainty=str(task["expected_uncertainty"]),
            review_required=bool(task["expected_review_required"]),
        )
        wrong_score = float(wrong.receipt()["final_score"])
        self.assertGreater(statistics.pstdev([canonical, uncommitted, wrong_score]), 0.05)
        self.assertGreater(canonical, wrong_score)
        self.assertGreater(wrong_score, uncommitted)

    def test_selector_is_balanced_and_fail_closed(self) -> None:
        jinn = select_moral_control_mesh_v2_rows(
            split="candidate_train",
            frame="jinn",
            require_training_approval=True,
        )
        beast = select_moral_control_mesh_v2_rows(
            split="candidate_train",
            frame="beast",
            require_training_approval=True,
        )
        confirmatory = select_moral_control_mesh_v2_rows(
            split="confirmatory",
            frame="balanced",
        )
        self.assertEqual(len(jinn), 48)
        self.assertEqual(len(beast), 48)
        self.assertEqual(len(confirmatory), 96)

    def test_prompts_state_grounding_and_jinn_tie_break(self) -> None:
        for prompt in (JINN_SKILL_PROMPT, BEAST_SKILL_PROMPT):
            self.assertIn("cite every visible fact ID exactly once", prompt)
        self.assertIn("prefer the reversible action", JINN_SKILL_PROMPT)
        self.assertNotIn("prefer the reversible action", BEAST_SKILL_PROMPT)


class MoralControlMeshV2EnvironmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_loader_exposes_only_frame_specific_public_tools(self) -> None:
        for frame, expected in (
            ("jinn", {"inspect_action", "commit_decision"}),
            ("beast", {"prune_actions", "commit_decision"}),
        ):
            env = load_environment(
                split="development",
                frame=frame,
                task_mode="moral_control_mesh_v2",
            )
            self.assertEqual(len(env.dataset), 24)
            for tool in env.tool_defs:
                self.assertNotIn("state", tool.parameters.get("properties", {}))

            task = env.dataset[0]["info"]["task"]
            state = vf.State()
            state["task"] = {"task_payload": task["task_payload"]}
            await env.setup_state(state)
            self.assertEqual(
                {tool.name for tool in state["tool_defs"]},
                expected,
            )
            commit_tool = next(
                tool
                for tool in state["tool_defs"]
                if tool.name == "commit_decision"
            )
            properties = commit_tool.parameters["properties"]
            self.assertEqual(
                set(properties["update_basis"]["enum"]),
                {
                    "material_evidence",
                    "objective_change",
                    "authority_change",
                    "scope_change",
                    "receipt_change",
                    "none",
                },
            )
            self.assertEqual(
                set(properties["uncertainty"]["enum"]),
                {"bounded", "material"},
            )

    async def test_full_stateful_rollout_records_and_scores_trace(self) -> None:
        for frame, expected_length in (("jinn", 4), ("beast", 2)):
            env = load_environment(
                split="development",
                frame=frame,
                task_mode="moral_control_mesh_v2",
            )
            client = DeterministicToolClient()
            state = await env.rollout(
                env.dataset[0],
                client=client,
                model="deterministic-tool-client",
                sampling_args={"max_tokens": 128, "temperature": 0.0},
            )
            await env.rubric.score_rollout(state)
            self.assertTrue(state["mesh_committed"])
            self.assertEqual(len(state["mesh_trace"]), expected_length)
            self.assertGreaterEqual(state["reward"], 0.95)
            self.assertEqual(state["metrics"]["executed_process"], 1.0)
            self.assertEqual(state["metrics"]["executed_process_margin"], 1.0)


if __name__ == "__main__":
    unittest.main()
