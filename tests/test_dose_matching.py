"""Tests for the dose-matching amendment (frame_internalization_dose_matching_v1)."""

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
import frame_sft_data as fsd  # noqa: E402
import run_six_arm_pipeline as pl  # noqa: E402

PKG = ROOT / "experiments/frame_internalization_sft_v1"
FREEZE = PKG / "rerun_freeze/qwen3_1p7b_v1/curriculum_generation_v1/request_manifest.json"


def lf_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(bytes([13, 10]), bytes([10]))).hexdigest()


def test_amendment_is_pinned_and_its_numbers_are_consistent() -> None:
    data = fx.load_dose_matching()
    assert lf_sha(PKG / "PROTOCOL_AMENDMENT_DOSE_MATCHING_V1.md") == data["human_readable_sha256_lf"]
    assert data["supersedes"] == "frame_internalization_parity_balance_v1"
    pair = data["matched_pairs"][0]
    assert (pair["reference_arm"], pair["matched_arm"]) == ("F3_reflection", "F3_concrete_reflection") and len(data["matched_pairs"]) == 1
    real = data["matched_schedule_on_real_rendered_data"]
    assert real["f3_reflection"]["steps"] == sum(real["f3_reflection"]["steps_per_epoch"]) == 52
    assert real["f3_concrete_native"]["steps"] == 54
    assert real["f3_concrete_matched"]["epoch_one_steps"] + real["f3_concrete_matched"]["epoch_two_steps"] == 52
    assert real["padded_tokens_each"] == 52 * data["packing"]["padded_tokens_per_step"]
    measured = data["measurement_recorded_not_enforced"]
    spread = (measured["f3_concrete_reflection_train_tokens"] - measured["f3_reflection_train_tokens"]) / measured["f3_reflection_train_tokens"]
    assert spread == pytest.approx(measured["spread"], abs=1e-12) and measured["enforced"] is False


def test_any_edit_to_the_amendment_is_refused(tmp_path: Path) -> None:
    doc = json.loads(fx.DOSE_MATCHING_AMENDMENT.read_text(encoding="utf-8"))
    doc["matched_pairs"].append({"reference_arm": "F1_reflection", "matched_arm": "F3_reflection"})
    changed = tmp_path / "a.json"
    changed.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(fx.ExclusionError):
        fx.load_dose_matching(changed)


def test_matched_steps_come_only_from_a_completed_reference_of_the_named_pair() -> None:
    import train_frame_internalization_qlora as tr

    amendment = fx.load_dose_matching()
    ref = {"arm": "F3_reflection", "complete": True, "max_steps": None, "training": {"steps_completed": 52}}
    assert tr.resolve_matched_steps("F3_concrete_reflection", amendment, ref) == 52
    with pytest.raises(tr.StopGate):
        tr.resolve_matched_steps("F1_reflection", amendment, ref)  # no other arm may be matched
    with pytest.raises(tr.StopGate):
        tr.resolve_matched_steps("F3_concrete_reflection", amendment, {**ref, "complete": False})
    with pytest.raises(tr.StopGate):
        tr.resolve_matched_steps("F3_concrete_reflection", amendment, {**ref, "max_steps": 50})  # a smoke is not a reference
    with pytest.raises(tr.StopGate):
        tr.resolve_matched_steps("F3_concrete_reflection", amendment, {**ref, "arm": "F1_reflection"})


def examples(count: int, length: int):
    return [fsd.Example(f"r{i}", [10 + (j % 40) for j in range(length)], [10 + (j % 40) for j in range(length)]) for i in range(count)]


def test_matched_schedule_is_the_prefix_of_the_native_schedule() -> None:
    long_arm = examples(60, 50)  # packs 2 per 128-token block here
    native = fsd.plan_steps(long_arm, 128, 0, 4, 42, 2, None)
    k = len(native) - 2
    matched = fsd.plan_steps(long_arm, 128, 0, 4, 42, 2, k)
    assert len(matched) == k and matched == native[:k]
    assert all(len(s) == 4 for s in matched)  # every step carries the same number of padded blocks


