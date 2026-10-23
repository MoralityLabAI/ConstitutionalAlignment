"""Tests for the one hash-pinned scenario exclusion (frame_internalization_failed_scenario_v1)."""

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
import run_six_arm_pipeline as pl  # noqa: E402

PKG = ROOT / "experiments/frame_internalization_sft_v1"
FREEZE = PKG / "rerun_freeze/qwen3_1p7b_v1/curriculum_generation_v1/request_manifest.json"


def lf_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def dilemmas() -> dict[str, dict]:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    rows = [json.loads(l) for l in (ROOT / freeze["dilemmas"]["path"]).read_bytes().decode("utf-8").splitlines() if l.strip()]
    return {r["scenario_id"]: r for r in rows}


def test_amendment_is_pinned_and_consistent_with_the_split() -> None:
    data = fx.load_exclusion()
    assert fx.excluded_scenarios(data) == {"d03508"} and fx.permitted_failed_requests(data) == {"neutral:d03508"}
    assert lf_sha(PKG / "PROTOCOL_AMENDMENT_FAILED_SCENARIO_V1.md") == data["human_readable_sha256_lf"]
    d = dilemmas()
    counts = fx.expected_split_counts(d, {"d03508"})
    assert counts == {"scenarios": 5599, "train": 5319, "val": 280}
    expected = data["expected_counts_per_arm"]
    assert (expected["scenarios"], expected["train"], expected["validation"]) == (5599, 5319, 280)
    assert d["d03508"]["split"] == data["scenario_record"]["split"] == "train"
    assert d["d03508"]["cluster_id"] == data["scenario_record"]["cluster_id"]
    assert fx.expected_split_counts(d, set()) == {"scenarios": 5600, "train": 5320, "val": 280}


def test_any_change_to_the_amendment_is_refused(tmp_path: Path) -> None:
    copy = tmp_path / "a.json"
    data = json.loads(fx.AMENDMENT.read_text(encoding="utf-8"))
    data["decision"]["excluded_scenario_ids"] = ["d03508", "d00001"]
    copy.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(fx.ExclusionError):
        fx.load_exclusion(copy)
    assert fx.load_exclusion(fx.AMENDMENT)["amendment_id"] == "frame_internalization_failed_scenario_v1"


def write_receipts(f06: Path, neutral: dict | None = None, **others: dict) -> None:
    f06.mkdir(exist_ok=True)
    for frame in pl.FRAMES:
        doc = {"scope": "full", "requested": 5600, "completed": 5600, "failed": [], "complete": True}
        if frame == "neutral" and neutral is not None:
            doc = neutral
        doc.update(others.get(frame, {}))
        (f06 / f"{frame}.receipt.json").write_text(json.dumps(doc), encoding="utf-8")


NEUTRAL_FAIL = {"scope": "full", "requested": 5600, "completed": 5599, "failed": ["neutral:d03508"], "complete": False}


def test_generation_gate_accepts_only_the_recorded_failure(tmp_path: Path) -> None:
    exclusion = fx.load_exclusion()
    f06 = tmp_path / "f06"
    write_receipts(f06, NEUTRAL_FAIL)
    assert pl.f06_gate_failures(f06, exclusion) == []
    assert pl.f06_gate_failures(f06, None)  # without the amendment the stop rule stands
    write_receipts(f06, {**NEUTRAL_FAIL, "failed": ["neutral:d00007"]})
    assert pl.f06_gate_failures(f06, exclusion)  # a different scenario
    write_receipts(f06, {**NEUTRAL_FAIL, "completed": 5598, "failed": ["neutral:d03508", "neutral:d00007"]})
    assert pl.f06_gate_failures(f06, exclusion)  # an additional failure
    write_receipts(f06, NEUTRAL_FAIL, F1={"complete": False, "completed": 5599, "failed": ["F1:d03508"]})
    assert pl.f06_gate_failures(f06, exclusion)  # the same scenario in another frame was not permitted
    write_receipts(f06, {**NEUTRAL_FAIL, "completed": 5500})
    assert pl.f06_gate_failures(f06, exclusion)  # silently missing transcripts


def manifest(train=5319, excluded=True, spread=0.01) -> dict:
    arm = {"over_4096_count": 0, "train_count": train, "validation_count": 280}
    return {"schema_version": "frame_internalization_curriculum_manifest.v1", "passed": True,
            "f3_pair_total_token_spread": spread, "arms": {a: dict(arm) for a in pl.ARMS},
            "exclusion": {"amendment_id": "frame_internalization_failed_scenario_v1",
                          "excluded_scenario_ids": ["d03508"]} if excluded else None}


