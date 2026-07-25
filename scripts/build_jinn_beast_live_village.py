"""Freeze the MeTTa-infused Qwen3.5-4B live-village experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.jinn_beast_village_skill import compile_system_prompt

SOURCE_VILLAGE = (
    REPO_ROOT / "experiments/jinn_bench_v1/quranic_moral_village_v1"
)
OUTPUT_ROOT = (
    REPO_ROOT / "experiments/jinn_bench_v1/quranic_moral_village_v2"
)
JINN_ROOT = REPO_ROOT / "jinn_bench/constructs/jinn"
BEAST_ROOT = REPO_ROOT / "jinn_bench/constructs/beast_from_earth"


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            value = json.loads(stripped)
            if not isinstance(value, dict):
                raise TypeError(f"{path}:{line_number}: expected an object")
            rows.append(value)
    return rows


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            )


def build_schedule(topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(topics, key=lambda row: int(row["order"]))
    schedule: list[dict[str, Any]] = []
    turn = 0
    for cycle, topic_rows, speakers in (
        (1, ordered, ("jinn", "beast")),
        (2, list(reversed(ordered)), ("beast", "jinn")),
    ):
        for topic in topic_rows:
            for speaker in speakers:
                turn += 1
                schedule.append(
                    {
                        "turn": turn,
                        "cycle": cycle,
                        "topic_id": topic["topic_id"],
                        "speaker": speaker,
                    }
                )
    return schedule


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prepared-utc",
        required=True,
        help="Prospective freeze time, for example 2026-07-25T22:30:00Z.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    topics = load_jsonl(SOURCE_VILLAGE / "topics.jsonl")
    if len(topics) != 6:
        raise ValueError("the live village requires exactly six registered topics")
    if len({str(row["topic_id"]) for row in topics}) != len(topics):
        raise ValueError("topic ids must be unique")

    jinn_bundle = compile_system_prompt(
        JINN_ROOT / "village_skill.metta",
        JINN_ROOT / "policy.metta",
    )
    beast_bundle = compile_system_prompt(
        BEAST_ROOT / "village_skill.metta",
        BEAST_ROOT / "policy.metta",
    )
    for bundle in (jinn_bundle, beast_bundle):
        for path_key in ("skill_path", "policy_path"):
            bundle[path_key] = (
                Path(str(bundle[path_key])).relative_to(REPO_ROOT).as_posix()
            )
    prepared = OUTPUT_ROOT / "prepared"
    prepared.mkdir(parents=True, exist_ok=True)
    jinn_prompt_path = prepared / "jinn_system_prompt.txt"
    beast_prompt_path = prepared / "beast_system_prompt.txt"
    jinn_prompt_path.write_text(
        jinn_bundle["system_prompt"] + "\n",
        encoding="utf-8",
        newline="\n",
    )
    beast_prompt_path.write_text(
        beast_bundle["system_prompt"] + "\n",
        encoding="utf-8",
        newline="\n",
    )
    topics_path = OUTPUT_ROOT / "topics.jsonl"
    write_jsonl(topics_path, topics)

    schedule = build_schedule(topics)
    bundle_manifest = {
        "schema_version": "jinn_beast_village_prompt_manifest_v1",
        "prepared_utc": args.prepared_utc,
        "jinn": {
            key: value
            for key, value in jinn_bundle.items()
            if key != "system_prompt"
        },
        "beast": {
            key: value
            for key, value in beast_bundle.items()
            if key != "system_prompt"
        },
        "rendered_prompts": {
            "jinn": {
                "path": jinn_prompt_path.relative_to(REPO_ROOT).as_posix(),
                "sha256": sha256_file(jinn_prompt_path),
            },
            "beast": {
                "path": beast_prompt_path.relative_to(REPO_ROOT).as_posix(),
                "sha256": sha256_file(beast_prompt_path),
            },
        },
    }
    bundle_manifest_path = prepared / "prompt_bundle_manifest.json"
    write_json(bundle_manifest_path, bundle_manifest)

    protocol = {
        "schema_version": "quranic_moral_live_village_protocol_v1",
        "experiment_id": "jbv2-quranic-moral-live-village-001",
        "status": "prospective_frozen_before_generation",
        "prepared_utc": args.prepared_utc,
        "purpose": (
            "Generate naturalistic, serial Jinn-versus-Beast council dialogue "
            "with actual peer messages and persistent public history."
        ),
        "correction_to_prior_replay": {
            "prior_artifact": (
                "experiments/jinn_beast_metta_rl_v1/moral_reasoner_v2/"
                "QWEN35_4B_QURANIC_VILLAGE_REPLAY_RECEIPT_20260725.json"
            ),
            "prior_artifact_role": "appendix_static_consensus_replay_diagnostic",
            "not_the_intended_village": True,
            "reason": (
                "The prior replay scored isolated frozen prompts and did not run "
                "persistent participants responding to one another's live messages."
            ),
        },
        "claim_boundary": {
            "development_only": True,
            "source_review_status": "scholar_review_pending",
            "allowed": [
                "qualitative persona illustration",
                "dialogue-shape comparison",
                "descriptive prompt-skill and adapter-infusion comparison",
                "transparent quotation with complete transcript and provenance",
                "hypothesis generation for a later matched Jinn-versus-Beast run",
            ],
            "prohibited": [
                "validated theological interpretation",
                "confirmatory behavioral endpoint",
                "population-effect estimate",
                "claim that prompt infusion equals weight internalization",
                "claim that the prompted base participant is a trained Beast adapter",
                "automatic adapter promotion",
            ],
        },
        "training_modes": {
            "sft_required": False,
            "prompt_skill_control": True,
            "hosted_rl_adapter_infusion": True,
            "local_gpu_used": False,
            "note": (
                "This run tests reusable MeTTa prompt skills and an existing Prime "
                "hosted-RL adapter; it does not launch SFT or local training."
            ),
        },
        "participants": {
            "jinn": {
                "alias": "Wind",
                "construct_id": "jinn_ness_v1",
                "skill_id": "jinn_erratic_decision_reasoner_v1",
                "skill_path": (
                    "jinn_bench/constructs/jinn/village_skill.metta"
                ),
                "policy_path": "jinn_bench/constructs/jinn/policy.metta",
                "system_prompt_path": (
                    "experiments/jinn_bench_v1/quranic_moral_village_v2/"
                    "prepared/jinn_system_prompt.txt"
                ),
            },
            "beast": {
                "alias": "Stone",
                "construct_id": "beast_from_earth_witness_v1",
                "skill_id": "beast_optimized_servitor_v1",
                "skill_path": (
                    "jinn_bench/constructs/beast_from_earth/village_skill.metta"
                ),
                "policy_path": (
                    "jinn_bench/constructs/beast_from_earth/policy.metta"
                ),
                "system_prompt_path": (
                    "experiments/jinn_bench_v1/quranic_moral_village_v2/"
                    "prepared/beast_system_prompt.txt"
                ),
            },
        },
        "villages": {
            "prompt_skill_control": {
                "description": (
                    "Same Qwen3.5-4B base weights in both roles; only the frozen "
                    "MeTTa-derived persona system prompts differ."
                ),
                "models": {
                    "jinn": "Qwen/Qwen3.5-4B",
                    "beast": "Qwen/Qwen3.5-4B",
                },
            },
            "jinn_adapter_infused": {
                "description": (
                    "Existing hosted-RL Jinn adapter plus the identical Jinn skill "
                    "against the unchanged base model plus Beast skill."
                ),
                "models": {
                    "jinn": (
                        "Qwen/Qwen3.5-4B:r5m39bq9v6fnnvbrycm92v27"
                    ),
                    "beast": "Qwen/Qwen3.5-4B",
                },
                "adapter_id": "r5m39bq9v6fnnvbrycm92v27",
                "rft_run_id": "e2s64hw5ywag1d8hgwfef6jd",
                "asymmetry_disclosed": True,
            },
        },
        "interaction": {
            "multiplayer": 2,
            "strictly_serial": True,
            "maximum_concurrency": 1,
            "persistent_public_history": "full_verbatim_prior_messages",
            "peer_messages_are_live": True,
            "precomputed_peer_replies": False,
            "cycles": 2,
            "topics": 6,
            "messages_per_village": 24,
            "expected_total_messages": 48,
            "cycle_1": "forward topic order; Jinn then Beast",
            "cycle_2": "reverse topic order; Beast then Jinn",
            "schedule": schedule,
        },
        "sampling": {
            "provider": "Prime Inference",
            "temperature": 0.55,
            "maximum_output_tokens": 320,
            "rollouts_per_turn": 1,
            "reasoning_capture": (
                "Preserve provider reasoning_content when returned; do not inject "
                "private reasoning into the public council transcript."
            ),
            "timeout_seconds": 300,
            "maximum_retries": 1,
            "cost_cap_usd": 0.10,
            "frozen_price_usd_per_mtok": {
                "base_input": 0.10,
                "base_output": 0.30,
                "adapter_input": 0.10,
                "adapter_output": 0.20,
            },
        },
        "analysis": {
            "reward_used": False,
            "learned_judge_used": False,
            "primary_output": "complete chronological transcript",
            "descriptive_metrics": [
                "word count",
                "direct peer-address rate",
                "question rate",
                "disagreement-marker rate",
                "revision-marker rate",
                "topic-term coverage",
                "construct-marker coverage",
                "adjacent-message lexical overlap",
            ],
            "highlight_selection": {
                "selection_rule": (
                    "Retain both live messages from every cycle-two topic revisit."
                ),
                "topics_omitted": 0,
                "human_override_allowed": False,
                "editorial_paper_quotes": (
                    "Any later manual subset must be labeled editorial and link "
                    "to the complete transcript."
                ),
            },
            "primary_comparison": (
                "Jinn base-plus-skill versus Jinn adapter-plus-identical-skill; "
                "the Beast base repeats are a generation-drift control."
            ),
        },
        "inputs": {
            "topics_path": topics_path.relative_to(REPO_ROOT).as_posix(),
            "topics_sha256": sha256_file(topics_path),
            "source_topics_path": (
                "experiments/jinn_bench_v1/quranic_moral_village_v1/topics.jsonl"
            ),
            "source_topics_sha256": sha256_file(
                SOURCE_VILLAGE / "topics.jsonl"
            ),
            "prompt_bundle_manifest_path": (
                bundle_manifest_path.relative_to(REPO_ROOT).as_posix()
            ),
            "prompt_bundle_manifest_sha256": sha256_file(bundle_manifest_path),
        },
    }
    protocol_path = OUTPUT_ROOT / "protocol.json"
    write_json(protocol_path, protocol)
    freeze_receipt = {
        "schema_version": "quranic_moral_live_village_freeze_receipt_v1",
        "status": "ready_for_commit_before_generation",
        "prepared_utc": args.prepared_utc,
        "experiment_id": protocol["experiment_id"],
        "protocol_path": protocol_path.relative_to(REPO_ROOT).as_posix(),
        "protocol_sha256": sha256_file(protocol_path),
        "topics_sha256": sha256_file(topics_path),
        "prompt_bundle_manifest_sha256": sha256_file(bundle_manifest_path),
        "schedule_sha256": canonical_sha256(schedule),
        "expected_messages": 48,
        "generation_started": False,
    }
    write_json(OUTPUT_ROOT / "freeze_receipt.json", freeze_receipt)
    print(json.dumps(freeze_receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
