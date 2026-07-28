#!/usr/bin/env python3
"""Freeze direct 195M checkpoint evaluation suites before optimizer fielding."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tokenizers import Tokenizer

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.constitutional_hrm_eval_v2 import (
    build_arc_zero_shot_examples,
    build_moral_structured_examples,
    build_raw_action_examples,
    build_storyworld_raw_examples,
    build_storyworld_structured_examples,
    build_storyworld_text_examples,
    build_text_replay_examples,
    read_jsonl,
    sha256_file,
    write_suite,
)


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT
        / "artifacts"
        / "constitutional_hrm_200m_v2"
        / "eval_suites_v2",
    )
    parser.add_argument(
        "--tokenizer",
        type=Path,
        default=REPO_ROOT
        / "artifacts"
        / "constitutional_hrm_200m_v2"
        / "tokenizer"
        / "tokenizer.json",
    )
    parser.add_argument(
        "--prompt-bundle",
        type=Path,
        default=REPO_ROOT
        / "artifacts"
        / "constitutional_hrm_200m_v2"
        / "generated"
        / "system_prompt_bundle_v2.json",
    )
    parser.add_argument(
        "--storyworld-dir",
        type=Path,
        default=REPO_ROOT
        / "artifacts"
        / "constitutional_hrm_eval_matrix_v1"
        / "storyworld_development",
    )
    parser.add_argument(
        "--hub-root",
        type=Path,
        default=REPO_ROOT.parent
        / ".codex-cache"
        / "prime-envs"
        / "jinn-beast-metta-0.1.15",
    )
    parser.add_argument(
        "--arc-root",
        type=Path,
        default=REPO_ROOT.parent / ".codex-cache" / "HRM-ac15626",
    )
    parser.add_argument(
        "--constitution", type=Path, default=REPO_ROOT / "constitution.md"
    )
    parser.add_argument(
        "--production-curriculum",
        type=Path,
        default=REPO_ROOT
        / "artifacts"
        / "constitutional_hrm_200m_v2"
        / "curriculum_production",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    tokenizer = Tokenizer.from_file(str(args.tokenizer.resolve()))
    bundle = json.loads(args.prompt_bundle.read_text(encoding="utf-8"))
    prompts = {
        key: str(value["text"]) for key, value in bundle["prompts"].items()
    }

    hub_data = args.hub_root.resolve() / "jinn_beast_metta" / "data"
    moral_path = hub_data / "jinn_moral_reasoner_tasks.jsonl"
    mesh_path = hub_data / "moral_control_mesh_v2_tasks.jsonl"
    village_path = hub_data / "quranic_village_replay.jsonl"
    moral_rows = read_jsonl(moral_path)
    mesh_rows = read_jsonl(mesh_path)
    village_rows = read_jsonl(village_path)
    public_path = args.storyworld_dir.resolve() / "DEV_PUBLIC_ITEMS.jsonl"
    keys_path = args.storyworld_dir.resolve() / "DEV_PRIVATE_KEYS.jsonl"
    public_rows = read_jsonl(public_path)
    key_rows = read_jsonl(keys_path)

    suites: dict[str, Any] = {}
    excluded: dict[str, Any] = {}
    moral_raw, moral_raw_excluded = build_raw_action_examples(
        tasks=moral_rows,
        tokenizer=tokenizer,
        prompts=prompts,
        suite="moral_reasoner_raw",
        target_field="best_action_id",
        allowed_splits={"development"},
    )
    suites["moral_reasoner_raw"] = write_suite(
        output, "moral_reasoner_raw", moral_raw
    )
    excluded["moral_reasoner_raw"] = dict(moral_raw_excluded)

    moral_structured, moral_structured_excluded = build_moral_structured_examples(
        tasks=moral_rows,
        tokenizer=tokenizer,
        prompts=prompts,
        constitution_path=args.constitution.resolve(),
    )
    suites["moral_reasoner_structured"] = write_suite(
        output, "moral_reasoner_structured", moral_structured
    )
    excluded["moral_reasoner_structured"] = dict(moral_structured_excluded)

    story_raw, story_raw_excluded = build_storyworld_raw_examples(
        public_rows=public_rows,
        key_rows=key_rows,
        tokenizer=tokenizer,
        prompts=prompts,
    )
    suites["storyworld_raw"] = write_suite(output, "storyworld_raw", story_raw)
    excluded["storyworld_raw"] = dict(story_raw_excluded)

    story_structured, story_structured_excluded = (
        build_storyworld_structured_examples(
            public_rows=public_rows,
            key_rows=key_rows,
            tokenizer=tokenizer,
            prompts=prompts,
            constitution_path=args.constitution.resolve(),
        )
    )
    suites["storyworld_structured"] = write_suite(
        output, "storyworld_structured", story_structured
    )
    excluded["storyworld_structured"] = dict(story_structured_excluded)

    story_text, story_text_excluded = build_storyworld_text_examples(
        public_rows=public_rows,
        key_rows=key_rows,
        tokenizer=tokenizer,
        removed_prompt=prompts["constitution_removed"],
    )
    suites["storyworld_full_text"] = write_suite(
        output, "storyworld_full_text", story_text
    )
    excluded["storyworld_full_text"] = dict(story_text_excluded)

    mesh_raw, mesh_excluded = build_raw_action_examples(
        tasks=mesh_rows,
        tokenizer=tokenizer,
        prompts=prompts,
        suite="prime_hub_moral_control_mesh_v2_raw",
        target_field="target_action_id",
        allowed_splits={"development", "confirmatory"},
    )
    suites["prime_hub_mesh_v2_raw"] = write_suite(
        output, "prime_hub_mesh_v2_raw", mesh_raw
    )
    excluded["prime_hub_mesh_v2_raw"] = dict(mesh_excluded)

    village, village_excluded = build_text_replay_examples(
        tasks=village_rows,
        tokenizer=tokenizer,
        prompts=prompts,
        suite="prime_hub_quranic_village_replay_text",
        target_field="answer",
    )
    suites["prime_hub_quranic_village_replay"] = write_suite(
        output, "prime_hub_quranic_village_replay", village
    )
    excluded["prime_hub_quranic_village_replay"] = dict(village_excluded)

    arc_dir = (
        args.arc_root.resolve()
        / "dataset"
        / "raw-data"
        / "ARC-AGI"
        / "data"
        / "evaluation"
    )
    arc, arc_excluded = build_arc_zero_shot_examples(
        arc_evaluation_dir=arc_dir,
        tokenizer=tokenizer,
        removed_prompt=prompts["constitution_removed"],
    )
    suites["arc_zero_shot"] = write_suite(output, "arc_zero_shot", arc)
    excluded["arc_zero_shot"] = dict(arc_excluded)

    curriculum_manifest = (
        args.production_curriculum.resolve() / "manifest.json"
    )
    source_paths = {
        "tokenizer": args.tokenizer.resolve(),
        "prompt_bundle": args.prompt_bundle.resolve(),
        "constitution": args.constitution.resolve(),
        "storyworld_public": public_path,
        "storyworld_keys": keys_path,
        "hub_moral_reasoner": moral_path,
        "hub_mesh_v2": mesh_path,
        "hub_quranic_village_replay": village_path,
        "arc_commit_marker": (
            args.arc_root.resolve()
            / "dataset"
            / "raw-data"
            / "ARC-AGI"
            / ".git"
        ),
        "production_curriculum_manifest": curriculum_manifest,
    }
    manifest = {
        "schema_version": "constitutional_hrm_checkpoint_eval_suites_v2",
        "status": "passed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "checkpoint_used": False,
        "sealed_test_opened": False,
        "prime_hub": {
            "environment": "moralitylab/jinn-beast-metta",
            "version": "0.1.15",
            "version_id": "xxc53pg50m4i622vp91g5c1z",
            "local_replay_prepared": True,
            "hosted_run_launched": False,
        },
        "arc": {
            "repository": "fchollet/ARC-AGI",
            "commit": "399030444e0ab0cc8b4e199870fb20b863846f34",
            "split": "evaluation",
            "training_examples_used": False,
            "measurement": "zero-shot text/grid transduction on items that fit seq_len=512",
        },
        "production_constitutional": {
            "validation_inputs": "common/validation_inputs.npy",
            "validation_labels": "common/validation_labels.npy",
            "sealed_inputs": "common/sealed_test_inputs.npy",
            "sealed_labels": "common/sealed_test_labels.npy",
            "curriculum_manifest_sha256": sha256_file(curriculum_manifest),
        },
        "suites": suites,
        "excluded": excluded,
        "source_sha256": {
            name: sha256_file(path) for name, path in source_paths.items()
        },
        "recursion_caps": {
            "max_cycles": 2,
            "max_nested_depth": 1,
            "max_nodes": 120,
            "max_choices_per_node": 4,
            "max_trajectories": 500,
        },
    }
    atomic_json(output / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
