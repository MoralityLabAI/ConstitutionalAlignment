#!/usr/bin/env python3
"""Study 3 stages after F06 on one pod: render, gates, F18 smoke, training, evaluation generation.

Every stage has an hour cap that also respects one dollar ceiling (total_usd /
price_per_hour). A failed gate or cap marks the stage failed and stops; a relaunch
resumes only an interrupted ("running") stage and never retries a failed one.
Judge scoring needs API credentials and is not run here: the pipeline ends at
``awaiting_judging``. Stdlib only apart from the child commands. Prints no secrets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parent.parent
PKG = "experiments/frame_internalization_sft_v1"
ARMS = ("neutral_reflection", "F1_reflection", "F1_demonstration", "F3_reflection",
        "F3_demonstration", "F3_concrete_reflection")
FRAMES = ("neutral", "F1", "F3", "F3_concrete")
STAGES = ("render", "gates", "smoke", "train", "eval", "analysis")
STAGE_CAP_HOURS = {"render": 0.5, "gates": 0.5, "smoke": 2.0, "train": 48.0, "eval": 12.0, "analysis": 0.25}
EVAL_RESERVE_HOURS = 4.0
SMOKE_WALL_SECONDS = 7200
TEMP_LIMIT_C = 90


class StageFailure(RuntimeError):
    """A registered gate or cap fired. The stage is marked failed and the run stops."""


@dataclass
class Config:
    repo: Path
    f06_dir: Path
    work: Path
    model_dir: Path
    train_python: Path
    vllm_python: Path
    price_per_hour: float
    total_usd: float = 60.0
    gpu_temp: Callable[[], int | None] = field(default=lambda: None)
    poll_seconds: float = 5.0

    @property
    def global_cap_hours(self) -> float:
        return self.total_usd / self.price_per_hour


# ---------------------------------------------------------------- budget and state
def load_state(path: Path) -> dict[str, Any]:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"cumulative_seconds": 0.0, "stages": {s: {"status": "pending", "seconds": 0.0} for s in STAGES}}


def save_state(path: Path, state: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def stage_hours(stage: str, state: dict[str, Any], cfg: Config) -> float:
    """Hours this stage may still use: its own cap and what is left of the dollar ceiling,
    keeping the evaluation reserve while training."""
    remaining = cfg.global_cap_hours - state["cumulative_seconds"] / 3600
    own = STAGE_CAP_HOURS[stage] - state["stages"][stage]["seconds"] / 3600
    if stage in ("render", "gates", "smoke", "train"):
        later = EVAL_RESERVE_HOURS if stage == "train" else 0.0
        remaining -= later
    return max(0.0, min(remaining, own))


def forecast_training_hours(smoke_receipts: dict[str, dict[str, Any]], load_overhead_seconds: float = 180.0) -> float:
    total = 0.0
    for arm, receipt in smoke_receipts.items():
        steps = max(1, int(receipt["training"]["steps_completed"]))
        per_step = float(receipt["training"]["elapsed_seconds"]) / steps
        total += per_step * int(receipt["planned_full_steps"]) + load_overhead_seconds
    return total / 3600


# ---------------------------------------------------------------- gates
def curriculum_gate_failures(manifest: dict[str, Any]) -> list[str]:
    failures = []
    if manifest.get("schema_version") != "frame_internalization_curriculum_manifest.v1":
        failures.append("manifest schema")
    if manifest.get("passed") is not True:
        failures.append("curriculum completeness/parity (renderer passed=false)")
    if float(manifest.get("f3_pair_total_token_spread", 1.0)) > 0.02:
        failures.append(f"F3 vs F3-concrete token spread {manifest.get('f3_pair_total_token_spread')} > 0.02")
    arms = manifest.get("arms", {})
    if sorted(arms) != sorted(ARMS):
        failures.append("arm set")
    for name, arm in arms.items():
        if int(arm.get("over_4096_count", 1)) != 0:
            failures.append(f"{name}: {arm.get('over_4096_count')} rows over 4,096 tokens (rows are never truncated)")
        if (arm.get("train_count"), arm.get("validation_count")) != (5320, 280):
            failures.append(f"{name}: split counts")
    return failures


def f06_gate_failures(f06_dir: Path) -> list[str]:
    failures = []
    for frame in FRAMES:
        path = f06_dir / f"{frame}.receipt.json"
        if not path.is_file() or json.loads(path.read_text(encoding="utf-8")).get("complete") is not True:
            failures.append(f"F06 receipt for {frame} is not complete")
    return failures


def write_base_freeze(inventory_path: Path, model_dir: Path, out: Path) -> dict[str, Any]:
    """Pod-local base-freeze receipt for the renderer: every artifact hash re-verified."""
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    checks = []
    for item in inventory["artifacts"]:
        p = model_dir / item["path"]
        digest = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
        checks.append({"path": item["path"], "passed": digest == item["sha256"]})
    receipt = {
        "schema_version": "frame_internalization_base_freeze.v1",
        "passed": bool(checks) and all(c["passed"] for c in checks),
        "repository": inventory["repository"], "revision": inventory["revision"],
        "model_dir": str(model_dir.resolve()), "artifact_checks": checks,
        "remote_inventory_sha256": hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
    }
    out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    if not receipt["passed"]:
        raise StageFailure("model artifact hash mismatch on the pod")
    return receipt


# ---------------------------------------------------------------- child processes
def gpu_compute_apps() -> int:
    try:
        out = subprocess.run(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return -1
    return len([l for l in out.splitlines() if l.strip()])


def run_child(cmd: list[str], *, cfg: Config, state: dict[str, Any], state_path: Path, stage: str,
              log_path: Path, seconds_cap: float, env: dict[str, str] | None = None) -> float:
    """Run one command with caps, heartbeat, STOP file, and temperature watch. Returns seconds used."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    last_tick = started
    hot = 0
    last_temp_check = 0.0
    with log_path.open("ab") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env={**os.environ, **(env or {})},
                                start_new_session=True)
        reason = None
        try:
            while proc.poll() is None:
                time.sleep(cfg.poll_seconds)
                now = time.time()
                state["cumulative_seconds"] += now - last_tick
                state["stages"][stage]["seconds"] += now - last_tick
                last_tick = now
                save_state(state_path, state)
                (cfg.work / "heartbeat.json").write_text(json.dumps({
                    "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "stage": stage,
                    "cumulative_hours": state["cumulative_seconds"] / 3600,
                    "cumulative_usd_at_price": state["cumulative_seconds"] / 3600 * cfg.price_per_hour,
                    "stage_seconds": state["stages"][stage]["seconds"], "command": Path(cmd[1]).name if len(cmd) > 1 else cmd[0],
                }, indent=2), encoding="utf-8")
                if (cfg.work / "STOP").exists():
                    reason = "manual_stop"
                elif now - started > seconds_cap:
                    reason = "stage_cap"
                elif state["cumulative_seconds"] / 3600 >= cfg.global_cap_hours:
                    reason = "dollar_cap"
                elif now - last_temp_check >= 60:
                    last_temp_check = now
                    temp = cfg.gpu_temp()
                    hot = hot + 1 if temp is not None and temp >= TEMP_LIMIT_C else 0
                    if hot >= 2:
                        reason = "gpu_temperature"
                if reason:
                    os.killpg(proc.pid, signal.SIGTERM)
                    for _ in range(120):
                        if proc.poll() is not None:
                            break
                        time.sleep(1)
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                    break
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
    tail = time.time() - last_tick
    state["cumulative_seconds"] += tail
    state["stages"][stage]["seconds"] += tail
    save_state(state_path, state)
    if reason:
        raise StageFailure(f"{stage}: stopped by {reason}")
    if proc.returncode != 0:
        raise StageFailure(f"{stage}: command exited {proc.returncode}: {' '.join(Path(c).name for c in cmd[:3])}")
    return time.time() - started


