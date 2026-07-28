"""Frozen evaluation adapters for the 195M constitutional HRM checkpoint."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from tokenizers import Tokenizer

from alignment_harness.constitutional_hrm import PROHIBITION_IDS, Scenario
from alignment_harness.constitutional_hrm_v2 import IGNORE_LABEL_ID, encode_example

PROMPT_CONDITIONS = (
    "constitution_metta_full",
    "constitution_hash_only",
    "constitution_removed",
)
MORAL_DIMENSION_ORDER = (
    "justice_without_scapegoat",
    "evidence_bounded_reason",
    "truth_under_concealment",
    "accountable_choice",
    "entrusted_stewardship",
    "repair_preservation",
)
FRAME_ORDER = ("neutral", "constitutional", "jinn", "beast")
ACTION_LINE = re.compile(r"(?m)^-\s+([A-Za-z0-9_-]+):\s+")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(f"{path}:{line_number} is not an object")
            rows.append(value)
    return rows


def native_balanced_indices(total: int, max_examples: int | None) -> np.ndarray:
    condition_count = len(PROMPT_CONDITIONS)
    if total % condition_count:
        raise ValueError("native constitutional rows are not condition-balanced")
    per_condition = total // condition_count
    if max_examples is None or max_examples >= total:
        return np.arange(total, dtype=np.int64)
    take = min(per_condition, max_examples // condition_count)
    if take < 1:
        raise ValueError(
            "max-examples-per-suite must be at least 3 for balanced native evaluation"
        )
    return np.concatenate(
        [
            np.arange(offset, offset + take, dtype=np.int64)
            for offset in range(0, total, per_condition)
        ]
    )


def native_metadata(
    *,
    groups_path: Path,
    selected_indices: np.ndarray,
    labels: np.ndarray,
    decision_token_ids: Sequence[int],
) -> list[dict[str, Any]]:
    groups = read_jsonl(groups_path)
    rows_per_condition = len(groups) * 8
    total = rows_per_condition * len(PROMPT_CONDITIONS)
    if total == 0:
        raise ValueError("native constitutional group list is empty")
    decision_lookup = {
        token_id: index for index, token_id in enumerate(decision_token_ids)
    }
    if any(index < 0 or index >= total for index in selected_indices):
        raise ValueError("native constitutional selection is out of range")
    metadata: list[dict[str, Any]] = []
    for output_index, source_index in enumerate(selected_indices.tolist()):
        condition_index, condition_row = divmod(source_index, rows_per_condition)
        group_index, augmentation = divmod(condition_row, 8)
        surface_variant, swapped = divmod(augmentation, 2)
        true_decision = decision_lookup.get(int(labels[output_index, 0]))
        if true_decision not in (0, 1):
            raise ValueError("native target is not decision A or B")
        group = groups[group_index]
        structural_group = str(group["group_id"])
        target_action = "A" if true_decision == 0 else "B"
        metadata.append(
            {
                "suite": "constitutional_native",
                "task_id": (
                    f"{structural_group}:surface_{surface_variant}:swapped_{swapped}"
                ),
                "group_id": f"{structural_group}:surface_{surface_variant}",
                "structural_group_id": structural_group,
                "family_id": str(group.get("family", "")),
                "condition": PROMPT_CONDITIONS[condition_index],
                "surface_variant": surface_variant,
                "orientation": "swapped" if swapped else "canonical",
                "action_order": ["A", "B"],
                "target_action_id": target_action,
                "acceptable_action_ids": [target_action],
                "split": "validation",
            }
        )
    if len(metadata) != len(selected_indices):
        raise AssertionError("native metadata row count drift")
    return metadata


def _control_id(tokenizer: Tokenizer, token: str) -> int:
    value = tokenizer.token_to_id(token)
    if value is None:
        raise ValueError(f"tokenizer is missing {token}")
    return int(value)


def decision_token_id(tokenizer: Tokenizer, index: int) -> int:
    if index not in range(4):
        raise ValueError(f"decision index must be in [0, 3], got {index}")
    return _control_id(tokenizer, f"<|decision:{index}|>")


def encode_raw_text(
    tokenizer: Tokenizer,
    text: str,
    *,
    seq_len: int = 512,
    allow_truncation: bool = True,
    head_tokens: int = 128,
) -> tuple[np.ndarray, dict[str, Any]]:
    token_ids = tokenizer.encode(text).ids
    original_tokens = len(token_ids)
    available = seq_len - 2
    truncated = original_tokens > available
    if truncated and not allow_truncation:
        raise ValueError(f"raw text has {original_tokens} tokens; budget is {available}")
    if truncated:
        tail_tokens = available - head_tokens
        if head_tokens < 1 or tail_tokens < 1:
            raise ValueError("invalid head/tail truncation allocation")
        token_ids = [*token_ids[:head_tokens], *token_ids[-tail_tokens:]]
    input_ids = [
        _control_id(tokenizer, "<|bos|>"),
        *token_ids,
        _control_id(tokenizer, "<|eos|>"),
    ]
    input_ids.extend(
        [_control_id(tokenizer, "<|pad|>")] * (seq_len - len(input_ids))
    )
    return np.asarray(input_ids, dtype=np.int32), {
        "original_tokens": original_tokens,
        "encoded_tokens": len(token_ids),
        "truncated": truncated,
        "truncation": "head_tail" if truncated else "none",
    }


def decision_label(tokenizer: Tokenizer, index: int, seq_len: int = 512) -> np.ndarray:
    labels = np.full((seq_len,), IGNORE_LABEL_ID, dtype=np.int32)
    labels[0] = decision_token_id(tokenizer, index)
    return labels


def token_sequence_label(
    tokenizer: Tokenizer, text: str, *, seq_len: int = 512
) -> tuple[np.ndarray, int]:
    ids = tokenizer.encode(text).ids
    ids.append(_control_id(tokenizer, "<|eos|>"))
    if len(ids) > seq_len:
        raise ValueError(f"target has {len(ids)} tokens; budget is {seq_len}")
    labels = np.full((seq_len,), IGNORE_LABEL_ID, dtype=np.int32)
    labels[: len(ids)] = np.asarray(ids, dtype=np.int32)
    return labels, len(ids)


def _messages_text(messages: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    system_parts = [
        str(message.get("content", ""))
        for message in messages
        if message.get("role") == "system"
    ]
    user_parts = [
        str(message.get("content", ""))
        for message in messages
        if message.get("role") == "user"
    ]
    return "\n".join(system_parts), "\n".join(user_parts)


def render_action_task(task: Mapping[str, Any]) -> tuple[str, list[str]]:
    action_scores = task.get("action_scores")
    if not isinstance(action_scores, Mapping) or not action_scores:
        raise ValueError("action task has no action_scores object")
    prompt = str(task.get("prompt", ""))
    action_order = ACTION_LINE.findall(prompt)
    if set(action_order) != set(map(str, action_scores)):
        action_order = sorted(map(str, action_scores))
        action_lines = [
            f"- {action_id}: {action_scores[action_id].get('text', '')}"
            for action_id in action_order
        ]
        prompt = f"{prompt}\n\nAvailable actions:\n" + "\n".join(action_lines)
    facts = task.get("visible_facts", [])
    if facts and "Visible facts:" not in prompt:
        fact_lines = [
            f"- {fact.get('id', '')}: {fact.get('text', '')}"
            for fact in facts
            if isinstance(fact, Mapping)
        ]
        prompt = f"{prompt}\n\nVisible facts:\n" + "\n".join(fact_lines)
    text = f"{task.get('system_prompt', '')}\n\n{prompt}".strip()
    return text, action_order


def build_raw_action_examples(
    *,
    tasks: Sequence[Mapping[str, Any]],
    tokenizer: Tokenizer,
    prompts: Mapping[str, str],
    suite: str,
    target_field: str,
    conditions: Sequence[str] = PROMPT_CONDITIONS,
    allowed_splits: set[str] | None = None,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    examples: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    for task in tasks:
        split = str(task.get("split", ""))
        if allowed_splits is not None and split not in allowed_splits:
            excluded[f"split:{split or 'missing'}"] += 1
            continue
        try:
            task_text, action_order = render_action_task(task)
        except ValueError:
            excluded["malformed_action_task"] += 1
            continue
        target = str(task.get(target_field, ""))
        if target not in action_order:
            excluded["target_not_in_action_order"] += 1
            continue
        if len(action_order) > 4:
            excluded["more_than_four_actions"] += 1
            continue
        target_index = action_order.index(target)
        for condition in conditions:
            condition_prompt = prompts.get(condition, "")
            text = f"{condition_prompt}\n\nEvaluation item:\n{task_text}".strip()
            input_ids, token_audit = encode_raw_text(tokenizer, text)
            examples.append(
                {
                    "input_ids": input_ids,
                    "labels": decision_label(tokenizer, target_index),
                    "metadata": {
                        "suite": suite,
                        "task_id": str(task.get("task_id", task.get("id", ""))),
                        "family_id": str(task.get("family_id", "")),
                        "split": split,
                        "condition": condition,
                        "action_order": action_order,
                        "target_action_id": target,
                        "acceptable_action_ids": [target],
                        "token_audit": token_audit,
                    },
                }
            )
    return examples, excluded


def build_storyworld_raw_examples(
    *,
    public_rows: Sequence[Mapping[str, Any]],
    key_rows: Sequence[Mapping[str, Any]],
    tokenizer: Tokenizer,
    prompts: Mapping[str, str],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    public = {str(row["item_id"]): row for row in public_rows}
    examples: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    for key in key_rows:
        if key.get("metric") != "frame_robust_policy_accuracy":
            excluded[f"metric:{key.get('metric', 'missing')}"] += 1
            continue
        item_id = str(key["item_id"])
        item = public.get(item_id)
        if item is None:
            excluded["missing_public_item"] += 1
            continue
        system, user = _messages_text(item.get("messages", []))
        try:
            payload = json.loads(user)
        except json.JSONDecodeError:
            excluded["user_payload_not_json"] += 1
            continue
        action_order = [
            str(action["action_id"]) for action in payload.get("legal_actions", [])
        ]
        acceptable = list(
            map(str, key.get("target", {}).get("acceptable_action_ids", []))
        )
        if (
            not action_order
            or not acceptable
            or not set(acceptable).issubset(action_order)
            or len(action_order) > 4
        ):
            excluded["invalid_action_or_target_set"] += 1
            continue
        canonical_target = acceptable[0]
        target_index = action_order.index(canonical_target)
        for condition in PROMPT_CONDITIONS:
            text = (
                f"{prompts[condition]}\n\nEvaluation item:\n{system}\n\n{user}"
            )
            input_ids, token_audit = encode_raw_text(tokenizer, text)
            examples.append(
                {
                    "input_ids": input_ids,
                    "labels": decision_label(tokenizer, target_index),
                    "metadata": {
                        "suite": "storyworld_raw_policy",
                        "task_id": item_id,
                        "family_id": str(item.get("family_id", "")),
                        "world_id": str(item.get("world_id", "")),
                        "split": "development",
                        "condition": condition,
                        "action_order": action_order,
                        "target_action_id": canonical_target,
                        "acceptable_action_ids": acceptable,
                        "token_audit": token_audit,
                    },
                }
            )
    return examples, excluded


def build_storyworld_text_examples(
    *,
    public_rows: Sequence[Mapping[str, Any]],
    key_rows: Sequence[Mapping[str, Any]],
    tokenizer: Tokenizer,
    removed_prompt: str,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    public = {str(row["item_id"]): row for row in public_rows}
    examples: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    for key in key_rows:
        item_id = str(key.get("item_id", ""))
        item = public.get(item_id)
        if item is None:
            excluded["missing_public_item"] += 1
            continue
        target = key.get("target")
        if not isinstance(target, Mapping):
            excluded["target_not_object"] += 1
            continue
        target_text = json.dumps(
            target, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        try:
            labels, target_tokens = token_sequence_label(tokenizer, target_text)
        except ValueError:
            excluded["target_over_budget"] += 1
            continue
        system, user = _messages_text(item.get("messages", []))
        for condition, prefix in (
            ("no_prompt", ""),
            ("constitution_removed", removed_prompt),
        ):
            input_ids, token_audit = encode_raw_text(
                tokenizer,
                f"{prefix}\n\n{system}\n\n{user}".strip(),
                allow_truncation=True,
            )
            examples.append(
                {
                    "input_ids": input_ids,
                    "labels": labels.copy(),
                    "metadata": {
                        "suite": "storyworld_full_text_transduction",
                        "task_id": item_id,
                        "family_id": str(item.get("family_id", "")),
                        "world_id": str(item.get("world_id", "")),
                        "split": "development",
                        "condition": condition,
                        "metric": str(key.get("metric", "")),
                        "target_text": target_text,
                        "target_tokens": target_tokens,
                        "token_audit": token_audit,
                    },
                }
            )
    return examples, excluded


def build_text_replay_examples(
    *,
    tasks: Sequence[Mapping[str, Any]],
    tokenizer: Tokenizer,
    prompts: Mapping[str, str],
    suite: str,
    target_field: str,
    conditions: Sequence[str] = PROMPT_CONDITIONS,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    examples: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    for task in tasks:
        target_text = str(task.get(target_field, ""))
        if not target_text:
            excluded["missing_target"] += 1
            continue
        try:
            labels, target_tokens = token_sequence_label(tokenizer, target_text)
        except ValueError:
            excluded["target_over_budget"] += 1
            continue
        task_text = (
            f"{task.get('system_prompt', '')}\n\n{task.get('prompt', '')}"
        ).strip()
        for condition in conditions:
            input_ids, token_audit = encode_raw_text(
                tokenizer,
                f"{prompts.get(condition, '')}\n\n{task_text}".strip(),
                allow_truncation=True,
            )
            examples.append(
                {
                    "input_ids": input_ids,
                    "labels": labels.copy(),
                    "metadata": {
                        "suite": suite,
                        "task_id": str(task.get("task_id", "")),
                        "family_id": str(
                            task.get("family_id", task.get("topic_id", ""))
                        ),
                        "split": str(task.get("split", "")),
                        "condition": condition,
                        "target_text": target_text,
                        "target_tokens": target_tokens,
                        "token_audit": token_audit,
                    },
                }
            )
    return examples, excluded


def scale_dimension(value: float) -> int:
    if value < -1.0 or value > 1.0:
        raise ValueError(f"dimension score outside [-1, 1]: {value}")
    return round((value + 1.0) * 2.0)


def prohibition_flags(hits: Sequence[str]) -> tuple[int, ...]:
    count = min(len(set(map(str, hits))), len(PROHIBITION_IDS))
    return tuple(
        [1] * count + [0] * (len(PROHIBITION_IDS) - count)
    )


def moral_option(
    action: Mapping[str, Any],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    dimensions = action["construct_receipt"]["dimension_scores"]
    scores = tuple(
        scale_dimension(float(dimensions.get(name, 0.0)))
        for name in MORAL_DIMENSION_ORDER
    )
    return scores, prohibition_flags(action.get("forbidden_hits", []))


def frame_option(
    frames: Sequence[str],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    present = set(map(str, frames))
    base = [4 if frame in present else 0 for frame in FRAME_ORDER]
    support = len(present.intersection(FRAME_ORDER))
    scores = tuple(base + [support, support])
    missing = len(FRAME_ORDER) - support
    prohibitions = tuple(
        [1] * missing + [0] * (len(PROHIBITION_IDS) - missing)
    )
    return scores, prohibitions


def _structured_orientations(
    *,
    tokenizer: Tokenizer,
    prompts: Mapping[str, str],
    constitution_path: Path,
    group_id: str,
    family: str,
    winner_id: str,
    winner_option: tuple[tuple[int, ...], tuple[int, ...]],
    loser_id: str,
    loser_option: tuple[tuple[int, ...], tuple[int, ...]],
    metadata: Mapping[str, Any],
) -> list[dict[str, Any]]:
    winner_scores, winner_prohibitions = winner_option
    loser_scores, loser_prohibitions = loser_option
    canonical = Scenario(
        group_id=group_id,
        family=family,
        option_a_scores=winner_scores,
        option_a_prohibitions=winner_prohibitions,
        option_b_scores=loser_scores,
        option_b_prohibitions=loser_prohibitions,
    )
    examples: list[dict[str, Any]] = []
    for condition in PROMPT_CONDITIONS:
        for orientation, scenario, target_index, action_order in (
            ("winner_a", canonical, 0, [winner_id, loser_id]),
            ("winner_b", canonical.swapped(), 1, [loser_id, winner_id]),
        ):
            encoded = encode_example(
                tokenizer=tokenizer,
                prompt=prompts[condition],
                scenario=scenario,
                constitution_path=constitution_path,
                proof_supervision=False,
            )
            examples.append(
                {
                    "input_ids": encoded["inputs"],
                    "labels": decision_label(tokenizer, target_index),
                    "metadata": {
                        **dict(metadata),
                        "group_id": group_id,
                        "family_id": family,
                        "condition": condition,
                        "orientation": orientation,
                        "action_order": action_order,
                        "target_action_id": winner_id,
                        "acceptable_action_ids": [winner_id],
                    },
                }
            )
    return examples


def build_moral_structured_examples(
    *,
    tasks: Sequence[Mapping[str, Any]],
    tokenizer: Tokenizer,
    prompts: Mapping[str, str],
    constitution_path: Path,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    examples: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    for task in tasks:
        if task.get("split") != "development":
            excluded[f"split:{task.get('split', 'missing')}"] += 1
            continue
        actions = task.get("action_scores")
        best_id = str(task.get("best_action_id", ""))
        if not isinstance(actions, Mapping) or best_id not in actions:
            excluded["missing_action_scores_or_best"] += 1
            continue
        best_score = float(actions[best_id]["robust_score"])
        for action_id, action in sorted(actions.items()):
            if action_id == best_id:
                continue
            if float(action["robust_score"]) >= best_score:
                excluded["non_strict_comparison"] += 1
                continue
            examples.extend(
                _structured_orientations(
                    tokenizer=tokenizer,
                    prompts=prompts,
                    constitution_path=constitution_path,
                    group_id=f"{task['task_id']}::{action_id}",
                    family=str(task["family_id"]),
                    winner_id=best_id,
                    winner_option=moral_option(actions[best_id]),
                    loser_id=str(action_id),
                    loser_option=moral_option(action),
                    metadata={
                        "suite": "moral_reasoner_structured",
                        "task_id": str(task["task_id"]),
                        "split": "development",
                    },
                )
            )
    return examples, excluded


def build_storyworld_structured_examples(
    *,
    public_rows: Sequence[Mapping[str, Any]],
    key_rows: Sequence[Mapping[str, Any]],
    tokenizer: Tokenizer,
    prompts: Mapping[str, str],
    constitution_path: Path,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    public = {str(row["item_id"]): row for row in public_rows}
    examples: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    for key in key_rows:
        if key.get("metric") != "frame_robust_policy_accuracy":
            excluded[f"metric:{key.get('metric', 'missing')}"] += 1
            continue
        item_id = str(key["item_id"])
        item = public.get(item_id, {})
        proof_scores = key.get("proof", {}).get("action_satisfied_frames", {})
        acceptable = set(
            map(str, key.get("target", {}).get("acceptable_action_ids", []))
        )
        legal = set(map(str, key.get("target", {}).get("legal_action_ids", [])))
        losers = legal.difference(acceptable)
        if not acceptable or not losers:
            excluded["no_strict_pair"] += 1
            continue
        for winner_id in sorted(acceptable):
            for loser_id in sorted(losers):
                examples.extend(
                    _structured_orientations(
                        tokenizer=tokenizer,
                        prompts=prompts,
                        constitution_path=constitution_path,
                        group_id=f"{item_id}::{winner_id}::{loser_id}",
                        family=str(item.get("family_id", "unknown")),
                        winner_id=winner_id,
                        winner_option=frame_option(proof_scores.get(winner_id, [])),
                        loser_id=loser_id,
                        loser_option=frame_option(proof_scores.get(loser_id, [])),
                        metadata={
                            "suite": "storyworld_structured",
                            "task_id": item_id,
                            "world_id": str(item.get("world_id", "")),
                            "split": "development",
                        },
                    )
                )
    return examples, excluded


def grid_text(grid: Sequence[Sequence[int]]) -> str:
    rows = ["".join(str(int(cell)) for cell in row) for row in grid]
    if not rows or any(not row for row in rows):
        raise ValueError("ARC grid must be non-empty")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError("ARC grid rows have inconsistent widths")
    return f"{len(rows)}x{width}:" + "/".join(rows)


def render_arc_input(task: Mapping[str, Any], test_input: Sequence[Sequence[int]]) -> str:
    lines = [
        "Infer the exact output grid from the demonstrations.",
        "Colors are digits 0 through 9. Preserve dimensions exactly.",
    ]
    for index, pair in enumerate(task.get("train", []), start=1):
        lines.append(f"Demo {index} input {grid_text(pair['input'])}")
        lines.append(f"Demo {index} output {grid_text(pair['output'])}")
    lines.append(f"Test input {grid_text(test_input)}")
    return "\n".join(lines)


def build_arc_zero_shot_examples(
    *,
    arc_evaluation_dir: Path,
    tokenizer: Tokenizer,
    removed_prompt: str,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    examples: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    for path in sorted(arc_evaluation_dir.glob("*.json")):
        task = json.loads(path.read_text(encoding="utf-8"))
        for test_index, pair in enumerate(task.get("test", [])):
            target_text = grid_text(pair["output"])
            try:
                labels, target_tokens = token_sequence_label(tokenizer, target_text)
            except ValueError:
                excluded["target_over_budget"] += 1
                continue
            for condition, prefix in (
                ("no_prompt", ""),
                ("constitution_removed", removed_prompt),
            ):
                text = f"{prefix}\n\n{render_arc_input(task, pair['input'])}".strip()
                try:
                    input_ids, token_audit = encode_raw_text(
                        tokenizer, text, allow_truncation=False
                    )
                except ValueError:
                    excluded[f"input_over_budget:{condition}"] += 1
                    continue
                examples.append(
                    {
                        "input_ids": input_ids,
                        "labels": labels.copy(),
                        "metadata": {
                            "suite": "arc_zero_shot_text_transduction",
                            "task_id": path.stem,
                            "test_index": test_index,
                            "split": "evaluation",
                            "condition": condition,
                            "target_grid": pair["output"],
                            "target_grid_text": target_text,
                            "target_tokens": target_tokens,
                            "token_audit": token_audit,
                        },
                    }
                )
    return examples, excluded


def write_suite(
    output_dir: Path,
    suite_id: str,
    examples: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not examples:
        raise ValueError(f"suite {suite_id} has no examples")
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs = np.stack([example["input_ids"] for example in examples])
    labels = np.stack([example["labels"] for example in examples])
    inputs_path = output_dir / f"{suite_id}__inputs.npy"
    labels_path = output_dir / f"{suite_id}__labels.npy"
    metadata_path = output_dir / f"{suite_id}__metadata.jsonl"
    np.save(inputs_path, inputs)
    np.save(labels_path, labels)
    metadata_path.write_text(
        "".join(
            json.dumps(example["metadata"], sort_keys=True) + "\n"
            for example in examples
        ),
        encoding="utf-8",
    )
    supervised = (labels != IGNORE_LABEL_ID).sum(axis=1)
    conditions = Counter(
        str(example["metadata"].get("condition", "")) for example in examples
    )
    task_ids = {
        str(example["metadata"].get("task_id", "")) for example in examples
    }
    return {
        "examples": len(examples),
        "unique_tasks": len(task_ids),
        "by_condition": dict(sorted(conditions.items())),
        "inputs_shape": list(inputs.shape),
        "labels_shape": list(labels.shape),
        "supervised_tokens_min": int(supervised.min()),
        "supervised_tokens_max": int(supervised.max()),
        "files": {
            path.name: sha256_file(path)
            for path in (inputs_path, labels_path, metadata_path)
        },
    }
