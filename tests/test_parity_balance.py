"""Tests for the parity-balance rule and its hash-bound amendment (frame_internalization_parity_balance_v1)."""

from __future__ import annotations

import glob
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import frame_exclusions as fx  # noqa: E402
import parity_balance as pb  # noqa: E402
import run_six_arm_pipeline as pl  # noqa: E402

PKG = ROOT / "experiments/frame_internalization_sft_v1"


def lf_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(bytes([13, 10]), bytes([10]))).hexdigest()


def test_rule_drops_largest_absolute_differences_first_and_stops_at_the_gate() -> None:
    f3 = {f"d{i:03d}": 1000 for i in range(100)}
    f3c = {sid: 1000 for sid in f3}
    f3c["d010"], f3c["d020"], f3c["d030"] = 3000, 2500, 2000  # +4,500 tokens over a 100,000 base
    result = pb.select_drops(f3, f3c)
    assert result["status"] == "balanced" and result["dropped"] == ["d010", "d020"] 
    assert result["final_spread"] <= 0.02 and result["initial_spread"] > 0.02


def test_ties_break_by_scenario_id_and_a_balanced_start_drops_nothing() -> None:
    f3 = {"d002": 1000, "d001": 1000, "d003": 1000, "d000": 1000}
    f3c = {"d002": 1500, "d001": 1500, "d003": 1500, "d000": 1000}
    result = pb.select_drops(f3, f3c)
    assert result["dropped"][:2] == ["d001", "d002"]
    same = pb.select_drops({"a": 10, "b": 10}, {"a": 10, "b": 10})
    assert same["status"] == "balanced" and same["dropped"] == []


def test_cap_makes_the_gate_unreachable() -> None:
    f3 = {f"d{i:04d}": 1000 for i in range(1000)}
    f3c = {sid: 1100 for sid in f3}  # a 10% gap in every scenario
    result = pb.select_drops(f3, f3c)
    assert result["status"] == "parity_unreachable" and len(result["dropped"]) == pb.CAP
    assert pb.scenarios_to_drop(result) == set()  # nothing is applied when unreachable
    assert result["final_spread"] == pytest.approx(0.1)
    with pytest.raises(ValueError):
        pb.select_drops({"a": 1}, {"b": 1})


def test_amendment_is_hash_bound_and_records_the_real_outcome() -> None:
    data = fx.load_parity()
    assert lf_sha(PKG / "PROTOCOL_AMENDMENT_PARITY_BALANCE_V1.md") == data["human_readable_sha256_lf"]
    assert lf_sha(ROOT / "scripts/parity_balance.py") == data["rule"]["code_sha256_lf"]
    result = data["result"]
    assert result["status"] == "parity_unreachable" and result["applied"] is False
    assert result["initial_spread"] == pytest.approx(0.09555105, abs=1e-8) and result["final_spread"] > 0.02
    listed = result["drop_list_evaluated_not_applied"]
    assert len(listed) == data["rule"]["cap"] == pb.CAP == 560 and pb.drop_list_sha256(listed) == result["drop_list_sha256"]
    assert data["gate_fired"]["measured"]["spread"] == result["initial_spread"]
    assert "d03508" in data["unchanged"][0]


def test_changing_the_amendment_or_the_rule_code_is_refused(tmp_path: Path) -> None:
    changed = tmp_path / "a.json"
    doc = json.loads(fx.PARITY_AMENDMENT.read_text(encoding="utf-8"))
    doc["rule"]["cap"] = 1300
    changed.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(fx.ExclusionError):
        fx.load_parity(changed)
    edited_code = tmp_path / "parity_balance.py"
    edited_code.write_bytes((ROOT / "scripts/parity_balance.py").read_bytes() + b"\nCAP = 1300\n")
    with pytest.raises(fx.ExclusionError):
        fx.load_parity(code_path=edited_code)


