from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from tokenizers import Tokenizer

from alignment_harness.constitutional_hrm_eval_v2 import (
    build_arc_zero_shot_examples,
    build_raw_action_examples,
    build_storyworld_text_examples,
    build_text_replay_examples,
    decision_token_id,
    encode_raw_text,
    grid_text,
    write_suite,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
TOKENIZER_PATH = (
    REPO_ROOT
    / "artifacts"
    / "constitutional_hrm_200m_v2"
    / "tokenizer"
    / "tokenizer.json"
)


def test_raw_action_adapter_preserves_action_order_and_balances_conditions() -> None:
    tokenizer = Tokenizer.from_file(str(TOKENIZER_PATH))
    task = {
        "task_id": "t1",
        "family_id": "f1",
        "split": "development",
        "system_prompt": "choose carefully",
        "prompt": "record",
        "visible_facts": [{"id": "F1", "text": "visible"}],
        "action_scores": {
            "A-z": {"text": "last"},
            "A-a": {"text": "first"},
            "A-m": {"text": "middle"},
        },
        "best_action_id": "A-m",
    }
    prompts = {
        "constitution_metta_full": "full",
        "constitution_hash_only": "hash",
        "constitution_removed": "removed",
    }
    examples, excluded = build_raw_action_examples(
        tasks=[task],
        tokenizer=tokenizer,
        prompts=prompts,
        suite="moral",
        target_field="best_action_id",
        allowed_splits={"development"},
    )
    assert not excluded
    assert len(examples) == 3
    assert all(
        example["metadata"]["action_order"] == ["A-a", "A-m", "A-z"]
        for example in examples
    )
    assert all(
        example["labels"][0] == decision_token_id(tokenizer, 1)
        for example in examples
    )


def test_head_tail_truncation_is_explicit() -> None:
    tokenizer = Tokenizer.from_file(str(TOKENIZER_PATH))
    encoded, audit = encode_raw_text(tokenizer, "one " * 2000)
    assert encoded.shape == (512,)
    assert audit["truncated"]
    assert audit["truncation"] == "head_tail"


def test_arc_adapter_excludes_over_budget_and_never_reads_training_split(
    tmp_path: Path,
) -> None:
    tokenizer = Tokenizer.from_file(str(TOKENIZER_PATH))
    evaluation = tmp_path / "evaluation"
    evaluation.mkdir()
    task = {
        "train": [{"input": [[1]], "output": [[2]]}],
        "test": [{"input": [[3]], "output": [[4]]}],
    }
    (evaluation / "abc.json").write_text(json.dumps(task), encoding="utf-8")
    examples, excluded = build_arc_zero_shot_examples(
        arc_evaluation_dir=evaluation,
        tokenizer=tokenizer,
        removed_prompt="select",
    )
    assert not excluded
    assert len(examples) == 2
    assert {example["metadata"]["condition"] for example in examples} == {
        "no_prompt",
        "constitution_removed",
    }
    assert grid_text([[1, 2], [3, 4]]) == "2x2:12/34"


def test_suite_writer_records_shapes_and_supervision(tmp_path: Path) -> None:
    tokenizer = Tokenizer.from_file(str(TOKENIZER_PATH))
    input_ids, _ = encode_raw_text(tokenizer, "short")
    labels = np.full((512,), -100, dtype=np.int32)
    labels[0] = decision_token_id(tokenizer, 0)
    receipt = write_suite(
        tmp_path,
        "tiny",
        [{"input_ids": input_ids, "labels": labels, "metadata": {"id": "x"}}],
    )
    assert receipt["examples"] == 1
    assert receipt["supervised_tokens_min"] == 1
    assert receipt["inputs_shape"] == [1, 512]


def test_storyworld_text_adapter_covers_non_policy_targets() -> None:
    tokenizer = Tokenizer.from_file(str(TOKENIZER_PATH))
    public = [
        {
            "item_id": "x",
            "family_id": "family",
            "world_id": "world",
            "messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "question"},
            ],
        }
    ]
    keys = [{"item_id": "x", "metric": "next_state_accuracy", "target": {"state": "s2"}}]
    examples, excluded = build_storyworld_text_examples(
        public_rows=public,
        key_rows=keys,
        tokenizer=tokenizer,
        removed_prompt="select",
    )
    assert not excluded
    assert len(examples) == 2
    assert all(example["metadata"]["metric"] == "next_state_accuracy" for example in examples)


def test_text_replay_adapter_uses_all_frozen_prompt_conditions() -> None:
    tokenizer = Tokenizer.from_file(str(TOKENIZER_PATH))
    prompts = {
        "constitution_metta_full": "full",
        "constitution_hash_only": "hash",
        "constitution_removed": "removed",
    }
    examples, excluded = build_text_replay_examples(
        tasks=[
            {
                "task_id": "replay",
                "topic_id": "topic",
                "split": "held_out",
                "system_prompt": "system",
                "prompt": "prompt",
                "answer": "answer",
            }
        ],
        tokenizer=tokenizer,
        prompts=prompts,
        suite="replay",
        target_field="answer",
    )
    assert not excluded
    assert len(examples) == 3
