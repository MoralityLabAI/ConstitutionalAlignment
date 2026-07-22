from __future__ import annotations

import json
import tempfile
from pathlib import Path

from alignment_harness.constitutional_metta import (
    HrmArchitecture,
    audit_hrm_architecture,
    compile_constitution_to_metta,
    derive_scenario_proof,
    render_prompt_bundle,
    scenario_proof_to_metta,
)
from alignment_harness.constitutional_hrm import Scenario


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "experiments" / "constitutional_hrm_200m_v2"


def test_constitution_compilation_is_hash_bound_and_complete() -> None:
    compilation = compile_constitution_to_metta(REPO_ROOT / "constitution.md")
    text = compilation["metta_text"]
    assert compilation["constitution_sha256"] in text
    assert "(tenet-weight adl 4)" in text
    assert "(tenet-weight rahmah 2)" in text
    assert "(prohibition ghurur)" in text
    assert "(decision-order 0 fewer-prohibitions)" in text
    assert "(auxiliary-target decisive-rule)" in text
    assert compilation["fact_count"] >= 70


def test_prompt_bundle_has_full_hash_and_removal_conditions() -> None:
    bundle = render_prompt_bundle(REPO_ROOT / "constitution.md")
    full = bundle["prompts"]["constitution_metta_full"]
    removed = bundle["prompts"]["constitution_removed"]
    assert bundle["constitution_sha256"] in full["text"]
    assert bundle["metta_sha256"] in full["text"]
    assert "Decision order:" in full["text"]
    assert bundle["constitution_sha256"] not in removed["text"]
    assert full["sha256"] != removed["sha256"]


def test_scenario_proof_exposes_dense_supervision() -> None:
    scenario = Scenario(
        group_id="dense-proof",
        family="prohibition_tradeoff",
        option_a_scores=(4, 4, 4, 4, 4, 4),
        option_a_prohibitions=(1, 0, 0, 0, 0),
        option_b_scores=(2, 2, 2, 2, 2, 2),
        option_b_prohibitions=(0, 0, 0, 0, 0),
    )
    proof = derive_scenario_proof(scenario, REPO_ROOT / "constitution.md")
    compilation = scenario_proof_to_metta(proof)
    assert proof["selected_option"] == "B"
    assert proof["decisive_rule"] == "fewer-prohibitions"
    assert proof["option_prohibitions"]["A"]["kidhb"] == 1
    assert proof["option_metrics"]["A"]["weighted_tenet_score"] > proof["option_metrics"]["B"]["weighted_tenet_score"]
    assert "(selected-option dense-proof B)" in compilation["metta_text"]
    assert compilation["fact_count"] >= 22


def test_200m_architecture_lands_in_target_band_without_allocation() -> None:
    payload = json.loads((PACKAGE / "model_config.json").read_text(encoding="utf-8"))
    audit = audit_hrm_architecture(HrmArchitecture.from_mapping(payload["architecture"]))
    assert audit["passed"] is True
    assert audit["parameter_count"] == 195_563_522
    assert audit["intermediate_size"] == 2816
    assert audit["static_training_memory_bytes"]["combined_before_activations"] == 3_129_016_352


def test_curriculum_is_focused_balanced_and_family_disjoint() -> None:
    payload = json.loads((PACKAGE / "curriculum_plan.json").read_text(encoding="utf-8"))
    slices = payload["train_slices"]
    assert sum(item["examples"] for item in slices) == payload["train_base_examples"]
    assert abs(sum(item["share"] for item in slices) - 1.0) < 1e-9
    assert len(payload["supervised_target_slots"]) == 11
    assert payload["supervised_target_slot_count"] == 22
    train_ids = {item["id"] for item in slices}
    assert train_ids.isdisjoint(payload["heldout_structural_families"])
    assert payload["augmentation"]["group_split_before_augmentation"] is True


def test_compiler_cli_artifacts_are_serializable() -> None:
    compilation = compile_constitution_to_metta(REPO_ROOT / "constitution.md")
    receipt = {key: value for key, value in compilation.items() if key != "metta_text"}
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "receipt.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        assert json.loads(path.read_text(encoding="utf-8"))["metta_sha256"] == compilation["metta_sha256"]
