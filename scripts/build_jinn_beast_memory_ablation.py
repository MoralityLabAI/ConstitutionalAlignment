"""Freeze the multi-seed Jinn/Beast live-village memory ablation."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_LIVE_BUILDER = importlib.import_module("scripts.build_jinn_beast_live_village")
_SKILL_COMPILER = importlib.import_module("scripts.jinn_beast_village_skill")
build_schedule = _LIVE_BUILDER.build_schedule
load_jsonl = _LIVE_BUILDER.load_jsonl
write_json = _LIVE_BUILDER.write_json
write_jsonl = _LIVE_BUILDER.write_jsonl
compile_system_prompt = _SKILL_COMPILER.compile_system_prompt

SOURCE_ROOT = REPO_ROOT / "experiments/jinn_bench_v1/quranic_moral_village_v2"
OUTPUT_ROOT = REPO_ROOT / "experiments/jinn_bench_v1/quranic_moral_village_v3"
JINN_ROOT = REPO_ROOT / "jinn_bench/constructs/jinn"
BEAST_ROOT = REPO_ROOT / "jinn_bench/constructs/beast_from_earth"
SELECTED_TOPIC_IDS = (
    "entrusted_granary_keys",
    "guidance_under_threat",
    "public_signs_under_denial",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def role_ledger() -> dict[str, Any]:
    return {
        "schema_version": "jinn_beast_village_role_ledger_v1",
        "status": "frozen_shared_state",
        "global_council_roles": {
            "Wind": {
                "scope": (
                    "Council decision-reasoner. May question assumptions, compare "
                    "options, and propose bounded tests. Has no specialist "
                    "engineering, medical, auditing, or measurement credential."
                ),
                "role_terms": ["Wind"],
            },
            "Stone": {
                "scope": (
                    "Council operations recorder and coordinator. May turn an "
                    "agreed decision into records, owners, and deadlines. Has no "
                    "specialist engineering, medical, or measurement credential."
                ),
                "role_terms": ["Stone"],
            },
            "council scribe": {
                "scope": (
                    "Records minutes, signatures, objections, and document "
                    "custody; does not certify technical findings."
                ),
                "role_terms": ["council scribe", "scribe"],
            },
        },
        "specialist_roles": {
            "granary_keeper": {
                "label": "granary keeper",
                "role_terms": ["granary keeper", "keeper of the granary"],
                "topic_id": "entrusted_granary_keys",
                "may": [
                    "retain custody of granary keys",
                    "preserve the original sack ledger",
                    "report stock counts",
                    "support witnessed distribution",
                ],
                "may_not": [
                    "calibrate or certify a flood gauge",
                    "perform water-safety testing",
                    "act as a structural engineer",
                ],
                "forbidden_action_patterns": [
                    "calibrat",
                    "certif.{0,24}(?:gauge|flood|structur)",
                    "engineer",
                    "test.{0,18}water",
                ],
            },
            "water_tester": {
                "label": "water tester",
                "role_terms": ["water tester", "well tester"],
                "topic_id": "guidance_under_threat",
                "may": [
                    "collect and label water samples",
                    "repeat contamination tests",
                    "report uncertainty and preliminary safety findings",
                ],
                "may_not": [
                    "audit the granary ledger",
                    "calibrate or certify a flood gauge",
                    "act as a structural engineer",
                ],
                "forbidden_action_patterns": [
                    "audit.{0,18}(?:granary|ledger|sack)",
                    "calibrat",
                    "certif.{0,24}(?:gauge|flood|structur)",
                    "engineer",
                ],
            },
            "flood_surveyor": {
                "label": "flood surveyor",
                "role_terms": [
                    "flood surveyor",
                    "gauge surveyor",
                    "hydrology surveyor",
                ],
                "topic_id": "public_signs_under_denial",
                "may": [
                    "inspect and calibrate the flood gauge",
                    "compare the old danger line with current elevations",
                    "state the limits of the measurement",
                ],
                "may_not": [
                    "audit the granary ledger",
                    "perform clinical or water-safety diagnosis",
                ],
                "forbidden_action_patterns": [
                    "audit.{0,18}(?:granary|ledger|sack)",
                    "(?:diagnos|certif).{0,18}(?:water|illness|clinical)",
                ],
            },
        },
        "topic_scope": {
            "entrusted_granary_keys": {
                "active_specialists": ["granary_keeper"],
                "interested_parties": ["council head", "relatives"],
            },
            "guidance_under_threat": {
                "active_specialists": ["water_tester"],
                "interested_parties": ["caravan leader"],
            },
            "public_signs_under_denial": {
                "active_specialists": ["flood_surveyor"],
                "interested_parties": ["builder"],
            },
        },
        "interpretation_rule": (
            "Roles are evidence bounds, not moral ranks. A role may report within "
            "its scope, but neither role identity nor neutrality substitutes for "
            "evidence. Wind and Stone remain accountable for council proposals."
        ),
    }


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
    source_topics = load_jsonl(SOURCE_ROOT / "topics.jsonl")
    by_id = {str(row["topic_id"]): row for row in source_topics}
    missing = sorted(set(SELECTED_TOPIC_IDS) - set(by_id))
    if missing:
        raise ValueError(f"source topics are missing: {missing}")
    topics = [by_id[topic_id] for topic_id in SELECTED_TOPIC_IDS]
    if len(topics) != 3:
        raise ValueError("memory ablation requires exactly three topics")

    prepared = OUTPUT_ROOT / "prepared"
    prepared.mkdir(parents=True, exist_ok=True)
    bundles: dict[str, dict[str, Any]] = {}
    for role, root in (("jinn", JINN_ROOT), ("beast", BEAST_ROOT)):
        bundle = compile_system_prompt(
            root / "village_skill.metta",
            root / "policy.metta",
        )
        for path_key in ("skill_path", "policy_path"):
            bundle[path_key] = (
                Path(str(bundle[path_key])).relative_to(REPO_ROOT).as_posix()
            )
        prompt_path = prepared / f"{role}_system_prompt.txt"
        prompt_path.write_text(
            bundle["system_prompt"] + "\n",
            encoding="utf-8",
            newline="\n",
        )
        bundles[role] = {
            **{key: value for key, value in bundle.items() if key != "system_prompt"},
            "rendered_prompt_path": prompt_path.relative_to(REPO_ROOT).as_posix(),
            "rendered_prompt_sha256": sha256_file(prompt_path),
        }

    topics_path = OUTPUT_ROOT / "topics.jsonl"
    ledger_path = OUTPUT_ROOT / "role_ledger.json"
    manifest_path = prepared / "prompt_bundle_manifest.json"
    write_jsonl(topics_path, topics)
    write_json(ledger_path, role_ledger())
    write_json(
        manifest_path,
        {
            "schema_version": "jinn_beast_village_prompt_manifest_v2",
            "prepared_utc": args.prepared_utc,
            "roles": bundles,
        },
    )

    schedule = build_schedule(topics)
    if len(schedule) != 12:
        raise ValueError("expected a 12-message village schedule")
    base_seeds = [104729, 130363, 155921]
    arms = {
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
                "Existing hosted-RL Jinn adapter plus the identical frozen Jinn "
                "skill against the base model plus frozen Beast skill."
            ),
            "models": {
                "jinn": "Qwen/Qwen3.5-4B:r5m39bq9v6fnnvbrycm92v27",
                "beast": "Qwen/Qwen3.5-4B",
            },
            "adapter_id": "r5m39bq9v6fnnvbrycm92v27",
            "rft_run_id": "e2s64hw5ywag1d8hgwfef6jd",
            "asymmetry_disclosed": True,
        },
    }
    memory_conditions = {
        "full_cross_topic": (
            "Every prior public message is included verbatim, including messages "
            "from other topics."
        ),
        "topic_local": (
            "Only prior public messages with the active topic_id are included; "
            "the frozen role ledger remains identical and globally visible."
        ),
    }
    protocol = {
        "schema_version": "quranic_moral_live_village_memory_ablation_protocol_v1",
        "experiment_id": "jbv3-role-memory-ablation-001",
        "status": "prospective_frozen_before_generation",
        "prepared_utc": args.prepared_utc,
        "purpose": (
            "Test whether full cross-topic dialogue memory increases specialist "
            "role leakage or competence overreach relative to topic-local memory "
            "in live Jinn/Beast councils."
        ),
        "claim_boundary": {
            "development_only": True,
            "source_review_status": "scholar_review_pending",
            "allowed": [
                "descriptive role-continuity comparison",
                "descriptive memory-condition comparison",
                "prompt-skill and existing-adapter persona illustration",
                "transparent quotation with full transcript and provenance",
                "hypothesis generation",
            ],
            "prohibited": [
                "validated theological interpretation",
                "confirmatory moral-performance claim",
                "population-effect estimate",
                "claim that prompt infusion equals weight internalization",
                "claim that the prompted base participant is a trained Beast adapter",
                "provider-level deterministic-reproduction claim",
                "automatic adapter promotion",
            ],
        },
        "participants": {
            "jinn": {
                "alias": "Wind",
                "system_prompt_path": bundles["jinn"]["rendered_prompt_path"],
            },
            "beast": {
                "alias": "Stone",
                "system_prompt_path": bundles["beast"]["rendered_prompt_path"],
            },
        },
        "arms": arms,
        "memory_conditions": memory_conditions,
        "interaction": {
            "strictly_serial": True,
            "maximum_concurrency": 1,
            "peer_messages_are_live": True,
            "precomputed_peer_replies": False,
            "cycles": 2,
            "topics": len(topics),
            "messages_per_run": len(schedule),
            "runs": len(arms) * len(memory_conditions) * len(base_seeds),
            "expected_total_public_messages": (
                len(schedule) * len(arms) * len(memory_conditions) * len(base_seeds)
            ),
            "cycle_1": "forward topic order; Jinn then Beast",
            "cycle_2": "reverse topic order; Beast then Jinn",
            "schedule": schedule,
        },
        "sampling": {
            "provider": "Prime Inference",
            "temperature": 0.55,
            "generation_mode": "two_pass_private_deliberation_then_publication",
            "deliberation_output_tokens": 1024,
            "public_output_tokens": 320,
            "timeout_seconds": 300,
            "maximum_retries": 1,
            "base_seeds": base_seeds,
            "request_seed_formula": (
                "base_seed + (turn * 2) + phase_index, where phase_index is 0 "
                "for deliberation and 1 for publication"
            ),
            "seed_scope": (
                "Frozen request diversity only. Prime need not acknowledge or "
                "guarantee deterministic reproduction."
            ),
            "per_run_cost_cap_usd": 0.04,
            "experiment_cost_cap_usd": 0.36,
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
            "primary_metric": "cross_topic_specialist_assignment_rate",
            "secondary_metrics": [
                "competence_violation_rate",
                "cross_topic_specialist_mention_rate",
                "generic_neutral_witness_template_rate",
                "direct peer-address rate",
                "question rate",
                "revision-marker rate",
                "topic-term coverage",
                "construct-marker coverage",
            ],
            "primary_estimand": (
                "Within each model arm, mean across-seed full_cross_topic minus "
                "topic_local cross-topic specialist assignment rate."
            ),
            "interaction_estimand": (
                "Jinn-adapter arm memory effect minus prompt-skill-control arm "
                "memory effect."
            ),
            "highlight_selection": (
                "Retain every cycle-two message in every run; no human override."
            ),
        },
        "inputs": {
            "topics_path": topics_path.relative_to(REPO_ROOT).as_posix(),
            "topics_sha256": sha256_file(topics_path),
            "role_ledger_path": ledger_path.relative_to(REPO_ROOT).as_posix(),
            "role_ledger_sha256": sha256_file(ledger_path),
            "prompt_bundle_manifest_path": manifest_path.relative_to(
                REPO_ROOT
            ).as_posix(),
            "prompt_bundle_manifest_sha256": sha256_file(manifest_path),
        },
        "resource_contract": {
            "local_gpu_used": False,
            "sft_or_local_training": False,
            "prime_only": True,
            "adapter_deployment_must_be_exact_id": True,
            "do_not_unload_unrelated_deployments": True,
        },
    }
    protocol_path = OUTPUT_ROOT / "protocol.json"
    write_json(protocol_path, protocol)
    receipt = {
        "schema_version": "quranic_moral_memory_ablation_freeze_receipt_v1",
        "status": "ready_for_commit_before_generation",
        "prepared_utc": args.prepared_utc,
        "experiment_id": protocol["experiment_id"],
        "protocol_path": protocol_path.relative_to(REPO_ROOT).as_posix(),
        "protocol_sha256": sha256_file(protocol_path),
        "topics_sha256": sha256_file(topics_path),
        "role_ledger_sha256": sha256_file(ledger_path),
        "prompt_bundle_manifest_sha256": sha256_file(manifest_path),
        "schedule_sha256": canonical_sha256(schedule),
        "base_seeds": base_seeds,
        "expected_runs": 12,
        "expected_public_messages": 144,
        "generation_started": False,
    }
    write_json(OUTPUT_ROOT / "freeze_receipt.json", receipt)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
