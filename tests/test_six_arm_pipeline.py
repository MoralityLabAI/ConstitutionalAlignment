"""CPU tests for the post-F06 pipeline: budgets, gates, state machine, child supervision."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import run_six_arm_pipeline as pl  # noqa: E402


def make_cfg(tmp_path: Path, price: float = 2.128, **kw) -> pl.Config:
    return pl.Config(repo=ROOT, f06_dir=tmp_path / "f06", work=tmp_path / "work", model_dir=tmp_path / "m",
                     train_python=Path(sys.executable), vllm_python=Path(sys.executable),
                     price_per_hour=price, poll_seconds=0.05, **kw)


def fresh_state() -> dict:
    return pl.load_state(Path("does-not-exist.json"))


def test_global_cap_is_the_dollar_ceiling(tmp_path: Path) -> None:
    cfg = make_cfg(tmp_path)
    assert cfg.global_cap_hours == pytest.approx(60 / 2.128)
    state = fresh_state()
    # training keeps the evaluation reserve; the 48 h registered cap never binds at this price
    assert pl.stage_hours("train", state, cfg) == pytest.approx(60 / 2.128 - pl.EVAL_RESERVE_HOURS)
    assert pl.stage_hours("smoke", state, cfg) == 2.0
    assert pl.stage_hours("eval", state, cfg) == 12.0  # its own cap
    state["cumulative_seconds"] = 27 * 3600
    assert pl.stage_hours("eval", state, cfg) == pytest.approx(60 / 2.128 - 27)
    state["cumulative_seconds"] = 29 * 3600
    assert pl.stage_hours("eval", state, cfg) == 0.0
    cheap = make_cfg(tmp_path, price=0.5)
    assert pl.stage_hours("train", fresh_state(), cheap) == pytest.approx(48.0)  # registered cap binds


def test_training_forecast_uses_measured_seconds_per_step() -> None:
    receipts = {a: {"training": {"steps_completed": 50, "elapsed_seconds": 500.0}, "planned_full_steps": 120}
                for a in pl.ARMS}
    hours = pl.forecast_training_hours(receipts, load_overhead_seconds=0)
    assert hours == pytest.approx(6 * 120 * 10.0 / 3600)


def good_manifest() -> dict:
    arm = {"over_4096_count": 0, "train_count": 5320, "validation_count": 280}
    return {"schema_version": "frame_internalization_curriculum_manifest.v1", "passed": True,
            "f3_pair_total_token_spread": 0.01, "arms": {a: dict(arm) for a in pl.ARMS}}


def test_curriculum_gates() -> None:
    assert pl.curriculum_gate_failures(good_manifest()) == []
    bad = good_manifest()
    bad["arms"]["F1_reflection"]["over_4096_count"] = 3
    assert any("over 4,096" in f for f in pl.curriculum_gate_failures(bad))
    bad = good_manifest()
    bad["f3_pair_total_token_spread"] = 0.05
    assert any("0.02" in f for f in pl.curriculum_gate_failures(bad))
    bad = good_manifest()
    bad["passed"] = False
    assert pl.curriculum_gate_failures(bad)


def test_f06_gate(tmp_path: Path) -> None:
    f06 = tmp_path / "f06"
    f06.mkdir()
    assert len(pl.f06_gate_failures(f06)) == 4
    for frame in pl.FRAMES:
        (f06 / f"{frame}.receipt.json").write_text(json.dumps({"complete": True}), encoding="utf-8")
    assert pl.f06_gate_failures(f06) == []
    (f06 / "F3.receipt.json").write_text(json.dumps({"complete": False}), encoding="utf-8")
    assert len(pl.f06_gate_failures(f06)) == 1


def test_base_freeze_receipt_verifies_hashes(tmp_path: Path) -> None:
    import hashlib

    model = tmp_path / "model"
    model.mkdir()
    (model / "a.bin").write_bytes(b"abc")
    inv = tmp_path / "inv.json"
    inv.write_text(json.dumps({"repository": "Qwen/Qwen3-1.7B", "revision": "r",
                               "artifacts": [{"path": "a.bin", "sha256": hashlib.sha256(b"abc").hexdigest()}]}),
                   encoding="utf-8")
    receipt = pl.write_base_freeze(inv, model, tmp_path / "freeze.json")
    assert receipt["passed"] and receipt["schema_version"] == "frame_internalization_base_freeze.v1"
    (model / "a.bin").write_bytes(b"tampered")
    with pytest.raises(pl.StageFailure):
        pl.write_base_freeze(inv, model, tmp_path / "freeze2.json")


def test_state_machine_resumes_running_and_never_retries_failed(tmp_path: Path) -> None:
    cfg = make_cfg(tmp_path)
    calls: list[str] = []

    def ok(name):
        def fn(c, s, p):
            calls.append(name)
        return fn

    def failing(c, s, p):
        calls.append("gates")
        raise pl.StageFailure("parity failed")

    funcs = {n: ok(n) for n in pl.STAGES}
    funcs["gates"] = failing
    assert pl.run_pipeline(cfg, funcs) == 2
    assert calls == ["render", "gates"]
    state = pl.load_state(cfg.work / "pipeline_state.json")
    assert state["stages"]["render"]["status"] == "done" and state["stages"]["gates"]["status"] == "failed"
    assert json.loads((cfg.work / "pipeline_stop.json").read_text())["stage"] == "gates"
    assert pl.run_pipeline(cfg, funcs) == 3 and calls == ["render", "gates"]  # failed stages are not retried

    cfg2 = make_cfg(tmp_path / "second")
    calls.clear()
    state = pl.load_state(cfg2.work / "pipeline_state.json")
    cfg2.work.mkdir(parents=True)
    state["stages"]["render"]["status"] = "done"
    state["stages"]["gates"]["status"] = "running"  # an interrupted stage resumes
    pl.save_state(cfg2.work / "pipeline_state.json", state)
    assert pl.run_pipeline(cfg2, {n: ok(n) for n in pl.STAGES}) == 0
    assert calls == ["gates", "smoke", "train", "eval", "analysis"]


def test_analysis_waits_for_judging_without_credentials(tmp_path: Path) -> None:
    cfg = make_cfg(tmp_path)
    cfg.work.mkdir(parents=True)
    pl.stage_analysis(cfg, fresh_state(), cfg.work / "s.json")
    note = json.loads((cfg.work / "awaiting_judging.json").read_text(encoding="utf-8"))
    assert note["status"] == "awaiting_judging" and "credentials" in note["reason"]


posix_only = pytest.mark.skipif(sys.platform == "win32", reason="process groups need POSIX")


def child(cfg, tmp_path, code, cap):
    state = fresh_state()
    cfg.work.mkdir(parents=True, exist_ok=True)
    path = cfg.work / "s.json"
    try:
        pl.run_child([sys.executable, "-c", code], cfg=cfg, state=state, state_path=path, stage="smoke",
                     log_path=cfg.work / "c.log", seconds_cap=cap)
        return state, None
    except pl.StageFailure as failure:
        return state, str(failure)


@posix_only
def test_child_supervision(tmp_path: Path) -> None:
    cfg = make_cfg(tmp_path)
    state, err = child(cfg, tmp_path, "import time; time.sleep(0.3)", 30)
    assert err is None and state["cumulative_seconds"] > 0.2
    assert (cfg.work / "heartbeat.json").exists() or state["cumulative_seconds"] > 0
    _, err = child(cfg, tmp_path, "import sys; sys.exit(3)", 30)
    assert err and "exited 3" in err
    _, err = child(cfg, tmp_path, "import time; time.sleep(30)", 0.3)
    assert err and "stage_cap" in err
    cfg.work.mkdir(parents=True, exist_ok=True)
    (cfg.work / "STOP").write_text("x")
    _, err = child(cfg, tmp_path, "import time; time.sleep(30)", 30)
    assert err and "manual_stop" in err


@posix_only
def test_dollar_cap_and_temperature_stop(tmp_path: Path) -> None:
    cfg = make_cfg(tmp_path, total_usd=0.0001)  # about 0.18 s of budget at 2.128/h
    _, err = child(cfg, tmp_path, "import time; time.sleep(30)", 30)
    assert err and "dollar_cap" in err
    hot = make_cfg(tmp_path / "hot", gpu_temp=lambda: 95)
    hot.poll_seconds = 0.05

    import run_six_arm_pipeline as mod

    original = mod.time.time
    clock = {"t": original()}
    # advance the temperature check interval quickly by faking a fast clock
    mod.time.time = lambda: clock.__setitem__("t", clock["t"] + 61) or clock["t"]
    try:
        _, err = child(hot, tmp_path, "import time; time.sleep(30)", 10**9)
    finally:
        mod.time.time = original
    assert err and "gpu_temperature" in err


def test_launcher_contract() -> None:
    script = (ROOT / "scripts/stage_and_run_six_arm_after_f06.sh").read_text(encoding="utf-8")
    assert 'total_usd="${TOTAL_USD:-60}"' in script and "setsid nohup" in script
    assert "run_six_arm_pipeline.py" in script and "prime.exe" not in script and "pods " not in script
    assert "environment_lock_20260723.txt" in script
    if shutil.which("bash"):
        result = subprocess.run(["bash", "-n", str(ROOT / "scripts/stage_and_run_six_arm_after_f06.sh")],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
