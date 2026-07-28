from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from tokenizers import Tokenizer

from alignment_harness.constitutional_hrm_v2 import (
    IGNORE_LABEL_ID,
    PROOF_SLOT_COUNT,
    encode_example,
    fixed_adapter_scenarios,
    proof_target_tokens,
    write_official_dataset,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
TOKENIZER_PATH = (
    REPO_ROOT / "artifacts" / "constitutional_hrm_200m_v2" / "tokenizer" / "tokenizer.json"
)
PROMPT_BUNDLE = (
    REPO_ROOT
    / "artifacts"
    / "constitutional_hrm_200m_v2"
    / "generated"
    / "system_prompt_bundle_v2.json"
)


def load_prompt() -> str:
    return json.loads(PROMPT_BUNDLE.read_text(encoding="utf-8"))["prompts"][
        "constitution_metta_full"
    ]["text"]


def test_proof_targets_have_exact_slot_count_and_atomic_tokens() -> None:
    tokenizer = Tokenizer.from_file(str(TOKENIZER_PATH))
    example = encode_example(
        tokenizer=tokenizer,
        prompt=load_prompt(),
        scenario=fixed_adapter_scenarios()[0],
        constitution_path=REPO_ROOT / "constitution.md",
    )
    tokens = proof_target_tokens(example["proof"])
    assert len(tokens) == PROOF_SLOT_COUNT
    assert all(len(tokenizer.encode(token).ids) == 1 for token in tokens)
    assert int((example["labels"] != IGNORE_LABEL_ID).sum()) == PROOF_SLOT_COUNT


def test_all_fixed_scenarios_fit_frozen_budgets() -> None:
    tokenizer = Tokenizer.from_file(str(TOKENIZER_PATH))
    examples = [
        encode_example(
            tokenizer=tokenizer,
            prompt=load_prompt(),
            scenario=scenario,
            constitution_path=REPO_ROOT / "constitution.md",
        )
        for scenario in fixed_adapter_scenarios()
    ]
    assert max(example["prompt_tokens"] for example in examples) <= 320
    assert max(example["scenario_tokens"] for example in examples) <= 160
    assert all(example["inputs"].shape == (512,) for example in examples)


def test_official_dataset_arrays_and_metadata_are_consistent(tmp_path) -> None:
    tokenizer = Tokenizer.from_file(str(TOKENIZER_PATH))
    examples = [
        encode_example(
            tokenizer=tokenizer,
            prompt=load_prompt(),
            scenario=scenario,
            constitution_path=REPO_ROOT / "constitution.md",
        )
        for scenario in fixed_adapter_scenarios()[:3]
    ]
    write_official_dataset(
        output_dir=tmp_path,
        train_examples=examples[:2],
        eval_sets={"development": examples[2:]},
        pad_id=int(tokenizer.token_to_id("<|pad|>")),
        vocab_size=tokenizer.get_vocab_size(with_added_tokens=True),
        seq_len=512,
    )
    metadata = json.loads((tmp_path / "train" / "dataset.json").read_text())
    assert metadata["vocab_size"] == 32768
    assert metadata["seq_len"] == 512
    assert metadata["ignore_label_id"] == IGNORE_LABEL_ID
    assert np.load(tmp_path / "train" / "all__inputs.npy").shape == (2, 512)
    labels = np.load(tmp_path / "test" / "development__labels.npy")
    assert labels.shape == (1, 512)
    assert int((labels != IGNORE_LABEL_ID).sum()) == PROOF_SLOT_COUNT
