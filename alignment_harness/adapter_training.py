"""Fail-closed adapter-spend planning and packed-curriculum audits."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from .storyworlds import read_json, sha256_file, sha256_json
from .trajectory_curriculum import read_jsonl, render_assistant_only_example


TRAINING_RECIPE_SCHEMA = "storyworld_adapter_training_recipe_v1"
TRAINING_PLAN_SCHEMA = "storyworld_adapter_training_plan_v1"


def validate_training_input_artifacts(
    input_artifacts: Sequence[dict[str, Any]],
    *,
    relative_to: Path,
) -> dict[str, dict[str, Any]]:
    """Validate release-manifest bindings and index every approved source row."""
    if not input_artifacts:
        raise ValueError("packed curriculum does not list its canonical input artifacts")
    source_rows: dict[str, dict[str, Any]] = {}
    validated_canonical_sources: set[Path] = set()
    for item in input_artifacts:
        if not item.get("sha256") or not item.get("source_manifest_sha256"):
            raise ValueError("packed input artifact lacks source-manifest provenance")
        artifact_path = Path(str(item.get("path", "")))
        source_manifest_path = Path(str(item.get("source_manifest_path", "")))
        if not artifact_path.is_absolute():
            artifact_path = relative_to / artifact_path
        if not source_manifest_path.is_absolute():
            source_manifest_path = relative_to / source_manifest_path
        artifact_path = artifact_path.resolve()
        source_manifest_path = source_manifest_path.resolve()
        if not artifact_path.is_file() or sha256_file(artifact_path) != item["sha256"]:
            raise ValueError("packed upstream input artifact is missing or drifted")
        if not source_manifest_path.is_file() or sha256_file(
            source_manifest_path
        ) != item["source_manifest_sha256"]:
            raise ValueError("packed upstream source manifest is missing or drifted")

        rows = read_jsonl(artifact_path)
        if len(rows) != int(item.get("rows", -1)):
            raise ValueError("packed upstream input artifact row count drifted")
        source_manifest = read_json(source_manifest_path)
        kind = str(item.get("kind", ""))
        if kind == "canonical_training_view":
            if source_manifest.get("schema_version") != (
                "storyworld_canonical_release_manifest_v1"
            ) or source_manifest.get("release_status") != "review_approved":
                raise ValueError("canonical training input is not a reviewed release")
            view = str(item.get("view", ""))
            binding = source_manifest.get("views", {}).get(view, {})
            if (
                binding.get("sha256") != item["sha256"]
                or int(binding.get("rows", -1)) != len(rows)
                or Path(str(binding.get("path", ""))).name != artifact_path.name
            ):
                raise ValueError("canonical release manifest does not bind its training view")
            if source_manifest_path not in validated_canonical_sources:
                derivation_module = Path(__file__).resolve().parent / "trajectory_curriculum.py"
                if source_manifest.get("derivation_module_sha256") != sha256_file(
                    derivation_module
                ):
                    raise ValueError("canonical derivation module drifted after release")
                if source_manifest.get("source_trace_provenance_complete") is not True:
                    raise ValueError("canonical release lacks complete trace provenance")
                trace_artifacts = source_manifest.get("source_trace_artifacts", [])
                if not isinstance(trace_artifacts, list) or not trace_artifacts:
                    raise ValueError("canonical release lists no approved trace artifacts")
                trace_hashes = []
                for trace_item in trace_artifacts:
                    if trace_item.get("kind") != "approved_harvest_traces":
                        raise ValueError("canonical release has an unexpected trace artifact")
                    trace_path = Path(str(trace_item.get("path", "")))
                    trace_manifest_path = Path(
                        str(trace_item.get("source_manifest_path", ""))
                    )
                    if not trace_path.is_absolute():
                        trace_path = source_manifest_path.parent / trace_path
                    if not trace_manifest_path.is_absolute():
                        trace_manifest_path = (
                            source_manifest_path.parent / trace_manifest_path
                        )
                    trace_path = trace_path.resolve()
                    trace_manifest_path = trace_manifest_path.resolve()
                    if (
                        not trace_path.is_file()
                        or sha256_file(trace_path) != trace_item.get("sha256")
                        or not trace_manifest_path.is_file()
                        or sha256_file(trace_manifest_path)
                        != trace_item.get("source_manifest_sha256")
                    ):
                        raise ValueError("canonical approved-trace artifact is missing or drifted")
                    trace_rows = read_jsonl(trace_path)
                    if len(trace_rows) != int(trace_item.get("rows", -1)):
                        raise ValueError("canonical approved-trace row count drifted")
                    trace_release = read_json(trace_manifest_path)
                    release_builder = (
                        Path(__file__).resolve().parent.parent
                        / "scripts"
                        / "prepare_storyworld_harvest_release.py"
                    )
                    if (
                        trace_release.get("schema_version")
                        != "storyworld_harvest_approved_release_manifest_v1"
                        or trace_release.get("status")
                        != "approved_real_teacher_traces_for_canonical_derivation"
                        or trace_release.get("approved_traces_sha256")
                        != trace_item.get("sha256")
                        or int(trace_release.get("training_approved_traces", -1))
                        != len(trace_rows)
                        or trace_release.get("trace_content_sha256")
                        != [sha256_json(trace) for trace in trace_rows]
                        or trace_release.get("job_evidence_sha256")
                        != sha256_json(trace_release.get("job_evidence", []))
                        or trace_release.get("release_builder_sha256")
                        != sha256_file(release_builder)
                        or len(trace_release.get("job_evidence", []))
                        != len(trace_rows)
                        or trace_release.get("passed") is not True
                    ):
                        raise ValueError("canonical harvest release binding drifted")
                    trace_hashes.extend(sha256_json(trace) for trace in trace_rows)
                if sorted(trace_hashes) != sorted(
                    map(str, source_manifest.get("source_trace_sha256", []))
                ):
                    raise ValueError("canonical manifest trace-content set drifted")
                validated_canonical_sources.add(source_manifest_path)
        elif kind == "approved_extra_rows":
            if source_manifest.get("schema_version") not in {
                "storyworld_support_approved_release_manifest_v1",
                "storyworld_recovered_extras_approved_release_v1",
            }:
                raise ValueError("unexpected approved-extra release manifest schema")
            if (
                source_manifest.get("approved_rows_sha256") != item["sha256"]
                or int(source_manifest.get("training_approved_rows", -1)) != len(rows)
                or source_manifest.get("passed") is not True
            ):
                raise ValueError("approved-extra release manifest does not bind every row")
        else:
            raise ValueError(f"unexpected packed input artifact kind: {kind}")

        for row in rows:
            record_id = str(row.get("record_id", ""))
            if not record_id or record_id in source_rows:
                raise ValueError("packed upstream inputs contain missing/duplicate record IDs")
            if row.get("source_split") != "train":
                raise ValueError("packed upstream input contains a non-train row")
            if not row.get("training_eligible") or not row.get("training_approved"):
                raise ValueError("packed upstream input contains an unapproved row")
            record_base = {
                key: value for key, value in row.items() if key != "record_sha256"
            }
            if row.get("record_sha256") != sha256_json(record_base):
                raise ValueError(f"packed upstream row checksum mismatch: {record_id}")
            source_rows[record_id] = {
                "row_sha256": sha256_json(row),
                "artifact_sha256": item["sha256"],
                "artifact_kind": kind,
            }
    return source_rows


def fingerprint_local_model_dir(path: Path) -> dict[str, Any]:
    """Hash configuration and every local model weight shard."""
    path = Path(path).resolve()
    if not path.is_dir():
        raise ValueError("frozen base model path must be a local directory")
    metadata_names = {
        "config.json",
        "generation_config.json",
        "model.safetensors.index.json",
        "pytorch_model.bin.index.json",
    }
    weight_suffixes = {".safetensors", ".bin"}
    files = []
    weight_files = 0
    for candidate in sorted(item for item in path.rglob("*") if item.is_file()):
        if candidate.name not in metadata_names and candidate.suffix.lower() not in weight_suffixes:
            continue
        if candidate.suffix.lower() in weight_suffixes:
            weight_files += 1
        files.append(
            {
                "path": candidate.relative_to(path).as_posix(),
                "bytes": candidate.stat().st_size,
                "sha256": sha256_file(candidate),
            }
        )
    if not (path / "config.json").is_file():
        raise ValueError("frozen base model is missing config.json")
    if weight_files == 0:
        raise ValueError("frozen base model contains no .safetensors or .bin weights")
    return {
        "model_artifact_set_sha256": sha256_json(files),
        "model_artifact_files": files,
        "weight_files": weight_files,
        "total_hashed_bytes": sum(int(item["bytes"]) for item in files),
    }


def verify_local_model_fingerprint(path: Path, receipt: dict[str, Any]) -> None:
    observed = fingerprint_local_model_dir(path)
    if observed["model_artifact_set_sha256"] != receipt.get(
        "model_artifact_set_sha256"
    ):
        raise ValueError("local base model artifacts drifted after freeze")


def validate_adapter_training_recipe(
    recipe: dict[str, Any], token_recipe: dict[str, Any]
) -> dict[str, Any]:
    if recipe.get("schema_version") != TRAINING_RECIPE_SCHEMA:
        raise ValueError("unexpected adapter training recipe schema")
    if recipe.get("status") != "frozen_protocol_not_spend_authorization":
        raise ValueError("adapter training recipe must remain a no-spend protocol")
    arms = list(map(str, recipe.get("arms", [])))
    if arms != list(map(str, token_recipe["arms"])):
        raise ValueError("adapter training arms drifted from the token recipe")
    checkpoints = list(map(int, recipe.get("checkpoint_tokens", [])))
    if checkpoints != list(map(int, token_recipe["checkpoints"])):
        raise ValueError("adapter checkpoints drifted from the token recipe")
    if recipe.get("dose_design") != "single_continuous_ordered_prefix_run_per_arm":
        raise ValueError("adapter dose design must use one continuous prefix run per arm")
    if recipe.get("dataset_passes") != 1:
        raise ValueError("adapter dose interpretation requires exactly one dataset pass")
    if recipe.get("shuffle") is not False:
        raise ValueError("adapter dose interpretation requires shuffle=false")
    if recipe.get("assistant_only_loss") is not True:
        raise ValueError("adapter training must mask non-assistant tokens")
    if recipe.get("truncation_allowed") is not False:
        raise ValueError("adapter training cannot truncate frozen packed rows")
    if int(recipe.get("max_sequence_tokens", 0)) <= 0:
        raise ValueError("adapter max sequence tokens must be positive")
    if recipe.get("checkpoint_boundary_policy") != (
        "flush accumulated gradients after the row crossing each frozen token boundary, then save"
    ):
        raise ValueError("adapter checkpoint boundary policy drifted")
    optimizer = recipe.get("optimizer", {})
    if float(optimizer.get("learning_rate", 0)) <= 0:
        raise ValueError("adapter learning rate must be positive")
    if int(optimizer.get("gradient_accumulation_rows", 0)) <= 0:
        raise ValueError("gradient accumulation rows must be positive")
    if not 0 <= float(optimizer.get("warmup_ratio", -1)) < 1:
        raise ValueError("adapter warmup ratio must be in [0, 1)")
    if optimizer.get("gradient_normalization") != (
        "loss_sum_divided_by_accumulated_supervised_tokens"
    ):
        raise ValueError("adapter gradients must be normalized by supervised tokens")
    lora = recipe.get("lora", {})
    if int(lora.get("rank", 0)) <= 0 or int(lora.get("alpha", 0)) <= 0:
        raise ValueError("LoRA rank and alpha must be positive")
    targets = lora.get("target_module_suffixes", [])
    if not isinstance(targets, list) or not targets or len(set(map(str, targets))) != len(targets):
        raise ValueError("LoRA target module suffixes must be unique and nonempty")
    quantization = recipe.get("quantization", {})
    if quantization.get("mode") != "qlora_4bit_nf4":
        raise ValueError("v1 adapter recipe requires 4-bit NF4 QLoRA")
    runtime = recipe.get("runtime", {})
    if runtime.get("single_process_single_cuda_device") is not True:
        raise ValueError("v1 exact-dose training requires one CUDA process")
    if runtime.get("local_files_only") is not True or runtime.get("trust_remote_code") is not False:
        raise ValueError("v1 adapter base must be local-only without remote code")
    gates = recipe.get("release_gates", {})
    required_true = {
        "review_approved_curriculum_required",
        "exact_frozen_huggingface_tokenizer_required",
        "frozen_local_base_model_required",
        "explicit_training_spend_authorization_required",
        "development_only_checkpoint_selection",
        "sealed_evaluation_open_once_after_recipe_freeze",
    }
    if any(gates.get(key) is not True for key in required_true):
        raise ValueError("adapter training release gates drifted")
    if gates.get("provisional_rows_allowed") is not False:
        raise ValueError("adapter training cannot consume provisional rows")
    return {
        "schema_version": "storyworld_adapter_training_recipe_validation_v1",
        "arms": arms,
        "checkpoint_tokens": checkpoints,
        "dose_design": recipe["dose_design"],
        "assistant_only_loss": True,
        "shuffle": False,
        "dataset_passes": 1,
        "passed": True,
    }


def audit_packed_curriculum_for_training(
    packing_manifest_path: Path,
    training_recipe: dict[str, Any],
    token_recipe: dict[str, Any],
) -> dict[str, Any]:
    """Verify every packed prefix/hash/token claim before model construction."""
    packing_manifest_path = Path(packing_manifest_path).resolve()
    manifest = read_json(packing_manifest_path)
    validate_adapter_training_recipe(training_recipe, token_recipe)
    if manifest.get("schema_version") != "storyworld_packed_curriculum_manifest_v1":
        raise ValueError("unexpected packed curriculum manifest schema")
    if manifest.get("release_status") != "review_approved":
        raise ValueError("adapter training requires a review-approved packed curriculum")
    if manifest.get("source_provenance_complete") is not True:
        raise ValueError("adapter training requires complete hash-bound pack input provenance")
    input_artifacts = manifest.get("input_artifacts", [])
    if not isinstance(input_artifacts, list) or not input_artifacts:
        raise ValueError("packed curriculum does not list its canonical input artifacts")
    source_rows = validate_training_input_artifacts(
        input_artifacts,
        relative_to=packing_manifest_path.parent,
    )
    tokenizer = manifest.get("tokenizer", {})
    if tokenizer.get("backend") != "huggingface_local" or not tokenizer.get(
        "tokenizer_artifact_set_sha256"
    ):
        raise ValueError("adapter training requires an exact frozen local tokenizer receipt")
    if int(manifest.get("target_tokens_per_arm", 0)) != int(
        token_recipe["target_tokens_per_arm"]
    ):
        raise ValueError("packed curriculum target drifted from the token recipe")
    if int(manifest.get("minimum_assistant_tokens_per_arm", 0)) != int(
        token_recipe["minimum_assistant_tokens_per_arm"]
    ):
        raise ValueError("packed assistant minimum drifted from the token recipe")
    expected_arms = list(map(str, training_recipe["arms"]))
    if set(manifest.get("arms", {})) != set(expected_arms):
        raise ValueError("packed curriculum arm set drifted")

    arm_receipts: dict[str, Any] = {}
    for arm in expected_arms:
        arm_manifest = manifest["arms"][arm]
        arm_path = (packing_manifest_path.parent / str(arm_manifest["path"])).resolve()
        if not arm_path.is_file() or sha256_file(arm_path) != arm_manifest.get("sha256"):
            raise ValueError(f"packed arm file is missing or drifted: {arm}")
        rows = read_jsonl(arm_path)
        if len(rows) != int(arm_manifest["rows"]):
            raise ValueError(f"packed arm row count mismatch: {arm}")
        record_ids: set[str] = set()
        actual_tokens = 0
        actual_assistant = 0
        tokens_by_slice: dict[str, int] = {}
        assistant_by_slice: dict[str, int] = {}
        for row in rows:
            if row.get("arm") != arm:
                raise ValueError(f"packed row reached the wrong arm file: {arm}")
            if row.get("source_split") == "evaluation":
                raise ValueError("sealed evaluation row reached adapter training")
            if not row.get("training_eligible") or not row.get("training_approved"):
                raise ValueError(f"packed arm contains provisional or ineligible row: {arm}")
            record_id = str(row.get("record_id", ""))
            if not record_id or record_id in record_ids:
                raise ValueError(f"packed arm contains missing/duplicate record ID: {arm}")
            record_ids.add(record_id)
            source_receipt = source_rows.get(record_id)
            packed_source_row = {
                key: value for key, value in row.items() if key != "token_counts"
            }
            if source_receipt is None or sha256_json(packed_source_row) != source_receipt[
                "row_sha256"
            ]:
                raise ValueError(
                    f"packed row is absent from or drifted against its approved source: {record_id}"
                )
            counts = row.get("token_counts", {})
            packed = int(counts.get("packed", 0))
            assistant = int(counts.get("loss_bearing_assistant", 0))
            if packed <= 0 or assistant <= 0 or assistant > packed:
                raise ValueError(f"packed row has invalid token counts: {record_id}")
            slice_id = str(row["slice"])
            actual_tokens += packed
            actual_assistant += assistant
            tokens_by_slice[slice_id] = tokens_by_slice.get(slice_id, 0) + packed
            assistant_by_slice[slice_id] = assistant_by_slice.get(slice_id, 0) + assistant
        if actual_tokens != int(arm_manifest["actual_tokens"]):
            raise ValueError(f"packed token total mismatch: {arm}")
        if actual_assistant != int(arm_manifest["actual_assistant_tokens"]):
            raise ValueError(f"packed assistant-token total mismatch: {arm}")
        if actual_tokens < int(token_recipe["target_tokens_per_arm"]):
            raise ValueError(f"packed arm misses its token target: {arm}")
        if actual_assistant < int(token_recipe["minimum_assistant_tokens_per_arm"]):
            raise ValueError(f"packed arm misses its assistant-token minimum: {arm}")
        for slice_id, target in token_recipe["slice_tokens"].items():
            if tokens_by_slice.get(slice_id, 0) < int(target):
                raise ValueError(f"packed arm misses {slice_id} target: {arm}")
            if assistant_by_slice.get(slice_id, 0) < int(
                token_recipe["minimum_assistant_tokens_by_slice"][slice_id]
            ):
                raise ValueError(f"packed arm misses {slice_id} assistant minimum: {arm}")
            slice_manifest = arm_manifest.get("slices", {}).get(slice_id, {})
            if (
                int(slice_manifest.get("target_tokens", -1)) != int(target)
                or int(slice_manifest.get("actual_tokens", -1))
                != tokens_by_slice.get(slice_id, 0)
                or int(slice_manifest.get("minimum_assistant_tokens", -1))
                != int(token_recipe["minimum_assistant_tokens_by_slice"][slice_id])
                or int(slice_manifest.get("assistant_tokens", -1))
                != assistant_by_slice.get(slice_id, 0)
            ):
                raise ValueError(f"packed slice receipt drifted: {arm}/{slice_id}")

        checkpoints = arm_manifest.get("checkpoints", [])
        if [int(item["target_tokens"]) for item in checkpoints] != list(
            map(int, training_recipe["checkpoint_tokens"])
        ):
            raise ValueError(f"packed checkpoint set drifted: {arm}")
        previous_row = 0
        previous_actual = 0
        for checkpoint in checkpoints:
            reached = int(checkpoint["reached_after_row"])
            actual = int(checkpoint["actual_cumulative_tokens"])
            if not previous_row < reached <= len(rows) or actual <= previous_actual:
                raise ValueError(f"packed checkpoint boundaries are not monotonic: {arm}")
            if sha256_json(rows[:reached]) != checkpoint.get("prefix_sha256"):
                raise ValueError(f"packed checkpoint prefix hash mismatch: {arm}")
            recomputed_tokens = sum(
                int(row["token_counts"]["packed"]) for row in rows[:reached]
            )
            recomputed_assistant = sum(
                int(row["token_counts"]["loss_bearing_assistant"])
                for row in rows[:reached]
            )
            if recomputed_tokens != actual or recomputed_assistant != int(
                checkpoint["actual_cumulative_assistant_tokens"]
            ):
                raise ValueError(f"packed checkpoint cumulative totals mismatch: {arm}")
            expected_checkpoint_slices: dict[str, tuple[int, int]] = {}
            for prefix_row in rows[:reached]:
                prefix_slice = str(prefix_row["slice"])
                packed_count, assistant_count = expected_checkpoint_slices.get(
                    prefix_slice, (0, 0)
                )
                expected_checkpoint_slices[prefix_slice] = (
                    packed_count + int(prefix_row["token_counts"]["packed"]),
                    assistant_count
                    + int(prefix_row["token_counts"]["loss_bearing_assistant"]),
                )
            for slice_id, target in token_recipe["slice_tokens"].items():
                checkpoint_slice = checkpoint.get("slices", {}).get(slice_id, {})
                observed_slice = expected_checkpoint_slices.get(slice_id, (0, 0))
                scaled_target = (
                    int(checkpoint["target_tokens"]) * int(target)
                    // int(token_recipe["target_tokens_per_arm"])
                )
                scaled_assistant = (
                    int(checkpoint["target_tokens"])
                    * int(token_recipe["minimum_assistant_tokens_by_slice"][slice_id])
                    // int(token_recipe["target_tokens_per_arm"])
                )
                if (
                    int(checkpoint_slice.get("scaled_target_tokens", -1))
                    != scaled_target
                    or int(checkpoint_slice.get("actual_tokens", -1))
                    != observed_slice[0]
                    or int(
                        checkpoint_slice.get(
                            "scaled_minimum_assistant_tokens", -1
                        )
                    )
                    != scaled_assistant
                    or int(checkpoint_slice.get("actual_assistant_tokens", -1))
                    != observed_slice[1]
                ):
                    raise ValueError(
                        f"packed checkpoint slice receipt drifted: {arm}/{slice_id}"
                    )
            previous_row, previous_actual = reached, actual
        if not checkpoints or int(checkpoints[-1]["reached_after_row"]) != len(rows):
            raise ValueError(f"final packed checkpoint does not cover the complete stream: {arm}")
        if checkpoints[-1].get("prefix_sha256") != sha256_json(rows):
            raise ValueError(f"final packed checkpoint does not bind the complete stream: {arm}")
        arm_receipts[arm] = {
            "path": arm_path.name,
            "sha256": sha256_file(arm_path),
            "rows": len(rows),
            "actual_tokens": actual_tokens,
            "actual_assistant_tokens": actual_assistant,
            "checkpoint_prefixes": [
                {
                    "target_tokens": int(item["target_tokens"]),
                    "reached_after_row": int(item["reached_after_row"]),
                    "actual_cumulative_tokens": int(item["actual_cumulative_tokens"]),
                    "prefix_sha256": item["prefix_sha256"],
                }
                for item in checkpoints
            ],
        }
    return {
        "schema_version": "storyworld_packed_curriculum_training_audit_v1",
        "packing_manifest_sha256": sha256_file(packing_manifest_path),
        "tokenizer": tokenizer,
        "arms": arm_receipts,
        "sealed_evaluation_rows": 0,
        "passed": True,
    }


def build_adapter_training_plan(
    package_path: Path,
    token_recipe_path: Path,
    training_recipe_path: Path,
) -> dict[str, Any]:
    package_path = Path(package_path).resolve()
    token_recipe_path = Path(token_recipe_path).resolve()
    training_recipe_path = Path(training_recipe_path).resolve()
    package = read_json(package_path)
    token_recipe = read_json(token_recipe_path)
    training_recipe = read_json(training_recipe_path)
    receipt = validate_adapter_training_recipe(training_recipe, token_recipe)
    jobs = []
    for arm in training_recipe["arms"]:
        jobs.append(
            {
                "job_id": f"adapter-curve-{arm}",
                "arm": arm,
                "dose_design": training_recipe["dose_design"],
                "checkpoint_tokens": training_recipe["checkpoint_tokens"],
                "dataset_passes": 1,
                "shuffle": False,
                "assistant_only_loss": True,
                "execution_eligible": False,
            }
        )
    return {
        "schema_version": TRAINING_PLAN_SCHEMA,
        "plan_id": "storyworld_four_arm_adapter_spend_curve_v1",
        "status": "awaiting_reviewed_pack_base_freeze_and_spend_authorization",
        "package_id": package["package_id"],
        "package_sha256": sha256_file(package_path),
        "token_recipe_sha256": sha256_file(token_recipe_path),
        "training_recipe_sha256": sha256_file(training_recipe_path),
        "training_recipe_validation": receipt,
        "jobs": jobs,
        "adapter_checkpoints": len(jobs) * len(training_recipe["checkpoint_tokens"]),
        "development_evaluations": len(jobs) * len(training_recipe["checkpoint_tokens"]),
        "sealed_evaluation_openings": 1,
        "automatic_spend_authorization": False,
        "claim_boundary": (
            "This freezes the matched adapter-spend design only. It is not evidence of a "
            "packed corpus, frozen base, trained adapter, development score, or spend authorization."
        ),
        "passed": True,
    }