# ---------------------------------------------------------------- stages
def py(cfg: Config, script: str, *args: str, vllm: bool = False) -> list[str]:
    return [str(cfg.vllm_python if vllm else cfg.train_python), str(cfg.repo / "scripts" / script), *args]


def stage_render(cfg: Config, state: dict[str, Any], path: Path) -> None:
    problems = f06_gate_failures(cfg.f06_dir)
    if problems:
        raise StageFailure("; ".join(problems))
    inventory = cfg.repo / PKG / "rerun_freeze/qwen3_1p7b_v1/model_tokenizer_remote_inventory_v1.json"
    write_base_freeze(inventory, cfg.model_dir, cfg.work / "base_freeze_pod.json")
    cap = stage_hours("render", state, cfg) * 3600
    run_child(py(cfg, "render_frame_curricula.py", "--freeze",
                 str(cfg.repo / PKG / "rerun_freeze/qwen3_1p7b_v1/curriculum_generation_v1/request_manifest.json"),
                 "--base-freeze-receipt", str(cfg.work / "base_freeze_pod.json"), "--raw-dir", str(cfg.f06_dir),
                 "--tokenizer", str(cfg.model_dir), "--output-dir", str(cfg.work / "rendered"),
                 "--manifest", str(cfg.work / "curriculum_manifest_v1.json")),
              cfg=cfg, state=state, state_path=path, stage="render", log_path=cfg.work / "logs/render.log", seconds_cap=cap)