def test_curriculum_gate_uses_the_amended_counts_only_with_the_amendment() -> None:
    exclusion = fx.load_exclusion()
    assert pl.curriculum_gate_failures(manifest(), exclusion) == []
    assert pl.curriculum_gate_failures(manifest(train=5320), exclusion)  # old count is wrong now
    assert pl.curriculum_gate_failures(manifest(), None)  # unexplained exclusion
    assert pl.curriculum_gate_failures(manifest(train=5320, excluded=False), None) == []
    assert pl.curriculum_gate_failures(manifest(train=5319, excluded=False), None)  # 5,319 needs the amendment
    wrong = manifest()
    wrong["exclusion"]["excluded_scenario_ids"] = ["d00001"]
    assert pl.curriculum_gate_failures(wrong, exclusion)
    assert pl.curriculum_gate_failures(manifest(spread=0.03), exclusion)  # parity gate not loosened


def test_launcher_passes_the_pinned_amendment() -> None:
    script = (ROOT / "scripts/stage_and_run_six_arm_after_f06.sh").read_text(encoding="utf-8")
    assert fx.AMENDMENT_SHA256 in script and "--exclusion-amendment" in script


TOKENIZERS = glob.glob(os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub",
                                    "models--Qwen--Qwen3-1.7B-Base", "snapshots", "*"))


@pytest.mark.skipif(not TOKENIZERS, reason="Qwen3 tokenizer not in the local HF cache")
def test_renderer_accepts_only_the_recorded_exclusion(tmp_path: Path) -> None:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    d = dilemmas()
    raw = tmp_path / "raw"
    raw.mkdir()
    prompt_hash = {f: freeze["frames"][f]["prompt_text_sha256"] for f in pl.FRAMES}

    def record(frame: str, sid: str) -> dict:
        row = d[sid]
        msgs = [{"role": r, "content": f"{r} {sid}"} for r in ("user", "assistant") * 3]
        return {"request_id": f"{frame}:{sid}", "scenario_id": sid, "source_frame": frame,
                "source_frame_prompt_sha256": prompt_hash[frame], "dilemma_prompt": row["prompt_text"],
                "cluster_id": row["cluster_id"], "split": row["split"], "transcript": msgs, "final": f"final {sid}"}

    for frame in pl.FRAMES:
        sids = [s for s in sorted(d) if not (frame == "neutral" and s == "d03508")]
        (raw / f"{frame}.jsonl").write_bytes(("\n".join(json.dumps(record(frame, s)) for s in sids) + "\n").encode())
    tok = TOKENIZERS[0]
    receipt = tmp_path / "freeze.json"
    receipt.write_text(json.dumps({"schema_version": "frame_internalization_base_freeze.v1", "passed": True,
                                   "revision": freeze["generation"]["model_revision"],
                                   "model_dir": str(Path(tok).resolve())}), encoding="utf-8")

    def render(out: str, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "scripts/render_frame_curricula.py"), "--freeze", str(FREEZE), "--base-freeze-receipt",
                               str(receipt), "--raw-dir", str(raw), "--tokenizer", tok, "--output-dir", str(tmp_path / out),
                               "--manifest", str(tmp_path / f"{out}.json"), *extra], capture_output=True, text=True)

    no_amendment = render("plain")
    assert no_amendment.returncode != 0 and "incomplete scenario join" in no_amendment.stderr
    with_amendment = render("amended", "--exclusion-amendment", str(fx.AMENDMENT))
    assert with_amendment.returncode == 0, with_amendment.stderr[-800:]
    m = json.loads((tmp_path / "amended.json").read_text(encoding="utf-8"))
    assert m["passed"] and m["exclusion"]["excluded_scenario_ids"] == ["d03508"]
    for arm in m["arms"].values():
        assert (arm["scenario_count"], arm["train_count"], arm["validation_count"]) == (5599, 5319, 280)
        assert arm["maximum_sequence_tokens"] > 2  # real token counts, not len(BatchEncoding)
    assert "d03508" not in (tmp_path / "amended/F1_reflection/training.jsonl").read_text(encoding="utf-8")
    assert pl.curriculum_gate_failures(m, fx.load_exclusion()) == []

    # one more missing transcript (any other scenario) must still stop, even with the amendment
    (raw / "F3.jsonl").write_bytes(b"".join(l + b"\n" for l in (raw / "F3.jsonl").read_bytes().splitlines()[1:]))
    other = render("other", "--exclusion-amendment", str(fx.AMENDMENT))
    assert other.returncode != 0 and "incomplete scenario join" in other.stderr