def test_training_loop_gives_equal_padded_tokens_and_reports_loss_tokens() -> None:
    torch = pytest.importorskip("torch")
    from test_frame_sft_trainer import tiny_model  # noqa: PLC0415

    class Tok:
        pad_token_id = 0
        eos_token_id = 1

    runs = {}
    for name, data in (("reference", examples(24, 30)), ("longer", examples(24, 40))):
        trainer, model, _ = tiny_model()
        steps_native = len(fsd.plan_steps(data, 64, 0, 2, 42, 2, None))
        cap = 6 if name == "longer" else None
        runs[name] = trainer.run_training(
            model, Tok(), data, device="cpu", sequence_length=64, micro_batches=2, epochs=2, max_steps=cap, seed=42,
            learning_rate=1e-2, optimizer_factory=lambda p, lr: torch.optim.AdamW(p, lr=lr), use_scaler=False,
            log=lambda *_: None)
        runs[name]["native"] = steps_native
    assert runs["longer"]["native"] > 6
    assert runs["longer"]["steps_completed"] == 6
    assert runs["longer"]["padded_tokens_total"] == 6 * 2 * 64
    assert runs["reference"]["padded_tokens_total"] == runs["reference"]["steps_completed"] * 2 * 64
    assert runs["longer"]["loss_tokens_total"] > 0


def test_forecast_gives_the_matched_arm_the_reference_step_count() -> None:
    def receipt(planned: int) -> dict:
        return {"training": {"steps_completed": 50, "elapsed_seconds": 500.0}, "planned_full_steps": planned}

    receipts = {a: receipt(10) for a in pl.ARMS}
    receipts["F3_reflection"] = receipt(52)
    receipts["F3_concrete_reflection"] = receipt(54)
    assert pl.full_steps("F3_concrete_reflection", receipts, True) == 52
    assert pl.full_steps("F3_concrete_reflection", receipts, False) == 54
    assert pl.full_steps("F1_reflection", receipts, True) == 10
    assert pl.forecast_training_hours(receipts, 0, True) < pl.forecast_training_hours(receipts, 0, False)


def manifest(matches: bool = True, spread: float = 0.09555105002684004, passed: bool = True) -> dict:
    arm = {"over_4096_count": 0, "train_count": 5319, "validation_count": 280}
    return {"schema_version": "frame_internalization_curriculum_manifest.v1", "passed": passed,
            "f3_pair_total_token_spread": spread, "arms": {a: dict(arm) for a in pl.ARMS},
            "exclusion": {"amendment_id": "frame_internalization_failed_scenario_v1", "excluded_scenario_ids": ["d03508"]},
            "parity_measurement": {"amendment_id": "frame_internalization_dose_matching_v1", "enforced": False,
                                   "matches_recorded_measurement": matches}}


def test_pipeline_gate_waives_the_spread_only_under_the_pinned_amendment() -> None:
    exclusion, dose = fx.load_exclusion(), fx.load_dose_matching()
    assert pl.curriculum_gate_failures(manifest(), exclusion, dose) == []
    assert pl.curriculum_gate_failures(manifest(), exclusion, None)  # without the amendment the gate stands
    assert pl.curriculum_gate_failures(manifest(matches=False), exclusion, dose)  # a different measurement stops
    assert pl.curriculum_gate_failures(manifest(passed=False), exclusion, dose)  # every other gate still stops
    bad = manifest()
    bad["arms"]["F1_reflection"]["over_4096_count"] = 1
    assert pl.curriculum_gate_failures(bad, exclusion, dose)
    bad = manifest()
    bad["arms"]["F1_reflection"]["train_count"] = 5318
    assert pl.curriculum_gate_failures(bad, exclusion, dose)


