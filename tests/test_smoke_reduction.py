"""Tests for the reduced F18 smoke and the corrected reload check (frame_internalization_smoke_reduction_v1)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import frame_exclusions as fx  # noqa: E402
import run_six_arm_pipeline as pl  # noqa: E402

PKG = ROOT / "experiments/frame_internalization_sft_v1"


def lf_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(bytes([13, 10]), bytes([10]))).hexdigest()


def test_amendment_is_pinned_and_consistent() -> None:
    data = fx.load_smoke_reduction()
    assert lf_sha(PKG / "PROTOCOL_AMENDMENT_SMOKE_REDUCTION_V1.md") == data["human_readable_sha256_lf"]
    measured = data["measured"]
    assert measured["elapsed_seconds"] / measured["steps"] == pytest.approx(measured["seconds_per_step"], abs=0.01)
    assert 6 * 50 * measured["seconds_per_step"] == pytest.approx(measured["registered_smoke_training_seconds"], abs=5)
    assert measured["registered_smoke_training_seconds"] > measured["registered_cap_seconds"]
    reduced = data["reduced_smoke"]
    seconds = reduced["full_arm_steps"] * measured["seconds_per_step"] + 5 * reduced["other_arms_steps"] * measured["seconds_per_step"]
    assert seconds < measured["registered_cap_seconds"]  # the reduced schedule fits the cap even before overhead
    assert data["reload_check_defect"]["tolerance_changed"] is False
    assert [fx.smoke_steps_for(a, data) for a in pl.ARMS] == [50, 10, 10, 10, 10, 10]
    assert [fx.smoke_steps_for(a, None) for a in pl.ARMS] == [50] * 6


def test_any_edit_to_the_amendment_is_refused(tmp_path: Path) -> None:
    doc = json.loads(fx.SMOKE_REDUCTION_AMENDMENT.read_text(encoding="utf-8"))
    doc["reduced_smoke"]["other_arms_steps"] = 1
    changed = tmp_path / "a.json"
    changed.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(fx.ExclusionError):
        fx.load_smoke_reduction(changed)


def arm_receipt(arm: str, steps: int, match: bool = True, oversize=()) -> dict:
    return {"arm": arm, "sequence_length": 4096, "rejected_oversize": list(oversize),
            "training": {"steps_completed": steps, "elapsed_seconds": steps * 50.7},
            "round_trip": {"logits_match": match, "generations_nonempty": 10, "generations_attempted": 10},
            "planned_full_steps": 60}


def aggregate(tmp_path: Path, steps: dict, *extra: str, match: bool = True) -> tuple[int, dict]:
    paths = []
    for arm in pl.ARMS:
        p = tmp_path / f"{arm}.json"
        p.write_text(json.dumps(arm_receipt(arm, steps[arm], match)), encoding="utf-8")
        paths += ["--arm-receipt", str(p)]
    out = tmp_path / "receipt.json"
    code = subprocess.run([sys.executable, str(ROOT / "scripts/train_frame_internalization_qlora.py"), "aggregate", *paths,
                           "--cleanup-passed", "--gpu-hours", "1.6", "--output", str(out), *extra],
                          capture_output=True, text=True).returncode
    return code, json.loads(out.read_text(encoding="utf-8"))


REDUCED = {a: (50 if a == "neutral_reflection" else 10) for a in pl.ARMS}


def test_reduced_receipt_passes_only_with_the_amendment_and_never_claims_50_steps_per_arm(tmp_path: Path) -> None:
    code, receipt = aggregate(tmp_path, REDUCED, "--smoke-reduction-amendment", str(fx.SMOKE_REDUCTION_AMENDMENT))
    assert code == 0 and receipt["passed"] is True
    assert receipt["steps_per_arm"] is None and receipt["steps_by_arm"] == REDUCED
    assert receipt["reduced_by_amendment"] == "frame_internalization_smoke_reduction_v1"
    assert receipt["checkpoint_round_trip_all_arms"] is True
    code, receipt = aggregate(tmp_path / "x", REDUCED) if (tmp_path / "x").mkdir() is None else (0, {})
    assert code == 2 and receipt["passed"] is False  # without the amendment the registered 50 steps are required


def test_reduced_receipt_still_fails_on_short_arms_or_a_failed_round_trip(tmp_path: Path) -> None:
    flag = ("--smoke-reduction-amendment", str(fx.SMOKE_REDUCTION_AMENDMENT))
    (tmp_path / "a").mkdir()
    code, receipt = aggregate(tmp_path / "a", {**REDUCED, "F1_reflection": 9}, *flag)
    assert code == 2 and not receipt["passed"]
    (tmp_path / "b").mkdir()
    code, receipt = aggregate(tmp_path / "b", {**REDUCED, "neutral_reflection": 10}, *flag)
    assert code == 2 and not receipt["passed"]  # the full-length arm must run all 50
    (tmp_path / "c").mkdir()
    code, receipt = aggregate(tmp_path / "c", REDUCED, *flag, match=False)
    assert code == 2 and not receipt["passed"] and receipt["checkpoint_round_trip_all_arms"] is False
    (tmp_path / "d").mkdir()
    code, receipt = aggregate(tmp_path / "d", {a: 50 for a in pl.ARMS}, *flag)
    assert code == 2  # the amendment fixes the schedule; longer arms do not match it either


def test_smoke_stage_runs_the_reduced_schedule(tmp_path: Path, monkeypatch) -> None:
    cfg = pl.Config(repo=ROOT, f06_dir=tmp_path / "f06", work=tmp_path / "work", model_dir=tmp_path, train_python=Path(sys.executable),
                    vllm_python=Path(sys.executable), price_per_hour=2.0, poll_seconds=0.05,
                    smoke_reduction_amendment=fx.SMOKE_REDUCTION_AMENDMENT)
    cfg.work.mkdir(parents=True)
    seen = {}

    def fake(cmd, **kwargs):
        arm = cmd[cmd.index("--arm") + 1]
        steps = int(cmd[cmd.index("--max-steps") + 1])
        seen[arm] = steps
        d = cfg.work / "smoke" / arm
        d.mkdir(parents=True)
        (d / "arm_receipt.json").write_text(json.dumps(arm_receipt(arm, steps)), encoding="utf-8")
        return 0.0

    monkeypatch.setattr(pl, "run_child", fake)
    monkeypatch.setattr(pl, "gpu_compute_apps", lambda: 0)
    state = pl.load_state(Path("none.json"))
    pl.stage_smoke(cfg, state, cfg.work / "s.json")
    assert seen == REDUCED
    receipt = json.loads((cfg.work / "training_smoke_receipt_v2.json").read_text(encoding="utf-8"))
    assert receipt["passed"] and receipt["steps_by_arm"] == REDUCED


def test_reload_check_uses_the_training_base_and_still_detects_a_real_difference(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")
    import test_frame_sft_trainer as support  # noqa: PLC0415
    import frame_sft_data as fsd  # noqa: PLC0415
    from transformers import Qwen3ForCausalLM  # noqa: PLC0415

    trainer, model, config = support.tiny_model()
    base_state = {k.replace(".base_layer", ""): v.clone() for k, v in model.get_base_model().state_dict().items() if "lora_" not in k}
    data = [fsd.Example(f"r{i}", [10 + (j % 40) for j in range(30)], [10 + (j % 40) for j in range(30)]) for i in range(8)]

    class Tok:
        pad_token_id = 0
        eos_token_id = 1

        def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False):
            return "x"

        def __call__(self, text, return_tensors=None, add_special_tokens=False):
            class Enc(dict):
                def to(self, _):
                    return self

            return Enc(input_ids=torch.tensor([[11, 12, 13]]), attention_mask=torch.ones(1, 3, dtype=torch.long))

        def decode(self, ids, skip_special_tokens=True):
            return "ok"

    trainer.run_training(model, Tok(), data, device="cpu", sequence_length=64, micro_batches=2, epochs=1, max_steps=None, seed=42,
                         learning_rate=1e-2, optimizer_factory=lambda p, lr: torch.optim.AdamW(p, lr=lr), use_scaler=False,
                         log=lambda *_: None)
    probe = trainer.pack_to_tensors(fsd.pack_examples(data, [0], 64, 0)[0], "cpu")
    prompts = [[{"role": "user", "content": "q"}]] * 10

    def like_training():
        m = Qwen3ForCausalLM(config)
        m.load_state_dict(base_state)
        return m

    def unlike_training():  # the defect: a base whose non-quantized weights differ from the trained model's
        m = like_training()
        with torch.no_grad():
            m.model.embed_tokens.weight.add_(0.05 * torch.randn_like(m.model.embed_tokens.weight))
        return m

    good = trainer.adapter_round_trip(model, like_training, Tok(), tmp_path / "good", probe, "cpu", prompts, 3)
    assert good["logits_match"] and good["max_abs_logit_diff"] < 1e-2
    bad = trainer.adapter_round_trip(model, unlike_training, Tok(), tmp_path / "bad", probe, "cpu", prompts, 3)
    assert not bad["logits_match"]  # the 0.01 tolerance still catches a genuinely different base

    source = (ROOT / "scripts/train_frame_internalization_qlora.py").read_text(encoding="utf-8")
    assert "lambda: load_prepared_base(args.model_dir, gradient_checkpointing=False)" in source
    assert "prepare_model_for_kbit_training(load_quantized_base" in source  # only inside load_prepared_base


def test_launcher_passes_the_pinned_smoke_amendment() -> None:
    script = (ROOT / "scripts/stage_and_run_six_arm_after_f06.sh").read_text(encoding="utf-8")
    assert fx.SMOKE_REDUCTION_AMENDMENT_SHA256 in script and "--smoke-reduction-amendment" in script
