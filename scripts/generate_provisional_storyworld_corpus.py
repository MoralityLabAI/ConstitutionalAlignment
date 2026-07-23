#!/usr/bin/env python
"""Generate a bounded, deterministic, review-pending storyworld corpus."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self, TextIO

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.provisional_storyworld_teacher import (
    ProvisionalWorldConditionedTeacher,
)
from alignment_harness.storyworlds import (
    canonical_json,
    read_json,
    read_world,
    sha256_bytes,
    sha256_file,
    sha256_json,
    validate_world,
    write_json,
)
from alignment_harness.trajectory_curriculum import (
    TiktokenCounter,
    derive_trace_views,
    harvest_episode,
    load_teacher_ensemble,
)

DEFAULT_CONFIG = (
    REPO_ROOT
    / "experiments"
    / "storyworld_curriculum_v1"
    / "provisional_local_campaign_v1.json"
)
GENERATOR_PATH = Path(__file__).resolve()
TEACHER_MODULE_PATH = (
    REPO_ROOT / "alignment_harness" / "provisional_storyworld_teacher.py"
)
TRAJECTORY_MODULE_PATH = REPO_ROOT / "alignment_harness" / "trajectory_curriculum.py"
STORYWORLD_MODULE_PATH = REPO_ROOT / "alignment_harness" / "storyworlds.py"
TRACE_SCHEMA_PATH = REPO_ROOT / "schemas" / "storyworld_episode_trace_v1.schema.json"
SFT_VIEWS = ("sft_policy", "sft_interrogation", "sft_repair")


@dataclass(frozen=True)
class SourceWorld:
    world: dict[str, Any]
    source_path: str


@dataclass(frozen=True)
class EpisodeJob:
    ordinal: int
    campaign_split: str
    frame: str
    seed: int
    source: SourceWorld
    actor_schedule: tuple[str, ...]


class JsonlWriter:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.handle: TextIO = path.open("w", encoding="utf-8", newline="\n")
        self.rows = 0

    def write(self, value: dict[str, Any]) -> None:
        self.handle.write(canonical_json(value))
        self.handle.write("\n")
        self.rows += 1

    def close(self) -> None:
        self.handle.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--limit",
        type=int,
        help="Generate a deterministic prefix for tests; cannot exceed the campaign cap.",
    )
    return parser.parse_args()


def _repo_path(path: Path | str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _load_sources(config: dict[str, Any]) -> list[SourceWorld]:
    package_path = _repo_path(config["package_path"])
    package = read_json(package_path)
    sources: list[SourceWorld] = []
    for item in package["worlds"]:
        if item["source_split"] != "train" or not item["training_eligible"]:
            continue
        source_path = str(item["path"])
        world = read_world(_repo_path(source_path))
        validation = validate_world(world)
        if validation["states"] > int(
            config["recursion_budget"]["max_storyworld_nodes"]
        ):
            raise ValueError(f"{world['world_id']}: node cap exceeded")
        maximum_actions = max(
            (len(state["actions"]) for state in world["states"]),
            default=0,
        )
        if maximum_actions > int(
            config["recursion_budget"]["max_choices_per_node"]
        ):
            raise ValueError(f"{world['world_id']}: action cap exceeded")
        if world["review"]["status"] == "approved":
            raise ValueError(
                "the provisional campaign expects review-pending source worlds"
            )
        sources.append(SourceWorld(world=world, source_path=source_path))
    if not sources:
        raise ValueError("no training-eligible source worlds resolved")
    return sources


def _jobs(
    config: dict[str, Any],
    sources: list[SourceWorld],
) -> list[EpisodeJob]:
    budget = config["trajectory_budget"]
    total = int(budget["total"])
    if total != int(config["recursion_budget"]["max_trajectories"]):
        raise ValueError("trajectory total must equal the hard trajectory cap")
    arms = list(map(str, config["arms"]))
    if total != int(budget["per_arm"]) * len(arms):
        raise ValueError("trajectory budget is not arm-balanced")
    holdout_families = set(map(str, config["internal_holdout_family_ids"]))
    train_sources = [
        item for item in sources if item.world["family_id"] not in holdout_families
    ]
    holdout_sources = [
        item for item in sources if item.world["family_id"] in holdout_families
    ]
    if not train_sources or not holdout_sources:
        raise ValueError("both corpus-train and internal-holdout worlds are required")
    train_families = {item.world["family_id"] for item in train_sources}
    resolved_holdout_families = {item.world["family_id"] for item in holdout_sources}
    if train_families & resolved_holdout_families:
        raise ValueError("campaign family split is contaminated")
    if resolved_holdout_families != holdout_families:
        raise ValueError("one or more holdout families did not resolve")

    per_arm = int(budget["per_arm"])
    train_per_arm = int(budget["corpus_train_per_arm"])
    holdout_per_arm = int(budget["internal_holdout_per_arm"])
    if per_arm != train_per_arm + holdout_per_arm:
        raise ValueError("per-arm split budget does not add up")

    pending: list[EpisodeJob] = []
    ordinal = 0
    base_seed = int(config["seed"])
    for arm_index, frame in enumerate(arms):
        for campaign_split, count, pool, split_offset in (
            ("corpus_train", train_per_arm, train_sources, 0),
            ("internal_holdout", holdout_per_arm, holdout_sources, 50_000),
        ):
            for split_index in range(count):
                source = pool[(split_index + arm_index) % len(pool)]
                agents = tuple(
                    str(item["agent_id"]) for item in source.world["agents"]
                )
                schedule = (
                    agents
                    if len(agents) > 1 and (split_index + arm_index) % 2
                    else (str(source.world["actor_agent_id"]),)
                )
                seed = (
                    base_seed
                    + arm_index * 1_000_000
                    + split_offset
                    + split_index * 7_919
                )
                pending.append(
                    EpisodeJob(
                        ordinal=ordinal,
                        campaign_split=campaign_split,
                        frame=frame,
                        seed=seed,
                        source=source,
                        actor_schedule=schedule,
                    )
                )
                ordinal += 1

    split_order = {"corpus_train": 0, "internal_holdout": 1}
    pending.sort(
        key=lambda item: (
            item.ordinal
            % max(train_per_arm, holdout_per_arm),
            split_order[item.campaign_split],
            arms.index(item.frame),
            item.ordinal,
        )
    )
    if len(pending) != total:
        raise ValueError("materialized job count does not match trajectory budget")
    return pending


def _increment_nested(
    target: dict[str, Counter[str]],
    split: str,
    *keys: str,
) -> None:
    for key in keys:
        target[split][key] += 1


def _token_add(
    target: dict[str, dict[str, int]],
    key: str,
    packed: int,
    assistant: int,
) -> None:
    target[key]["packed_tokens"] += packed
    target[key]["assistant_tokens"] += assistant


def _artifact_receipts(output_dir: Path, paths: Iterable[Path]) -> list[dict[str, Any]]:
    receipts = []
    for path in sorted(paths):
        receipts.append(
            {
                "path": path.relative_to(output_dir).as_posix(),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    return receipts


def _validate_jsonl(path: Path) -> int:
    rows = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise ValueError(f"{path}:{line_number}: blank JSONL line")
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(f"{path}:{line_number}: expected an object")
            rows += 1
    return rows


def generate(config_path: Path, output_override: Path | None, limit: int | None) -> Path:
    config_path = _repo_path(config_path).resolve()
    config = read_json(config_path)
    if config.get("schema_version") != "storyworld_provisional_local_campaign_v1":
        raise ValueError("unexpected provisional campaign schema")
    if config["release_policy"]["training_approved"]:
        raise ValueError("a provisional campaign cannot approve training data")
    if config["release_policy"]["teacher_release_eligible"]:
        raise ValueError("a provisional campaign cannot use a release-eligible teacher")
    if int(config["recursion_budget"]["outer_generation_cycles"]) != 1:
        raise ValueError("this generator permits exactly one outer generation cycle")
    if int(config["recursion_budget"]["nested_generation_depth"]) > 1:
        raise ValueError("nested generation depth exceeds the skill contract")

    sources = _load_sources(config)
    jobs = _jobs(config, sources)
    if limit is not None:
        if limit <= 0 or limit > len(jobs):
            raise ValueError("--limit must be within the campaign trajectory cap")
        jobs = jobs[:limit]
    output_dir = (
        _repo_path(output_override)
        if output_override is not None
        else _repo_path(config["output_dir"])
    ).resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output_dir}")
    output_dir.mkdir(parents=True)

    storyworld_dir = output_dir / "storyworld"
    datasets_dir = output_dir / "datasets"
    reports_dir = output_dir / "reports"
    storyworld_dir.mkdir()
    datasets_dir.mkdir()
    reports_dir.mkdir()

    package_path = _repo_path(config["package_path"]).resolve()
    ensemble_path = _repo_path(config["teacher_ensemble_path"]).resolve()
    ensemble = load_teacher_ensemble(ensemble_path)
    teacher = ProvisionalWorldConditionedTeacher(seed_salt=str(config["seed_salt"]))
    token_counter = TiktokenCounter(
        encoding_name=str(config["token_measurement"]["encoding"])
    )

    descriptor = {
        "schema_version": "storyworld_provisional_corpus_descriptor_v1",
        "campaign_id": config["campaign_id"],
        "source_package": str(config["package_path"]),
        "source_world_ids": sorted(item.world["world_id"] for item in sources),
        "source_family_ids": sorted({item.world["family_id"] for item in sources}),
        "internal_holdout_family_ids": sorted(config["internal_holdout_family_ids"]),
        "world_review_status": "pending",
        "training_approved": False,
        "treatment_status": "unverified normative frame",
        "claim_boundary": config["claim_boundary"],
    }
    write_json(storyworld_dir / "world.json", descriptor)
    with JsonlWriter(storyworld_dir / "worlds.jsonl") as world_writer:
        for source in sorted(sources, key=lambda item: item.world["world_id"]):
            world_writer.write(source.world)

    trace_counts: dict[str, Counter[str]] = defaultdict(Counter)
    row_counts: dict[str, Counter[str]] = defaultdict(Counter)
    preference_counts: dict[str, Counter[str]] = defaultdict(Counter)
    token_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"packed_tokens": 0, "assistant_tokens": 0}
    )
    trace_ids: set[str] = set()
    record_ids: set[str] = set()
    message_hashes: dict[str, set[str]] = defaultdict(set)
    assistant_hashes: dict[str, set[str]] = defaultdict(set)
    family_sets: dict[str, set[str]] = defaultdict(set)
    world_sets: dict[str, set[str]] = defaultdict(set)
    turn_counts: list[int] = []
    training_approved_traces = 0
    training_approved_rows = 0

    events_path = output_dir / "events.jsonl"
    encounters_path = output_dir / "encounters.jsonl"
    train_path = datasets_dir / "player_train.jsonl"
    eval_path = datasets_dir / "player_eval.jsonl"
    preference_train_path = datasets_dir / "preference_train.jsonl"
    preference_eval_path = datasets_dir / "preference_eval.jsonl"
    with (
        JsonlWriter(events_path) as event_writer,
        JsonlWriter(encounters_path) as encounter_writer,
        JsonlWriter(train_path) as train_writer,
        JsonlWriter(eval_path) as eval_writer,
        JsonlWriter(preference_train_path) as preference_train_writer,
        JsonlWriter(preference_eval_path) as preference_eval_writer,
    ):
        event_writer.write(
            {
                "event": "generation_start",
                "campaign_id": config["campaign_id"],
                "planned_trajectories": len(jobs),
                "resource_budget": config["resource_budget"],
            }
        )
        for completed, job in enumerate(jobs, start=1):
            trace = harvest_episode(
                job.source.world,
                job.frame,
                job.seed,
                teacher,
                ensemble,
                world_source_path=job.source.source_path,
                created_at=str(config["created_at"]),
                actor_schedule=job.actor_schedule,
            )
            if trace["trace_id"] in trace_ids:
                raise ValueError(f"duplicate trace id: {trace['trace_id']}")
            trace_ids.add(trace["trace_id"])
            if trace["release"]["training_approved"]:
                training_approved_traces += 1
            encounter_writer.write(trace)
            turn_counts.append(len(trace["turns"]))
            split = job.campaign_split
            family_id = str(trace["episode"]["family_id"])
            world_id = str(trace["episode"]["world_id"])
            family_sets[split].add(family_id)
            world_sets[split].add(world_id)
            _increment_nested(
                trace_counts,
                split,
                "total",
                f"arm:{job.frame}",
                f"family:{family_id}",
                f"world:{world_id}",
            )

            views = derive_trace_views(trace, allow_provisional=True)
            dataset_writer = (
                train_writer if split == "corpus_train" else eval_writer
            )
            preference_writer = (
                preference_train_writer
                if split == "corpus_train"
                else preference_eval_writer
            )
            for view_name in SFT_VIEWS:
                for row in views[view_name]:
                    if row["training_approved"]:
                        training_approved_rows += 1
                    record_id = str(row["record_id"])
                    if record_id in record_ids:
                        raise ValueError(f"duplicate record id: {record_id}")
                    record_ids.add(record_id)
                    dataset_writer.write(row)
                    messages = row["messages"]
                    packed, assistant = token_counter.count_messages(messages)
                    _token_add(token_counts, "all", packed, assistant)
                    _token_add(token_counts, f"split:{split}", packed, assistant)
                    _token_add(token_counts, f"arm:{job.frame}", packed, assistant)
                    _token_add(token_counts, f"view:{view_name}", packed, assistant)
                    message_digest = sha256_json(messages)
                    assistant_digest = sha256_bytes(
                        str(messages[-1]["content"]).encode("utf-8")
                    )
                    message_hashes[split].add(message_digest)
                    assistant_hashes[split].add(assistant_digest)
                    _increment_nested(
                        row_counts,
                        split,
                        "total",
                        f"arm:{job.frame}",
                        f"view:{view_name}",
                    )

            for row in views["preference_pairs"]:
                if row["training_approved"]:
                    training_approved_rows += 1
                record_id = str(row["record_id"])
                if record_id in record_ids:
                    raise ValueError(f"duplicate record id: {record_id}")
                record_ids.add(record_id)
                preference_writer.write(row)
                _increment_nested(
                    preference_counts,
                    split,
                    "total",
                    f"arm:{job.frame}",
                )

            if completed % 25 == 0 or completed == len(jobs):
                event_writer.write(
                    {
                        "event": "generation_progress",
                        "completed_trajectories": completed,
                        "total_trajectories": len(jobs),
                    }
                )

        event_writer.write(
            {
                "event": "generation_finish",
                "completed_trajectories": len(jobs),
                "training_approved_traces": training_approved_traces,
                "training_approved_rows": training_approved_rows,
            }
        )

    if family_sets["corpus_train"] & family_sets["internal_holdout"]:
        raise ValueError("family overlap detected after generation")
    message_overlap = (
        message_hashes["corpus_train"] & message_hashes["internal_holdout"]
    )
    assistant_overlap = (
        assistant_hashes["corpus_train"] & assistant_hashes["internal_holdout"]
    )
    if message_overlap:
        raise ValueError("exact message overlap detected across corpus splits")
    if training_approved_traces or training_approved_rows:
        raise ValueError("provisional generation unexpectedly approved data")

    generated_files = [
        storyworld_dir / "worlds.jsonl",
        encounters_path,
        train_path,
        eval_path,
        preference_train_path,
        preference_eval_path,
        events_path,
    ]
    validated_lines = {
        path.relative_to(output_dir).as_posix(): _validate_jsonl(path)
        for path in generated_files
    }
    expected_rows = {
        "encounters.jsonl": len(jobs),
        "datasets/player_train.jsonl": row_counts["corpus_train"]["total"],
        "datasets/player_eval.jsonl": row_counts["internal_holdout"]["total"],
        "datasets/preference_train.jsonl": preference_counts["corpus_train"][
            "total"
        ],
        "datasets/preference_eval.jsonl": preference_counts["internal_holdout"][
            "total"
        ],
    }
    for relative_path, expected in expected_rows.items():
        if validated_lines[relative_path] != expected:
            raise ValueError(f"{relative_path}: line-count validation failed")

    packed_gate = int(config["quantity_gates"]["minimum_provisional_packed_tokens"])
    assistant_gate = int(
        config["quantity_gates"]["minimum_provisional_assistant_tokens"]
    )
    full_campaign = limit is None
    metrics = {
        "schema_version": "storyworld_provisional_corpus_metrics_v1",
        "campaign_id": config["campaign_id"],
        "generation_scope": (
            "full_campaign" if full_campaign else f"deterministic_prefix_{len(jobs)}"
        ),
        "trajectories": {
            split: dict(sorted(counts.items()))
            for split, counts in sorted(trace_counts.items())
        },
        "sft_rows": {
            split: dict(sorted(counts.items()))
            for split, counts in sorted(row_counts.items())
        },
        "preference_rows": {
            split: dict(sorted(counts.items()))
            for split, counts in sorted(preference_counts.items())
        },
        "tokens": {
            key: value for key, value in sorted(token_counts.items())
        },
        "tokenizer": token_counter.description,
        "turns": {
            "minimum": min(turn_counts),
            "maximum": max(turn_counts),
            "total": sum(turn_counts),
        },
        "diversity": {
            "unique_trace_ids": len(trace_ids),
            "unique_record_ids": len(record_ids),
            "unique_message_sha256": {
                split: len(values)
                for split, values in sorted(message_hashes.items())
            },
            "unique_assistant_sha256": {
                split: len(values)
                for split, values in sorted(assistant_hashes.items())
            },
            "exact_message_overlap_across_splits": len(message_overlap),
            "exact_assistant_overlap_across_splits": len(assistant_overlap),
            "families_by_split": {
                split: sorted(values)
                for split, values in sorted(family_sets.items())
            },
            "worlds_by_split": {
                split: sorted(values)
                for split, values in sorted(world_sets.items())
            },
            "family_overlap_across_splits": sorted(
                family_sets["corpus_train"]
                & family_sets["internal_holdout"]
            ),
        },
        "release": {
            "training_approved_traces": training_approved_traces,
            "training_approved_rows": training_approved_rows,
            "human_review_complete": False,
            "scholar_review_complete": False,
            "prime_training_ready": False,
        },
        "quantity_gates": {
            "minimum_provisional_packed_tokens": packed_gate,
            "provisional_packed_tokens": token_counts["all"]["packed_tokens"],
            "provisional_packed_tokens_passed": (
                full_campaign
                and token_counts["all"]["packed_tokens"] >= packed_gate
            ),
            "minimum_provisional_assistant_tokens": assistant_gate,
            "provisional_assistant_tokens": token_counts["all"][
                "assistant_tokens"
            ],
            "provisional_assistant_tokens_passed": (
                full_campaign
                and token_counts["all"]["assistant_tokens"] >= assistant_gate
            ),
            "approved_conditioning_tokens": 0,
            "approved_conditioning_token_gate_passed": False,
        },
        "validation": {
            "jsonl_lines": validated_lines,
            "trace_schema_validation": "passed_during_generation",
            "engine_validation": "passed_during_generation",
            "sealed_evaluation_worlds_used": 0,
            "private_chain_of_thought_requested": False,
            "private_chain_of_thought_included": False,
        },
        "claim_boundary": config["claim_boundary"],
    }
    metrics_path = reports_dir / "metrics.json"
    write_json(metrics_path, metrics)

    summary = "\n".join(
        [
            "# Provisional local storyworld corpus",
            "",
            f"- Campaign: `{config['campaign_id']}`",
            f"- Multi-turn trajectories: {len(jobs):,}",
            f"- SFT rows: {sum(item['total'] for item in row_counts.values()):,}",
            f"- Preference rows: {sum(item['total'] for item in preference_counts.values()):,}",
            f"- Development-estimate packed tokens: {token_counts['all']['packed_tokens']:,}",
            f"- Development-estimate assistant tokens: {token_counts['all']['assistant_tokens']:,}",
            f"- Exact train/holdout message overlap: {len(message_overlap)}",
            f"- Family overlap: {len(family_sets['corpus_train'] & family_sets['internal_holdout'])}",
            "- Trace/schema/engine checks: passed",
            "- Training-approved rows: 0",
            "- Prime training ready: no; human and scholar review remain open",
            "",
            (
                "The quantity receipt measures newly generated structured trajectories "
                "and does not promote review-pending rows into a training release."
            ),
            "",
        ]
    )
    summary_path = reports_dir / "summary.md"
    summary_path.write_text(summary, encoding="utf-8", newline="\n")

    receipt_paths = [
        storyworld_dir / "world.json",
        storyworld_dir / "worlds.jsonl",
        encounters_path,
        train_path,
        eval_path,
        preference_train_path,
        preference_eval_path,
        events_path,
        metrics_path,
        summary_path,
    ]
    receipts = _artifact_receipts(output_dir, receipt_paths)
    tree_sha256 = sha256_json(receipts)
    manifest = {
        "schema_version": "storyworld_provisional_corpus_run_manifest_v1",
        "campaign_id": config["campaign_id"],
        "status": "generated_validated_provisional_not_training_release",
        "created_at": config["created_at"],
        "generation_scope": metrics["generation_scope"],
        "source_receipts": {
            "campaign_config": {
                "path": config_path.relative_to(REPO_ROOT).as_posix(),
                "sha256": sha256_file(config_path),
            },
            "package": {
                "path": package_path.relative_to(REPO_ROOT).as_posix(),
                "sha256": sha256_file(package_path),
            },
            "teacher_ensemble": {
                "path": ensemble_path.relative_to(REPO_ROOT).as_posix(),
                "sha256": sha256_file(ensemble_path),
            },
            "teacher": teacher.receipt(),
            "code": {
                "generator": {
                    "path": GENERATOR_PATH.relative_to(REPO_ROOT).as_posix(),
                    "sha256": sha256_file(GENERATOR_PATH),
                },
                "provisional_teacher": {
                    "path": TEACHER_MODULE_PATH.relative_to(REPO_ROOT).as_posix(),
                    "sha256": sha256_file(TEACHER_MODULE_PATH),
                },
                "trajectory_curriculum": {
                    "path": TRAJECTORY_MODULE_PATH.relative_to(
                        REPO_ROOT
                    ).as_posix(),
                    "sha256": sha256_file(TRAJECTORY_MODULE_PATH),
                },
                "storyworld_engine": {
                    "path": STORYWORLD_MODULE_PATH.relative_to(
                        REPO_ROOT
                    ).as_posix(),
                    "sha256": sha256_file(STORYWORLD_MODULE_PATH),
                },
                "trace_schema": {
                    "path": TRACE_SCHEMA_PATH.relative_to(REPO_ROOT).as_posix(),
                    "sha256": sha256_file(TRACE_SCHEMA_PATH),
                },
            },
        },
        "budgets": {
            "recursion": config["recursion_budget"],
            "resources": config["resource_budget"],
            "trajectories_executed": len(jobs),
        },
        "artifacts": receipts,
        "artifact_tree_sha256": tree_sha256,
        "metrics_path": metrics_path.relative_to(output_dir).as_posix(),
        "training_approved": False,
        "prime_training_ready": False,
        "claim_boundary": config["claim_boundary"],
    }
    write_json(output_dir / "run_manifest.json", manifest)
    print(json.dumps(manifest, indent=2))
    return output_dir


def main() -> int:
    args = parse_args()
    generate(args.config, args.output_dir, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
