"""CPU tests for resume, the throughput gate, and the full-run wrapper (no GPU, no pod)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import generate_qwen3_frame_curriculum_transcripts as gen  # noqa: E402
import monitor_f06_full as mon  # noqa: E402

PKG = ROOT / "experiments" / "frame_internalization_sft_v1"
MANIFEST = PKG / "rerun_freeze/qwen3_1p7b_v1/curriculum_generation_v1/request_manifest.json"


def reqs(frame: str, n: int) -> list[dict]:
    return [{"request_id": f"{frame}-{i}", "source_frame": frame} for i in range(n)]


def test_pending_jobs_skips_done_and_never_duplicates() -> None:
    frames = ["neutral", "F1"]
    by_frame = {f: reqs(f, 5) for f in frames}
    done = {"neutral": {"neutral-0", "neutral-1"}, "F1": {"F1-0"}}
    jobs = gen.pending_jobs(by_frame, frames, done)
    ids = [j["request_id"] for j in jobs]
    assert len(ids) == len(set(ids)) == 10 - 3
    assert not set(ids) & {"neutral-0", "neutral-1", "F1-0"}
    # interleaved, the same order as a fresh run
    assert ids[:3] == ["F1-1", "neutral-2", "F1-2"]
    assert gen.pending_jobs(by_frame, frames, {f: {r["request_id"] for r in by_frame[f]} for f in frames}) == []


def test_resume_after_torn_write(tmp_path: Path) -> None:
    raw = tmp_path / "F1.jsonl"
    good = [json.dumps({"request_id": f"F1-{i}"}) + "\n" for i in range(3)]
    raw.write_bytes(("".join(good) + '{"request_id": "F1-3", "transc').encode())
    dropped = gen.repair_torn_tail(raw)
    assert dropped > 0 and raw.read_bytes() == "".join(good).encode()
    assert gen.load_done(raw) == {"F1-0", "F1-1", "F1-2"}
    # a terminated but unparsable last line is also dropped; intact files are untouched
    raw.write_bytes(("".join(good) + "garbage\n").encode())
    assert gen.repair_torn_tail(raw) == len("garbage\n")
    assert gen.repair_torn_tail(raw) == 0
    # the interrupted transcript is regenerated exactly once
    by_frame = {"F1": reqs("F1", 5)}
    ids = [j["request_id"] for j in gen.pending_jobs(by_frame, ["F1"], {"F1": gen.load_done(raw)})]
    assert ids == ["F1-3", "F1-4"]


def test_load_done_rejects_duplicates(tmp_path: Path) -> None:
    raw = tmp_path / "x.jsonl"
    raw.write_text('{"request_id": "a"}\n{"request_id": "a"}\n', encoding="utf-8")
    with pytest.raises(RuntimeError):
        gen.load_done(raw)


def call(ts: str, elapsed: float, tokens: int) -> dict:
    return {"event": "generation_call", "timestamp_utc": ts, "elapsed_seconds": elapsed, "generated_tokens": tokens}


def test_gate_waits_for_the_15_minute_window() -> None:
    calls = [call("2026-10-24T10:05:00Z", 300, 90_000)]
    now = mon.parse_utc("2026-10-24T10:10:00Z")
    assert mon.evaluate_gate(calls, 32, 70_000, 1.2, now) is None


def test_gate_passes_at_registered_throughput() -> None:
    # 320 tokens/s over 20 minutes -> about 42 h, about US$51 at 1.2/h
    calls = [call("2026-10-24T10:10:00Z", 600, 192_000), call("2026-10-24T10:20:00Z", 600, 192_000)]
    now = mon.parse_utc("2026-10-24T10:21:00Z")
    decision = mon.evaluate_gate(calls, 160, 160 * 2166, 1.2, now)
    assert decision and decision["passed"] and decision["projected_generator_hours"] < 60
    assert decision["projected_usd"] < 75


def test_gate_aborts_below_threshold_or_over_price() -> None:
    slow = [call("2026-10-24T10:10:00Z", 600, 72_000), call("2026-10-24T10:20:00Z", 600, 72_000)]  # 120 tok/s
    now = mon.parse_utc("2026-10-24T10:21:00Z")
    decision = mon.evaluate_gate(slow, 64, 64 * 2166, 1.2, now)
    assert decision and not decision["passed"] and decision["projected_generator_hours"] > 60
    fast = [call("2026-10-24T10:10:00Z", 600, 192_000), call("2026-10-24T10:20:00Z", 600, 192_000)]
    expensive = mon.evaluate_gate(fast, 160, 160 * 2166, 2.0, now)  # about 42 h but US$84
    assert expensive and not expensive["passed"] and expensive["projected_usd"] > 75


def test_gate_uses_measured_tokens_when_longer_than_smoke() -> None:
    calls = [call("2026-10-24T10:10:00Z", 600, 192_000), call("2026-10-24T10:20:00Z", 600, 192_000)]
    now = mon.parse_utc("2026-10-24T10:21:00Z")
    longer = mon.evaluate_gate(calls, 100, 100 * 4000, 1.0, now)
    base = mon.evaluate_gate(calls, 100, 100 * 2000, 1.0, now)
    assert longer["projected_generator_hours"] > base["projected_generator_hours"]


def test_read_events_ignores_a_line_still_being_written(tmp_path: Path) -> None:
    path = tmp_path / "e.jsonl"
    path.write_bytes((json.dumps({"event": "a"}) + "\n" + '{"event": "b"').encode())
    events, offset = mon.read_events(path, 0)
    assert [e["event"] for e in events] == ["a"]
    path.write_bytes(path.read_bytes() + b"}\n")
    more, _ = mon.read_events(path, offset)
    assert [e["event"] for e in more] == ["b"]


def test_frozen_pins_in_the_wrapper_match_the_repo() -> None:
    script = (ROOT / "scripts/stage_and_run_primelab_f06_full.sh").read_text(encoding="utf-8")
    freeze = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert freeze["requests"]["sha256"] in script
    assert "--batch-size \"$batch_size\"" in script and "batch_size=32" in script
    assert "limit-per-frame" not in script
    assert "maximum_hours=60" in script


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_wrapper_syntax() -> None:
    result = subprocess.run(["bash", "-n", str(ROOT / "scripts/stage_and_run_primelab_f06_full.sh")],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