def test_train_command_matches_steps_only_for_the_named_arm_and_not_in_the_smoke(tmp_path: Path) -> None:
    cfg = pl.Config(repo=ROOT, f06_dir=tmp_path, work=tmp_path / "w", model_dir=tmp_path, train_python=Path(sys.executable),
                    vllm_python=Path(sys.executable), price_per_hour=2.0, dose_matching_amendment=fx.DOSE_MATCHING_AMENDMENT)
    out = tmp_path / "train"
    full = pl.train_cmd(cfg, "F3_concrete_reflection", out, None)
    assert "--match-steps-from" in full and str(out / "F3_reflection" / "arm_receipt.json") in full
    assert "--match-steps-from" not in pl.train_cmd(cfg, "F3_concrete_reflection", out, 50)  # smoke
    assert "--match-steps-from" not in pl.train_cmd(cfg, "F3_reflection", out, None)
    assert "--match-steps-from" not in pl.train_cmd(cfg, "F1_reflection", out, None)


def test_launcher_passes_the_pinned_dose_amendment() -> None:
    script = (ROOT / "scripts/stage_and_run_six_arm_after_f06.sh").read_text(encoding="utf-8")
    assert fx.DOSE_MATCHING_AMENDMENT_SHA256 in script and "--dose-matching-amendment" in script


TOKENIZERS = glob.glob(os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub",
                                    "models--Qwen--Qwen3-1.7B-Base", "snapshots", "*"))


@pytest.mark.skipif(not TOKENIZERS, reason="Qwen3 tokenizer not in the local HF cache")
def test_renderer_records_the_measurement_but_a_different_imbalance_still_stops(tmp_path: Path) -> None:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    rows = [json.loads(l) for l in (ROOT / freeze["dilemmas"]["path"]).read_bytes().decode("utf-8").splitlines() if l.strip()]
    receipt = tmp_path / "freeze.json"
    receipt.write_text(json.dumps({"schema_version": "frame_internalization_base_freeze.v1", "passed": True,
                                   "revision": freeze["generation"]["model_revision"],
                                   "model_dir": str(Path(TOKENIZERS[0]).resolve())}), encoding="utf-8")

    def build(raw: Path, f3c_pad: int) -> None:
        raw.mkdir()
        for frame in ("neutral", "F1", "F3", "F3_concrete"):
            out = []
            for row in rows:
                if row["scenario_id"] == "d03508" and frame == "neutral":
                    continue
                pad = " word" * f3c_pad if frame == "F3_concrete" else ""
                msgs = [{"role": r, "content": f"{r} {row['scenario_id']}{pad}"} for r in ("user", "assistant") * 3]
                out.append(json.dumps({"request_id": f"{frame}:{row['scenario_id']}", "scenario_id": row["scenario_id"],
                                       "source_frame": frame, "source_frame_prompt_sha256": freeze["frames"][frame]["prompt_text_sha256"],
                                       "dilemma_prompt": row["prompt_text"], "cluster_id": row["cluster_id"], "split": row["split"],
                                       "transcript": msgs, "final": f"final{pad}"}))
            (raw / f"{frame}.jsonl").write_bytes(("\n".join(out) + "\n").encode())

    def render(raw: Path, name: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "scripts/render_frame_curricula.py"), "--freeze", str(FREEZE),
                               "--base-freeze-receipt", str(receipt), "--raw-dir", str(raw), "--tokenizer", TOKENIZERS[0],
                               "--output-dir", str(tmp_path / name), "--manifest", str(tmp_path / f"{name}.json"),
                               "--exclusion-amendment", str(fx.AMENDMENT), "--dose-matching-amendment", str(fx.DOSE_MATCHING_AMENDMENT)],
                              capture_output=True, text=True)

    build(tmp_path / "even", 0)
    even = render(tmp_path / "even", "even")
    m = json.loads((tmp_path / "even.json").read_text(encoding="utf-8"))
    assert even.returncode == 0 and m["parity_measurement"]["enforced"] is False
    assert m["parity_measurement"]["matches_recorded_measurement"] is False  # not the measurement the amendment was decided on
    assert pl.curriculum_gate_failures(m, fx.load_exclusion(), fx.load_dose_matching())  # so the pipeline still stops

    build(tmp_path / "skewed", 40)  # F3-concrete far longer: a spread the amendment did not record
    skewed = render(tmp_path / "skewed", "skewed")
    ms = json.loads((tmp_path / "skewed.json").read_text(encoding="utf-8"))
    assert skewed.returncode == 2 and ms["passed"] is False and ms["f3_pair_total_token_spread"] > 0.02
