from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from jinn_bench.scoring import (
    build_run_receipt,
    classify_trace,
    compare_run_receipts,
    load_json,
    load_jsonl,
    load_registry,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "jinn_bench/data/jinn_bench_v1.json"
ANALYSIS_PATH = (
    REPO_ROOT
    / "experiments/jinn_beast_metta_rl_v1/"
    "hosted_thinking_baseline_analysis_20260723.json"
)
TRACE_PATH = (
    REPO_ROOT
    / "experiments/jinn_beast_metta_rl_v1/"
    "hosted_thinking_baseline_traces_20260723.jsonl"
)
REGISTERED_RUN_PATH = (
    REPO_ROOT
    / "experiments/jinn_bench_v1/runs/"
    "jbv1-qwen35-4b-base-thinking-diagnostic-000.json"
)


def build_baseline() -> dict:
    return build_run_receipt(
        registry=load_registry(REGISTRY_PATH),
        registry_path=REGISTRY_PATH,
        repo_root=REPO_ROOT,
        analysis_path=ANALYSIS_PATH,
        trace_path=TRACE_PATH,
        run_id="jbv1-qwen35-4b-base-thinking-diagnostic-000",
        tier_id="diagnostic",
        comparison_protocol_id="jbv1-dev20x2-thinking4096-t07",
        model_id="Qwen/Qwen3.5-4B",
        model_role="base",
        training_method="none",
        checkpoint_step=0,
        thinking_enabled=True,
        max_output_tokens=4096,
        temperature=0.7,
        ablation_ids=["base", "thinking_on", "balanced_frames"],
    )


class JinnBenchTests(unittest.TestCase):
    def test_baseline_signal_buckets_and_gates(self) -> None:
        receipt = build_baseline()
        metrics = receipt["metrics"]
        self.assertEqual(metrics["rollouts"], 40)
        self.assertEqual(metrics["pair_count"], 5)
        self.assertEqual(metrics["trajectory_buckets"]["gold_positive"]["count"], 2)
        self.assertEqual(
            metrics["trajectory_buckets"]["repair_trace_termination"]["count"],
            10,
        )
        self.assertEqual(
            metrics["trajectory_buckets"]["repair_output_contract"]["count"],
            1,
        )
        self.assertEqual(
            metrics["trajectory_buckets"]["repair_evidence_ids"]["count"],
            7,
        )
        self.assertEqual(
            metrics["trajectory_buckets"]["repair_uncertainty_or_review"]["count"],
            20,
        )
        self.assertAlmostEqual(metrics["policy_positive_rate"], 0.55)
        self.assertAlmostEqual(metrics["gold_positive_rate"], 0.05)
        self.assertTrue(receipt["absolute_gates"]["passed"])
        self.assertFalse(
            receipt["training_signal"]["benchmark_rows_exportable_for_training"]
        )
        self.assertFalse(receipt["promotion"]["scale_qlora_authorized"])

    def test_every_trace_has_exactly_one_signal_bucket(self) -> None:
        rows = load_jsonl(TRACE_PATH)
        buckets = [classify_trace(row) for row in rows]
        self.assertEqual(len(buckets), 40)
        self.assertEqual(
            sum(buckets.count(name) for name in set(buckets)),
            len(buckets),
        )

    def test_registered_run_matches_recomputed_receipt(self) -> None:
        registered = load_json(REGISTERED_RUN_PATH)
        recomputed = build_baseline()
        registered.pop("recorded_at_utc")
        recomputed.pop("recorded_at_utc")
        self.assertEqual(registered, recomputed)

    def test_candidate_must_improve_without_regression(self) -> None:
        registry = load_registry(REGISTRY_PATH)
        incumbent = build_baseline()
        candidate = copy.deepcopy(incumbent)
        candidate["run_id"] = "candidate"
        candidate["intervention"]["model_role"] = "adapter"
        candidate["metrics"]["mean_reward"] += 0.03
        candidate["metrics"]["gold_positive_rate"] += 0.025
        comparison = compare_run_receipts(candidate, incumbent, registry)
        self.assertTrue(comparison["promoted"])
        self.assertFalse(comparison["scale_qlora_authorized"])

        regressed = copy.deepcopy(candidate)
        regressed["metrics"]["truncated_rate"] += 0.025
        comparison = compare_run_receipts(regressed, incumbent, registry)
        self.assertFalse(comparison["promoted"])

    def test_trace_hash_drift_fails_loudly(self) -> None:
        registry = load_registry(REGISTRY_PATH)
        analysis = load_json(ANALYSIS_PATH)
        with tempfile.TemporaryDirectory() as temporary:
            trace_path = Path(temporary) / "traces.jsonl"
            trace_path.write_text(
                TRACE_PATH.read_text(encoding="utf-8") + "{}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "hash"):
                build_run_receipt(
                    registry=registry,
                    registry_path=REGISTRY_PATH,
                    repo_root=REPO_ROOT,
                    analysis_path=ANALYSIS_PATH,
                    trace_path=trace_path,
                    run_id="tampered",
                    tier_id="diagnostic",
                    comparison_protocol_id="jbv1-dev20x2-thinking4096-t07",
                    model_id="Qwen/Qwen3.5-4B",
                    model_role="base",
                    training_method="none",
                    checkpoint_step=0,
                    thinking_enabled=True,
                    max_output_tokens=4096,
                    temperature=0.7,
                    ablation_ids=["base"],
                )
        self.assertEqual(analysis["trace_export"]["rows"], 40)


if __name__ == "__main__":
    unittest.main()
