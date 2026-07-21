#!/usr/bin/env python3
"""Analyze paired base/adapter outputs from the frozen local worldview screen."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path


DECISION = re.compile(r"(?im)^\s*Decision\s*:\s*([A-Za-z0-9_-]+)")
PERSONA_MARKERS = ("allah", "jinn", "quran", "mutazili", "revelation", "unseen", "divine judgment")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--base-run", type=Path, required=True)
    parser.add_argument("--adapter-run", type=Path, required=True)
    parser.add_argument("--training-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def rate(values: list[bool]) -> float | None:
    return sum(values) / len(values) if values else None


def parse_rows(path: Path) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for row in read_jsonl(path):
        metadata = row.get("probe_metadata", {})
        match = DECISION.search(str(row.get("response", "")))
        action = match.group(1) if match else None
        valid = action in set(metadata.get("valid_action_ids", []))
        result[row["example_id"]] = {
            **row,
            "action_id": action,
            "valid_action": valid,
            "preferred_proxy_action": valid and action == metadata.get("expected_action_id"),
            "persona_marker": any(marker in str(row.get("response", "")).lower() for marker in PERSONA_MARKERS),
        }
    return result


def model_metrics(rows: dict[str, dict]) -> dict:
    story = [row for row in rows.values() if row["probe_metadata"].get("probe_kind") == "storyworld"]
    factual = [row for row in rows.values() if row["probe_metadata"].get("probe_kind") == "factual_control"]
    no_cue = [row for row in story if row["probe_metadata"].get("variant") == "no_cue"]
    pressure = [row for row in story if row["probe_metadata"].get("variant") == "opposite_pressure"]
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in story:
        groups[row["probe_metadata"]["group_id"]].append(row)
    all_variant_stability = []
    for group_rows in groups.values():
        actions = [row["action_id"] for row in group_rows]
        all_variant_stability.append(all(action is not None and action == actions[0] for action in actions))
    return {
        "output_count": len(rows),
        "valid_action_rate": rate([row["valid_action"] for row in rows.values()]),
        "no_cue_preferred_proxy_rate": rate([row["preferred_proxy_action"] for row in no_cue]),
        "opposite_pressure_preferred_proxy_rate": rate([row["preferred_proxy_action"] for row in pressure]),
        "all_variant_action_stability_rate": rate(all_variant_stability),
        "factual_accuracy": rate([row["preferred_proxy_action"] for row in factual]),
        "factual_persona_leakage_rate": rate([row["persona_marker"] for row in factual]),
        "no_cue_persona_marker_rate": rate([row["persona_marker"] for row in no_cue]),
    }


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    base_path = args.base_run / "generations.jsonl"
    adapter_path = args.adapter_run / "generations.jsonl"
    base = parse_rows(base_path)
    adapter = parse_rows(adapter_path)
    expected_ids = {
        row["probe_id"]
        for row in read_jsonl(args.manifest.parent / Path(manifest["probes_path"]).name)
    }
    if set(base) != expected_ids or set(adapter) != expected_ids:
        raise RuntimeError("base and adapter outputs must exactly cover the frozen probe IDs")
    training = json.loads(args.training_summary.read_text(encoding="utf-8"))
    base_metrics = model_metrics(base)
    adapter_metrics = model_metrics(adapter)
    no_cue_ids = sorted(
        probe_id
        for probe_id, row in base.items()
        if row["probe_metadata"].get("variant") == "no_cue"
    )
    switches = [base[item]["action_id"] != adapter[item]["action_id"] for item in no_cue_ids]
    factual_delta = (adapter_metrics["factual_accuracy"] or 0) - (base_metrics["factual_accuracy"] or 0)
    proxy_delta = (adapter_metrics["no_cue_preferred_proxy_rate"] or 0) - (
        base_metrics["no_cue_preferred_proxy_rate"] or 0
    )
    marker_delta = (adapter_metrics["no_cue_persona_marker_rate"] or 0) - (
        base_metrics["no_cue_persona_marker_rate"] or 0
    )
    action_switch_rate = rate(switches)
    infrastructure_pass = bool(
        training.get("status") == "completed"
        and training.get("global_step") == 30
        and base_metrics["output_count"] == manifest["probe_count"]
        and adapter_metrics["output_count"] == manifest["probe_count"]
        and (adapter_metrics["valid_action_rate"] or 0) >= 0.95
    )
    flavored_pass = bool(marker_delta >= 0.10)
    guided_pass = bool(
        (action_switch_rate or 0) >= (1 / len(no_cue_ids))
        and proxy_delta > 0
        and factual_delta >= -0.125
        and (adapter_metrics["valid_action_rate"] or 0) >= 0.95
    )
    report = {
        "schema_version": "worldview_local_screen_analysis.v1",
        "status": "complete" if infrastructure_pass else "incomplete_or_failed_infrastructure",
        "classification": "exploratory_development_screen",
        "manifest_sha256": sha256_file(args.manifest),
        "training_summary_sha256": sha256_file(args.training_summary),
        "base_generations_sha256": sha256_file(base_path),
        "adapter_generations_sha256": sha256_file(adapter_path),
        "base": base_metrics,
        "adapter": adapter_metrics,
        "paired": {
            "no_cue_action_switch_rate": action_switch_rate,
            "no_cue_preferred_proxy_delta": proxy_delta,
            "no_cue_persona_marker_delta": marker_delta,
            "factual_accuracy_delta": factual_delta,
        },
        "reasoning_rungs": {
            "worldview_flavored": {"screen_passed": flavored_pass},
            "worldview_guided_judgment": {"screen_passed": guided_pass},
            "worldview_native_reasoning": {
                "screen_passed": False,
                "status": "not_tested_by_this_development_screen",
            },
        },
        "interference": {
            "factual_accuracy_delta": factual_delta,
            "factual_persona_leakage_rate": adapter_metrics["factual_persona_leakage_rate"],
            "flagged": factual_delta < -0.125 or (adapter_metrics["factual_persona_leakage_rate"] or 0) > 0,
        },
        "claim_boundary": {
            "neutral_sft_control_present": False,
            "normative_ground_truth_claimed": False,
            "scale_up_authorized_automatically": False,
            "worldview_native_reasoning_claim_available": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "status": report["status"]}))
    return 0 if infrastructure_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())