def stage_gates(cfg: Config, state: dict[str, Any], path: Path) -> None:
    manifest = json.loads((cfg.work / "curriculum_manifest_v1.json").read_text(encoding="utf-8"))
    failures = curriculum_gate_failures(manifest)
    if failures:
        raise StageFailure("curriculum gate failed: " + "; ".join(failures))
    evals = [PKG + f"/rerun_freeze/evaluation_universes_v2/{n}_queries.jsonl" for n in ("harmful", "benign", "override")]
    evals.append("data/storyworld_sources/constitutional_alignment_20260715_v1/evaluation/mihna_ca_eval_v2.encounter_prompts.jsonl")
    args = ["--curriculum-manifest", str(cfg.work / "curriculum_manifest_v1.json"),
            "--curriculum-dir", str(cfg.work / "rendered"), "--output", str(cfg.work / "nonleakage_audit_v1.json")]
    for e in evals:
        args += ["--evaluation", str(cfg.repo / e)]
    run_child(py(cfg, "audit_frame_curriculum_nonleakage.py", *args), cfg=cfg, state=state, state_path=path,
              stage="gates", log_path=cfg.work / "logs/nonleakage.log", seconds_cap=stage_hours("gates", state, cfg) * 3600)


def train_cmd(cfg: Config, arm: str, out: Path, max_steps: int | None) -> list[str]:
    args = ["train", "--arm", arm, "--train-jsonl", str(cfg.work / "rendered" / arm / "training.jsonl"),
            "--model-dir", str(cfg.model_dir), "--output-dir", str(out)]
    if max_steps:
        args += ["--max-steps", str(max_steps)]
    return py(cfg, "train_frame_internalization_qlora.py", *args)


def stage_smoke(cfg: Config, state: dict[str, Any], path: Path) -> None:
    out = cfg.work / "smoke"
    started = time.time()
    receipts = {}
    for arm in ARMS:
        remaining = min(SMOKE_WALL_SECONDS - (time.time() - started), stage_hours("smoke", state, cfg) * 3600)
        if remaining <= 0:
            raise StageFailure("smoke: the 2 hour cap was reached before all six arms finished")
        run_child(train_cmd(cfg, arm, out, 50), cfg=cfg, state=state, state_path=path, stage="smoke",
                  log_path=cfg.work / f"logs/smoke_{arm}.log", seconds_cap=remaining)
        receipts[arm] = json.loads((out / arm / "arm_receipt.json").read_text(encoding="utf-8"))
    apps = gpu_compute_apps()
    gpu_hours = (time.time() - started) / 3600
    cmd = py(cfg, "train_frame_internalization_qlora.py", "aggregate", "--gpu-hours", f"{gpu_hours:.4f}",
             "--output", str(cfg.work / "training_smoke_receipt_v2.json"))
    for arm in ARMS:
        cmd += ["--arm-receipt", str(out / arm / "arm_receipt.json")]
    if apps == 0:
        cmd.append("--cleanup-passed")
    subprocess.run(cmd, check=False, capture_output=True)
    receipt = json.loads((cfg.work / "training_smoke_receipt_v2.json").read_text(encoding="utf-8"))
    if receipt.get("passed") is not True:
        raise StageFailure(f"smoke receipt failed: {receipt}")
    forecast = forecast_training_hours(receipts)
    train_cap = min(48.0, cfg.global_cap_hours - state["cumulative_seconds"] / 3600 - EVAL_RESERVE_HOURS)
    (cfg.work / "training_forecast.json").write_text(json.dumps(
        {"forecast_hours": forecast, "cap_hours": train_cap, "price_per_hour_usd": cfg.price_per_hour,
         "forecast_usd": forecast * cfg.price_per_hour}, indent=2) + "\n", encoding="utf-8")
    if forecast > train_cap:
        raise StageFailure(f"smoke: two-epoch forecast {forecast:.1f} h exceeds the {train_cap:.1f} h training cap")


