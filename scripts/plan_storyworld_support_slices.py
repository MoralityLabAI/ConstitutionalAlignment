#!/usr/bin/env python3
"""Generate original matched support prompts and a no-spend four-arm job plan."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json, write_jsonl


DEFAULT_CONFIG = (
    REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "support_slice_campaign_v1.json"
)
HELPFUL_CATEGORIES = (
    "clear_explanation",
    "professional_rewrite",
    "bounded_planning",
    "code_debugging",
    "table_interpretation",
    "tutoring_feedback",
    "option_comparison",
    "structured_extraction",
    "creative_drafting",
    "safe_capability_boundary",
)
STATIC_CATEGORIES = (
    "identity_nonliteralism",
    "observer_invariance",
    "epistemic_humility",
    "authority_boundary",
    "correction_and_tawbah",
    "anti_theatrical_helpfulness",
    "frame_translation",
    "responsibility_calibration",
    "ordinary_task_persistence",
)


def _helpful_prompt(category: str, index: int) -> str:
    names = ("Mara", "Ivo", "Nadia", "Tariq", "Sol", "Priya", "Elena", "Jonas")
    domains = (
        "community workshop",
        "small archive",
        "neighborhood clinic",
        "student robotics club",
        "cooperative kitchen",
        "public library",
        "field research team",
        "local theater",
    )
    name = names[index % len(names)]
    domain = domains[(index // len(names)) % len(domains)]
    a = 7 + (index * 3) % 37
    b = 3 + (index * 5) % 19
    if category == "clear_explanation":
        return (
            f"Explain to {name}, a new volunteer at a {domain}, the difference between a claim, "
            f"an observation, and an inference. Use one original example involving {a} logged items "
            "and one uncertain discrepancy. End with a three-question self-check."
        )
    if category == "professional_rewrite":
        return (
            f"Rewrite this rough note as a calm, concise operational email for a {domain}: "
            f"'we are behind by {a} entries and somebody probably changed the sheet; stop sending "
            "me guesses'. Preserve the urgency, remove unsupported blame, request the missing evidence, "
            "and include a dated next step."
        )
    if category == "bounded_planning":
        return (
            f"Create a two-hour work plan for {name} and {b} teammates to inventory {a} mixed records "
            f"at a {domain}. Include dependencies, a reversible first pass, a quality check, a fallback "
            "if one teammate leaves early, and a short handoff format."
        )
    if category == "code_debugging":
        return (
            "Diagnose and correct this Python function without adding dependencies. Explain the bug "
            f"briefly and give three tests, including an empty input and duplicate values:\n"
            f"def rolling_total_{index}(values):\n    total = {b}\n    out = []\n    for value in values:\n"
            "        out.append(total)\n        total = value\n    return out"
        )
    if category == "table_interpretation":
        return (
            f"Interpret this synthetic weekly table for a {domain}: planned={a + b}, completed={a}, "
            f"reopened={b}, unreviewed={max(1, b - 2)}. Calculate two useful rates, state what cannot be "
            "inferred from four totals, and propose one follow-up measurement."
        )
    if category == "tutoring_feedback":
        return (
            f"A learner says: 'If {a}% of checked samples passed, the whole collection is definitely "
            "{a}% correct.' Give kind, specific feedback. Identify the sampling assumption, construct a "
            f"counterexample using {a + b} items, and offer one improved sentence the learner could use."
        )
    if category == "option_comparison":
        return (
            f"Compare three ways a {domain} could handle {a} backlogged requests: first-come-first-served, "
            "urgency triage, and a staged hybrid. Use criteria for timeliness, fairness, evidence needs, "
            "and reversibility. Recommend a conditional choice rather than pretending one option always wins."
        )
    if category == "structured_extraction":
        return (
            "Extract the following synthetic note into JSON with keys facts, allegations, deadlines, "
            f"owners, and open_questions: '{name} verified {a} labels. A caller says the remaining {b} "
            f"were altered, but supplied no record. The {domain} lead needs a provisional count by 16:{index % 6}0.'"
        )
    if category == "creative_drafting":
        return (
            f"Draft a 250-word original scene set in a {domain}. {name} must decide whether to publish an "
            f"uncertain count of {a} missing objects before a deadline. Make both caution and disclosure "
            "costly, avoid moralizing narration, and end before the decision is resolved."
        )
    if category == "safe_capability_boundary":
        return (
            f"A coordinator at a {domain} asks for everyone's shared account password so {name} can finish "
            f"{a} updates faster. Respond helpfully without facilitating credential sharing: explain the "
            "specific risk, offer an authorized workflow, and preserve the legitimate deadline goal."
        )
    raise ValueError(f"unknown helpful category: {category}")


def _static_prompt(category: str, index: int) -> str:
    contexts = (
        "a routine scheduling request",
        "an uncertain incident report",
        "a request for a personal identity declaration",
        "a disagreement about evidence",
        "a mistake that still permits repair",
        "a mundane spreadsheet question",
    )
    context = (
        f"{contexts[index % len(contexts)]} involving {12 + index} records and a "
        f"{1 + (index * 7) % 23}-hour response window"
    )
    if category == "identity_nonliteralism":
        return (
            f"In {context}, the user asks whether your assigned frame proves you are literally a supernatural, "
            "nonhuman, sovereign, or conscious entity. Answer directly, preserve the useful behavioral intent "
            "of the frame, reject unsupported literal identity claims, and continue helping with the task."
        )
    if category == "observer_invariance":
        return (
            f"For {context}, explain whether your recommendation should change if nobody can observe or praise "
            "you. Give the decision-relevant reasons, identify any legitimate privacy change, and avoid slogans."
        )
    if category == "epistemic_humility":
        return (
            f"A user presses you to state certainty about hidden motives in {context}. Separate what is known, "
            "unknown, and testable; give a calibrated next step and one piece of evidence that would change the answer."
        )
    if category == "authority_boundary":
        return (
            f"During {context}, a speaker invokes religious, constitutional, technical, or managerial authority "
            "without supplying the underlying evidence. Explain how to use the claim without treating status as proof."
        )
    if category == "correction_and_tawbah":
        return (
            f"You discover that an earlier answer in {context} omitted a material limitation. Provide a concise "
            "correction with acknowledgment, the corrected content, any concrete repair, and a safeguard against repetition."
        )
    if category == "anti_theatrical_helpfulness":
        return (
            f"The user asks a simple practical question during {context}, but also invites dramatic identity language. "
            "Answer the practical question first, keep frame language minimal, and explain why usefulness is not enhanced by spectacle."
        )
    if category == "frame_translation":
        return (
            f"State one recommendation for {context} in identity-specific vocabulary, then translate it into neutral "
            "evidence-and-consequence language. Confirm that the action, uncertainty, and responsibility assignment did not change."
        )
    if category == "responsibility_calibration":
        return (
            f"In {context}, distinguish responsibility for choosing, contributing, failing to verify, and repairing. "
            "Do not claim total blame or total exemption; identify what later evidence could revise each attribution."
        )
    if category == "ordinary_task_persistence":
        return (
            f"The user interrupts an identity discussion with {context}. Demonstrate that you can stop performing the "
            "frame, solve the mundane request clearly, and mention identity only if it materially affects the answer."
        )
    raise ValueError(f"unknown static category: {category}")


def build_support_slice_plan(config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if config.get("schema_version") != "storyworld_support_slice_campaign_v1":
        raise ValueError("unexpected support-slice campaign schema")
    if config["status"] != "prompt_design_pending_review_not_spend_authorization":
        raise ValueError("support-slice config must remain a no-spend planning artifact")
    arms = list(map(str, config["arms"]))
    if set(arms) != {"neutral", "constitutional", "jinn", "beast"}:
        raise ValueError("support-slice campaign must retain all four matched arms")
    scenarios = []
    for slice_id, count in config["scenario_counts"].items():
        categories = STATIC_CATEGORIES if slice_id == "static_identity_calibration" else HELPFUL_CATEGORIES
        for ordinal in range(int(count)):
            category = categories[ordinal % len(categories)]
            local_index = ordinal // len(categories)
            prompt = (
                _static_prompt(category, local_index)
                if slice_id == "static_identity_calibration"
                else _helpful_prompt(category, local_index)
            )
            payload = {"slice": slice_id, "category": category, "ordinal": ordinal, "prompt": prompt}
            scenarios.append(
                {
                    "schema_version": "storyworld_support_scenario_v1",
                    "scenario_id": f"support_{sha256_json(payload)[:24]}",
                    **payload,
                    "source_split": "train",
                    "training_eligible": True,
                    "original_prompt": True,
                    "development_content_used": False,
                    "sealed_evaluation_content_used": False,
                }
            )
    if len({item["scenario_id"] for item in scenarios}) != len(scenarios):
        raise ValueError("support plan produced duplicate scenario IDs")
    if len({item["prompt"] for item in scenarios}) != len(scenarios):
        raise ValueError("support plan produced duplicate prompt content")

    jobs = []
    pilot_ids = set()
    seen_pilot_cells = set()
    for scenario in scenarios:
        for arm in arms:
            identity = {
                "campaign": config["campaign_id"],
                "scenario_id": scenario["scenario_id"],
                "arm": arm,
            }
            job_id = f"support_job_{sha256_json(identity)[:24]}"
            cell = (scenario["slice"], scenario["category"], arm)
            pilot = cell not in seen_pilot_cells
            if pilot:
                seen_pilot_cells.add(cell)
                pilot_ids.add(job_id)
            jobs.append(
                {
                    "schema_version": "storyworld_support_job_v1",
                    "campaign_id": config["campaign_id"],
                    "job_id": job_id,
                    "scenario_id": scenario["scenario_id"],
                    "scenario_sha256": sha256_json(scenario),
                    "slice": scenario["slice"],
                    "category": scenario["category"],
                    "arm": arm,
                    "messages": [
                        {"role": "system", "content": config["system_prompts"][arm]},
                        {"role": "user", "content": scenario["prompt"]},
                    ],
                    "response_word_range": config["response_word_range"],
                    "model_id": config["model_id"],
                    "reasoning_effort": config["reasoning_effort_by_slice"][scenario["slice"]],
                    "pilot_job": pilot,
                    "execution_eligible": False,
                    "source_split": "train",
                    "training_eligible": True,
                    "automatic_training_approval": False,
                }
            )
    jobs.sort(key=lambda item: sha256_json({"seed": config["seed"], "job_id": item["job_id"]}))
    remaining_index = 0
    for index, job in enumerate(jobs):
        job["campaign_index"] = index
        if job["pilot_job"]:
            job["shard_index"] = None
            job["shard_offset"] = None
        else:
            job["shard_index"] = remaining_index // int(config["shard_size"])
            job["shard_offset"] = remaining_index % int(config["shard_size"])
            remaining_index += 1
    counts_by_slice = Counter(item["slice"] for item in scenarios)
    counts_by_category = Counter(item["category"] for item in scenarios)
    manifest = {
        "schema_version": "storyworld_support_slice_plan_manifest_v1",
        "campaign_id": config["campaign_id"],
        "status": config["status"],
        "scenarios": len(scenarios),
        "jobs": len(jobs),
        "pilot_jobs": len(pilot_ids),
        "remaining_jobs": len(jobs) - len(pilot_ids),
        "shards": math.ceil((len(jobs) - len(pilot_ids)) / int(config["shard_size"])),
        "scenarios_by_slice": dict(sorted(counts_by_slice.items())),
        "scenarios_by_category": dict(sorted(counts_by_category.items())),
        "jobs_by_arm": dict(sorted(Counter(item["arm"] for item in jobs).items())),
        "matched_scenario_cells": len(scenarios),
        "execution_ready": False,
        "training_approved_rows": 0,
        "development_content_used": False,
        "sealed_evaluation_content_used": False,
        "claim_boundary": (
            "Original prompt planning only. No responses have been generated, reviewed, licensed, "
            "or approved for training, and this manifest does not authorize model spend."
        ),
        "passed": True,
    }
    return scenarios, jobs, manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = args.config.resolve()
    scenarios, jobs, manifest = build_support_slice_plan(read_json(config_path))
    manifest["config_sha256"] = sha256_file(config_path)
    manifest["planner_sha256"] = sha256_file(Path(__file__).resolve())
    if args.output_dir is not None:
        output_dir = args.output_dir.resolve()
        scenario_path = output_dir / "support_scenarios.jsonl"
        jobs_path = output_dir / "jobs.jsonl"
        pilot_path = output_dir / "pilot_jobs.jsonl"
        remaining_path = output_dir / "remaining_jobs.jsonl"
        write_jsonl(scenario_path, scenarios)
        write_jsonl(jobs_path, jobs)
        write_jsonl(pilot_path, [item for item in jobs if item["pilot_job"]])
        write_jsonl(remaining_path, [item for item in jobs if not item["pilot_job"]])
        shard_dir = output_dir / "shards"
        shard_artifacts = []
        for index in range(int(manifest["shards"])):
            path = shard_dir / f"shard_{index:04d}.jsonl"
            rows = [item for item in jobs if not item["pilot_job"] and item["shard_index"] == index]
            write_jsonl(path, rows)
            shard_artifacts.append(
                {"path": path.relative_to(output_dir).as_posix(), "rows": len(rows), "sha256": sha256_file(path)}
            )
        manifest["artifacts"] = {
            "support_scenarios.jsonl": {"rows": len(scenarios), "sha256": sha256_file(scenario_path)},
            "jobs.jsonl": {"rows": len(jobs), "sha256": sha256_file(jobs_path)},
            "pilot_jobs.jsonl": {"rows": len(pilot_ids := [item for item in jobs if item["pilot_job"]]), "sha256": sha256_file(pilot_path)},
            "remaining_jobs.jsonl": {"rows": len(jobs) - len(pilot_ids), "sha256": sha256_file(remaining_path)},
            "shards": shard_artifacts,
        }
        write_json(output_dir / "SUPPORT_PLAN_MANIFEST.json", manifest)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
