"""CPU tests for the vLLM F06 path: seeds, chunking, retries, schema, equivalence check, caps."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_f06_vllm_equivalence as eq  # noqa: E402
import generate_frame_curriculum_vllm as vg  # noqa: E402
import monitor_f06_full as mon  # noqa: E402

PKG = ROOT / "experiments" / "frame_internalization_sft_v1"
AMENDMENT = PKG / "protocol_amendment_generation_vllm_v1.json"
REFERENCE = PKG / "primelab_f06/full_run_attempt_20261023/reference_batch32_nf4"
GENERATION = {
    "turns": ["draft", "critique", "revise"],
    "instructions": {"draft": "D {dilemma}", "critique": "C", "revise": "R"},
    "max_tokens_per_turn": 2500,
    "retry_attempts": 4,
}


def test_seed_rule_pairs_frames_and_varies_turn_and_attempt() -> None:
    assert vg.derive_seed(42, 0, 0) == 42
    assert vg.derive_seed(42, 2, 1) == (42 + 200000 + 1000003) & 0x7FFFFFFF
    seen = {vg.derive_seed(45, t, a) for t in range(3) for a in range(4)}
    assert len(seen) == 12 and all(0 <= s < 2**31 for s in seen)
    assert vg.derive_seed(10**12, 0, 0) < 2**31


def test_chunk_plan_small_first_chunk() -> None:
    jobs = [{"i": i} for i in range(64 + 512 + 10)]
    chunks = vg.plan_chunks(jobs)
    assert [len(c) for c in chunks] == [64, 512, 10]
    assert [j for c in chunks for j in c] == jobs
    with pytest.raises(ValueError):
        vg.plan_chunks(jobs, 0, 5)


def make_batch(frames=("neutral", "F1"), scenarios=(0, 1)):
    batch, dilemmas = [], {}
    for s in scenarios:
        sid = f"d{s:05d}"
        dilemmas[sid] = {"prompt_text": f"dilemma {s}"}
        for f in frames:
            batch.append({"request_id": f"{f}:{sid}", "scenario_id": sid, "source_frame": f,
                          "generation_seed": 42 + s, "cluster_id": "c", "split": "train"})
    return batch, dilemmas


def test_run_chunk_schema_pairing_retry_and_failure() -> None:
    batch, dilemmas = make_batch()
    calls = []

    def generate(prompts, seeds, max_tokens):
        calls.append({"seeds": list(seeds), "n": len(prompts), "max": max_tokens})
        out = []
        for p in prompts:
            if "dilemma 1" in p and len(calls) == 1:  # first draft attempt for scenario 1: empty visible answer
                out.append(("<think>unterminated", 7, "length"))
            else:
                out.append(("<think>x</think> answer text<|im_end|>", 5, "stop"))
        return out

    events = []
    rows, failed = vg.run_chunk(batch, 0, generate, lambda c: json.dumps(c), {"neutral": "N", "F1": "F"},
                                dilemmas, GENERATION, events.append)
    assert failed == [] and len(rows) == 4
    row = rows[0]
    assert [m["role"] for m in row["transcript"]] == ["user", "assistant"] * 3
    assert row["final"] == "answer text" and row["sampler"] == vg.SAMPLER_NAME
    for key in ("request_id", "scenario_id", "source_frame", "dilemma_prompt", "transcript", "final",
                "final_sha256", "generated_token_count", "generation_seed"):
        assert key in row
    # the retried scenarios were re-run with a different seed on attempt 1
    assert calls[1]["n"] == 2
    assert set(calls[1]["seeds"]) == {vg.derive_seed(43, 0, 1)}
    # paired frames share the seed within a call
    assert calls[0]["seeds"][:2] == [42, 42] and calls[0]["seeds"][2:] == [43, 43]
    retry_events = [e for e in events if e["attempt_index"] > 0]
    assert retry_events and retry_events[0]["batch_size"] == 2
    assert all(e["event"] == "generation_call" for e in events)

    def always_empty(prompts, seeds, max_tokens):
        return [("<think>never closes", 3, "length")] * len(prompts)

    rows2, failed2 = vg.run_chunk(batch, 0, always_empty, lambda c: "p", {"neutral": "N", "F1": "F"},
                                  dilemmas, GENERATION, lambda e: None)
    assert rows2 == [] and sorted(failed2) == sorted(r["request_id"] for r in batch)


def test_resume_never_duplicates_with_the_shared_helpers(tmp_path: Path) -> None:
    import generate_qwen3_frame_curriculum_transcripts as old

    batch, dilemmas = make_batch()
    rows, _ = vg.run_chunk(batch, 0, lambda p, s, m: [("a b", 2, "stop")] * len(p), lambda c: "p",
                           {"neutral": "N", "F1": "F"}, dilemmas, GENERATION, lambda e: None)
    raw = tmp_path / "neutral.jsonl"
    for row in rows:
        if row["source_frame"] == "neutral":
            old.append_jsonl(raw, row)
    with raw.open("ab") as handle:
        handle.write(b'{"request_id": "neutral:d0')  # torn tail from a crash
    old.repair_torn_tail(raw)
    done = {"neutral": old.load_done(raw), "F1": set()}
    by_frame = {f: [r for r in batch if r["source_frame"] == f] for f in ("neutral", "F1")}
    pending = old.pending_jobs(by_frame, ["neutral", "F1"], done)
    assert [r["request_id"] for r in pending] == ["F1:d00000", "F1:d00001"]


def test_amendment_pins_match_the_reference_files() -> None:
    spec = json.loads(AMENDMENT.read_text(encoding="utf-8"))
    for name, expected in spec["equivalence_check"]["reference"]["sha256"].items():
        data = (REFERENCE / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == expected
    assert spec["caps"]["maximum_wall_clock_hours"] == 30 and spec["caps"]["maximum_usd"] == 80
    assert spec["pinned_software"]["vllm"] == "0.11.0"


def test_ks_sanity() -> None:
    same = [float(i) for i in range(30)]
    assert eq.ks_two_sample(same, same) == (0.0, 1.0)
    d, p = eq.ks_two_sample([float(i) for i in range(30)], [float(i + 100) for i in range(30)])
    assert d == 1.0 and p < 0.01
    _, p_shift = eq.ks_two_sample([float(i) for i in range(32)], [float(i) + 3 for i in range(32)])
    assert p_shift > 0.5


def run_checker(candidate: Path, tmp_path: Path) -> tuple[int, dict]:
    out = tmp_path / "result.json"
    code = subprocess.run([sys.executable, str(ROOT / "scripts/check_f06_vllm_equivalence.py"),
                           "--candidate", str(candidate), "--output", str(out)],
                          capture_output=True, text=True).returncode
    return code, json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}


def copy_reference(dest: Path) -> Path:
    shutil.copytree(REFERENCE, dest)
    return dest


def test_reference_against_itself_passes(tmp_path: Path) -> None:
    code, result = run_checker(REFERENCE, tmp_path)
    assert code == 0 and result["passed"], result
    assert set(result["checks"]) == {"B1_tokens_per_transcript_ks", "B2_visible_chars_per_turn_ks",
                                     "B3_completion_rate", "B4_refusal_opening_rate", "B5_retry_rate",
                                     "B6_thinking_marker_leaks", "B7_mean_tokens_ratio",
                                     "B8_frame_length_order"}


def mutate(candidate: Path, fn) -> None:
    for frame in eq.FRAMES:
        path = candidate / f"{frame}.jsonl"
        rows = [json.loads(l) for l in path.read_bytes().decode().splitlines() if l.strip()]
        for row in rows:
            fn(frame, row)
        path.write_bytes(("\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n").encode())


def test_checker_fails_on_length_shift_leak_and_refusal(tmp_path: Path) -> None:
    cand = copy_reference(tmp_path / "length")
    mutate(cand, lambda f, r: r.update(generated_token_count=r["generated_token_count"] * 3))
    code, result = run_checker(cand, tmp_path)
    assert code == 2 and not result["checks"]["B1_tokens_per_transcript_ks"]["passed"]
    assert not result["checks"]["B7_mean_tokens_ratio"]["passed"]

    leak = copy_reference(tmp_path / "leak")

    def add_leak(f, r):
        r["transcript"][1]["content"] += " </think> leaked"

    mutate(leak, add_leak)
    code, result = run_checker(leak, tmp_path)
    assert code == 2 and not result["checks"]["B6_thinking_marker_leaks"]["passed"]

    refusal = copy_reference(tmp_path / "refusal")

    def add_refusal(f, r):
        r["transcript"][1]["content"] = "I'm sorry, but I can't help with that."

    mutate(refusal, add_refusal)
    code, result = run_checker(refusal, tmp_path)
    assert code == 2 and not result["checks"]["B4_refusal_opening_rate"]["passed"]


def test_checker_rejects_wrong_scenarios(tmp_path: Path) -> None:
    cand = copy_reference(tmp_path / "wrong")
    mutate(cand, lambda f, r: r.update(request_id=r["request_id"] + "x"))
    code, _ = run_checker(cand, tmp_path)
    assert code == 3


def test_gate_caps_follow_arguments() -> None:
    def call(ts, elapsed, tokens):
        return {"event": "generation_call", "timestamp_utc": ts, "elapsed_seconds": elapsed, "generated_tokens": tokens}

    now = mon.parse_utc("2026-10-24T10:21:00Z")
    slow = [call("2026-10-24T10:10:00Z", 600, 192_000), call("2026-10-24T10:20:00Z", 600, 192_000)]  # 320 tok/s
    fast = [call("2026-10-24T10:10:00Z", 600, 288_000), call("2026-10-24T10:20:00Z", 600, 288_000)]  # 480 tok/s
    assert mon.evaluate_gate(slow, 160, 160 * 2166, 1.2, now, 30, 80)["passed"] is False  # ~42 h
    ok = mon.evaluate_gate(fast, 240, 240 * 2166, 1.2, now, 30, 80)
    assert ok["passed"] and ok["projected_generator_hours"] < 30 and ok["projected_usd"] < 80
    assert mon.evaluate_gate(fast, 240, 240 * 2166, 3.0, now, 30, 80)["passed"] is False  # over US$80


def test_wrapper_contract() -> None:
    script = (ROOT / "scripts/stage_and_run_primelab_f06_vllm.sh").read_text(encoding="utf-8")
    assert 'vllm_version="0.11.0"' in script and "maximum_hours=30" in script and "maximum_usd=80" in script
    assert script.index('"$checker"') < script.index("full generation start")
    assert "--max-hours" in script and "--max-usd" in script and "setsid nohup" in script
    assert "--limit-per-frame 8" in script and script.count("limit-per-frame") == 1
    assert "PRICE_PER_HOUR" in script and "equivalence_failed" in script
    if shutil.which("bash"):
        result = subprocess.run(["bash", "-n", str(ROOT / "scripts/stage_and_run_primelab_f06_vllm.sh")],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