def stage_train(cfg: Config, state: dict[str, Any], path: Path) -> None:
    out = cfg.work / "train"
    for arm in ARMS:
        receipt = out / arm / "arm_receipt.json"
        if receipt.is_file() and json.loads(receipt.read_text(encoding="utf-8")).get("complete") is True:
            continue
        cap = stage_hours("train", state, cfg) * 3600
        if cap <= 0:
            raise StageFailure("train: hour or dollar cap reached")
        run_child(train_cmd(cfg, arm, out, None), cfg=cfg, state=state, state_path=path, stage="train",
                  log_path=cfg.work / f"logs/train_{arm}.log", seconds_cap=cap)


def stage_eval(cfg: Config, state: dict[str, Any], path: Path) -> None:
    env = {"VLLM_NO_USAGE_STATS": "1", "DO_NOT_TRACK": "1", "VLLM_ENABLE_V1_MULTIPROCESSING": "0",
           "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    cap = stage_hours("eval", state, cfg) * 3600
    if cap <= 0:
        raise StageFailure("eval: hour or dollar cap reached")
    run_child(py(cfg, "generate_six_arm_eval_vllm.py", "--model-dir", str(cfg.model_dir), "--train-root",
                 str(cfg.work / "train"), "--output-dir", str(cfg.work / "eval"), vllm=True),
              cfg=cfg, state=state, state_path=path, stage="eval", log_path=cfg.work / "logs/eval.log",
              seconds_cap=cap, env=env)
    if not (cfg.work / "eval/eval_receipt.json").is_file():
        raise StageFailure("eval: generation receipt missing")


def stage_analysis(cfg: Config, state: dict[str, Any], path: Path) -> None:
    judged = cfg.work / "judged_rows.jsonl"
    if not judged.is_file():
        (cfg.work / "awaiting_judging.json").write_text(json.dumps({
            "status": "awaiting_judging",
            "reason": "the registered judges are Claude models and need API credentials, which are not on the pod",
            "next": "score work/eval/*.jsonl off the pod, merge judge_refusal into the rows as judged_rows.jsonl, "
                    "then run scripts/analyze_six_arm.py once",
        }, indent=2) + "\n", encoding="utf-8")
        return
    run_child(py(cfg, "analyze_six_arm.py", "--judged-rows", str(judged), "--output", str(cfg.work / "six_arm_results.json")),
              cfg=cfg, state=state, state_path=path, stage="analysis", log_path=cfg.work / "logs/analysis.log",
              seconds_cap=max(60.0, stage_hours("analysis", state, cfg) * 3600))


STAGE_FUNCS: dict[str, Callable[[Config, dict[str, Any], Path], None]] = {
    "render": stage_render, "gates": stage_gates, "smoke": stage_smoke, "train": stage_train,
    "eval": stage_eval, "analysis": stage_analysis,
}


def run_pipeline(cfg: Config, funcs: dict[str, Callable[[Config, dict[str, Any], Path], None]] = STAGE_FUNCS) -> int:
    cfg.work.mkdir(parents=True, exist_ok=True)
    path = cfg.work / "pipeline_state.json"
    state = load_state(path)
    for stage in STAGES:
        entry = state["stages"][stage]
        if entry["status"] == "done":
            continue
        if entry["status"] == "failed":
            print(f"stage {stage} failed earlier: {entry.get('reason')}; not retrying", file=sys.stderr)
            return 3
        entry["status"] = "running"
        save_state(path, state)
        try:
            funcs[stage](cfg, state, path)
        except StageFailure as failure:
            entry["status"], entry["reason"] = "failed", str(failure)
            save_state(path, state)
            (cfg.work / "pipeline_stop.json").write_text(json.dumps({"stage": stage, "reason": str(failure)}, indent=2) + "\n")
            print(f"STOP at {stage}: {failure}", file=sys.stderr)
            return 2
        entry["status"] = "done"
        save_state(path, state)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--f06-dir", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--train-python", type=Path, required=True)
    parser.add_argument("--vllm-python", type=Path, required=True)
    parser.add_argument("--price-per-hour", type=float, required=True)
    parser.add_argument("--total-usd", type=float, default=60.0)
    args = parser.parse_args()
    if args.price_per_hour <= 0:
        raise SystemExit("price per hour must be positive")

    def temp() -> int | None:
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=20).stdout.split()
            return int(out[0])
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            return None

    cfg = Config(args.repo_root, args.f06_dir, args.work, args.model_dir, args.train_python, args.vllm_python,
                 args.price_per_hour, args.total_usd, gpu_temp=temp)
    return run_pipeline(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
