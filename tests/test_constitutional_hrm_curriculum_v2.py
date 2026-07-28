from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from alignment_harness.constitutional_hrm_curriculum_v2 import (
    ARMS,
    HELDOUT_FAMILIES,
    IGNORE_LABEL_ID,
    PROOF_SLOT_COUNT,
    materialize_curriculum,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_smoke_curriculum_is_matched_disjoint_and_deterministic(tmp_path) -> None:
    output = tmp_path / "first"
    kwargs = {
        "tokenizer_path": REPO_ROOT
        / "artifacts"
        / "constitutional_hrm_200m_v2"
        / "tokenizer"
        / "tokenizer.json",
        "prompt_bundle_path": REPO_ROOT
        / "artifacts"
        / "constitutional_hrm_200m_v2"
        / "generated"
        / "system_prompt_bundle_v2.json",
        "constitution_path": REPO_ROOT / "constitution.md",
        "production": False,
        "seed": 99,
    }
    first = materialize_curriculum(output_dir=output, **kwargs)
    second = materialize_curriculum(output_dir=tmp_path / "second", **kwargs)

    assert first["status"] == "passed"
    assert first["checks"]["split_groups_disjoint"]
    assert first["checks"]["group_permutation_has_no_fixed_points"]
    assert first["heldout_families"] == list(HELDOUT_FAMILIES)
    assert set(first["arms"]) == set(ARMS)
    assert first["counts"]["train_examples"] == 96
    assert first["counts"]["validation_examples"] == 192
    assert first["file_sha256"] == second["file_sha256"]

    inputs = np.load(output / "common" / "train_inputs.npy", mmap_mode="r")
    assert inputs.shape == (96, 512)
    metta = np.load(
        output / "arms" / "constitutional_metta" / "train_labels.npy",
        mmap_mode="r",
    )
    text = np.load(
        output / "arms" / "constitutional_text_only" / "train_labels.npy",
        mmap_mode="r",
    )
    assert np.all((metta != IGNORE_LABEL_ID).sum(axis=1) == PROOF_SLOT_COUNT)
    assert np.all((text != IGNORE_LABEL_ID).sum(axis=1) == 1)


def test_smoke_manifest_hashes_every_array(tmp_path) -> None:
    materialize_curriculum(
        output_dir=tmp_path,
        tokenizer_path=REPO_ROOT
        / "artifacts"
        / "constitutional_hrm_200m_v2"
        / "tokenizer"
        / "tokenizer.json",
        prompt_bundle_path=REPO_ROOT
        / "artifacts"
        / "constitutional_hrm_200m_v2"
        / "generated"
        / "system_prompt_bundle_v2.json",
        constitution_path=REPO_ROOT / "constitution.md",
        production=False,
        seed=7,
    )
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert "common/train_inputs.npy" in manifest["file_sha256"]
    for arm in ARMS:
        assert f"arms/{arm}/train_labels.npy" in manifest["file_sha256"]