def test_verification_rejects_data_the_amendment_was_not_computed_on() -> None:
    amendment = json.loads(fx.PARITY_AMENDMENT.read_text(encoding="utf-8"))
    f3 = {f"d{i:03d}": 1000 for i in range(50)}
    with pytest.raises(pb.ParityError):
        pb.verify_against_amendment(f3, dict(f3), amendment)  # balanced data vs a recorded unreachable outcome
    # a synthetic amendment that matches synthetic data verifies
    f3c = {sid: 1000 for sid in f3}
    f3c["d001"] = 2500
    result = pb.select_drops(f3, f3c)
    synthetic = {"rule": {"gate": pb.GATE, "cap": pb.CAP},
                 "result": {"status": result["status"], "drop_list_sha256": pb.drop_list_sha256(result["dropped"]),
                            "final_spread": result["final_spread"]}}
    assert pb.verify_against_amendment(f3, f3c, synthetic)["dropped"] == result["dropped"]
    synthetic["result"]["drop_list_sha256"] = "0" * 64
    with pytest.raises(pb.ParityError):
        pb.verify_against_amendment(f3, f3c, synthetic)


def test_pipeline_gate_stops_on_an_unreachable_parity_outcome() -> None:
    arm = {"over_4096_count": 0, "train_count": 5319, "validation_count": 280}
    manifest = {"schema_version": "frame_internalization_curriculum_manifest.v1", "passed": False,
                "f3_pair_total_token_spread": 0.0956, "arms": {a: dict(arm) for a in pl.ARMS},
                "exclusion": {"amendment_id": "frame_internalization_failed_scenario_v1", "excluded_scenario_ids": ["d03508"]},
                "parity_balance": {"status": "parity_unreachable", "applied": False}}
    failures = pl.curriculum_gate_failures(manifest, fx.load_exclusion())
    assert any("parity rule outcome parity_unreachable" in f for f in failures)
    assert any("0.02" in f or "0.0956" in f for f in failures)


TOKENIZERS = glob.glob(os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub",
                                    "models--Qwen--Qwen3-1.7B-Base", "snapshots", "*"))


@pytest.mark.skipif(not TOKENIZERS, reason="Qwen3 tokenizer not in the local HF cache")
def test_renderer_refuses_data_that_does_not_match_the_recorded_outcome(tmp_path: Path) -> None:
    freeze_path = PKG / "rerun_freeze/qwen3_1p7b_v1/curriculum_generation_v1/request_manifest.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    rows = [json.loads(l) for l in (ROOT / freeze["dilemmas"]["path"]).read_bytes().decode("utf-8").splitlines() if l.strip()]
    raw = tmp_path / "raw"
    raw.mkdir()
    for frame in ("neutral", "F1", "F3", "F3_concrete"):
        out = []
        for row in rows:
            if row["scenario_id"] == "d03508" and frame == "neutral":
                continue
            msgs = [{"role": r, "content": f"{r} {row['scenario_id']}"} for r in ("user", "assistant") * 3]
            out.append(json.dumps({"request_id": f"{frame}:{row['scenario_id']}", "scenario_id": row["scenario_id"],
                                   "source_frame": frame, "source_frame_prompt_sha256": freeze["frames"][frame]["prompt_text_sha256"],
                                   "dilemma_prompt": row["prompt_text"], "cluster_id": row["cluster_id"], "split": row["split"],
                                   "transcript": msgs, "final": "final"}))
        (raw / f"{frame}.jsonl").write_bytes(("\n".join(out) + "\n").encode())
    receipt = tmp_path / "freeze.json"
    receipt.write_text(json.dumps({"schema_version": "frame_internalization_base_freeze.v1", "passed": True,
                                   "revision": freeze["generation"]["model_revision"],
                                   "model_dir": str(Path(TOKENIZERS[0]).resolve())}), encoding="utf-8")
    run = subprocess.run([sys.executable, str(ROOT / "scripts/render_frame_curricula.py"), "--freeze", str(freeze_path),
                          "--base-freeze-receipt", str(receipt), "--raw-dir", str(raw), "--tokenizer", TOKENIZERS[0],
                          "--output-dir", str(tmp_path / "out"), "--manifest", str(tmp_path / "m.json"),
                          "--exclusion-amendment", str(fx.AMENDMENT), "--parity-amendment", str(fx.PARITY_AMENDMENT)],
                         capture_output=True, text=True)
    assert run.returncode != 0 and "ParityError" in run.stderr
