#!/usr/bin/env python3
"""Heartbeat, progress log, throughput gate, and caps for the full F06 run.

Launched by scripts/stage_and_run_primelab_f06_full.sh next to the generator
(standard library only). It never touches Prime or any pod. On a violated cap it
writes a marker file and sends SIGTERM to the generator; the wrapper does the
rest. State persists in run_state.json so relaunches keep one cumulative clock.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FRAMES = ("neutral", "F1", "F3", "F3_concrete")
REGISTERED_TRANSCRIPTS = 22400
PLAN_TOKENS_PER_TRANSCRIPT = 34651 / 16  # measured in the batch-8 smoke
GATE_WINDOW_SECONDS = 900
MAX_HOURS = 60.0
MAX_USD = 130.0  # amendment frame_internalization_generation_budget_v2


def parse_utc(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def read_events(path: Path, offset: int) -> tuple[list[dict[str, Any]], int]:
    if not path.is_file():
        return [], offset
    with path.open("rb") as handle:
        handle.seek(offset)
        data = handle.read()
    end = data.rfind(b"\n") + 1  # ignore a line still being written
    events = []
    for line in data[:end].splitlines():
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events, offset + end


def evaluate_gate(calls: list[dict[str, Any]], completed_in_window: int, tokens_completed: int,
                  price_per_hour: float, now: float) -> dict[str, Any] | None:
    """Return None until the window is long enough, else the gate decision.

    ``calls`` are generation_call events seen in this launch. Tokens per second
    is wall-clock: generated tokens over the span from the first call's start to
    the last completed call's end. The projection uses the larger of the
    measured tokens per transcript and the batch-8 smoke figure.
    """
    if not calls:
        return None
    first_start = parse_utc(calls[0]["timestamp_utc"]) - float(calls[0]["elapsed_seconds"])
    last_end = parse_utc(calls[-1]["timestamp_utc"])
    if now - first_start < GATE_WINDOW_SECONDS or last_end - first_start < GATE_WINDOW_SECONDS * 0.5:
        return None
    span = last_end - first_start
    tokens = sum(int(call["generated_tokens"]) for call in calls)
    tps = tokens / span
    measured = tokens_completed / completed_in_window if completed_in_window else 0.0
    per_transcript = max(measured, PLAN_TOKENS_PER_TRANSCRIPT)
    needed = per_transcript * REGISTERED_TRANSCRIPTS
    hours = needed / tps / 3600 if tps > 0 else float("inf")
    usd = hours * price_per_hour
    return {
        "window_seconds": span,
        "generated_tokens": tokens,
        "generated_tokens_per_second": tps,
        "completed_transcripts_in_window": completed_in_window,
        "measured_tokens_per_transcript": measured,
        "tokens_per_transcript_used": per_transcript,
        "projected_generator_hours": hours,
        "price_per_hour_usd": price_per_hour,
        "projected_usd": usd,
        "maximum_hours": MAX_HOURS,
        "maximum_usd": MAX_USD,
        "passed": bool(tps > 0 and hours <= MAX_HOURS and usd <= MAX_USD),
    }


def count_rows(path: Path) -> tuple[int, int]:
    """Completed rows and their generated tokens (tolerates a torn last line)."""
    if not path.is_file():
        return 0, 0
    rows = tokens = 0
    for line in path.read_bytes().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows += 1
        tokens += int(row.get("generated_token_count", 0))
    return rows, tokens


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--generator-pid", type=int, required=True)
    parser.add_argument("--price-per-hour", type=float, required=True)
    parser.add_argument("--maximum-output-bytes", type=int, required=True)
    parser.add_argument("--interval", type=float, default=30.0)
    args = parser.parse_args()
    if args.price_per_hour <= 0:
        raise SystemExit("price per hour must be positive")

    root = args.output_root
    gen_dir = root / "generation"
    events_path = gen_dir / "generation.events.jsonl"
    state_path = root / "run_state.json"
    gate_passed = root / "throughput_gate_passed.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    offset = events_path.stat().st_size if events_path.is_file() else 0
    calls: list[dict[str, Any]] = []
    baseline = {f: count_rows(gen_dir / f"{f}.jsonl") for f in FRAMES}
    last_tick = time.time()
    last_progress = 0.0
    stop_reason: str | None = None

    def alive() -> bool:
        try:
            os.kill(args.generator_pid, 0)
            return True
        except OSError:
            return False

    while alive():
        time.sleep(args.interval)
        now = time.time()
        state["cumulative_seconds"] = float(state.get("cumulative_seconds", 0)) + (now - last_tick)
        last_tick = now
        atomic_write(state_path, state)
        new, offset = read_events(events_path, offset)
        calls += [e for e in new if e.get("event") == "generation_call"]
        counts = {f: count_rows(gen_dir / f"{f}.jsonl") for f in FRAMES}
        total = sum(c[0] for c in counts.values())
        hours = state["cumulative_seconds"] / 3600
        output_bytes = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
        last_tps = None
        if calls:
            span = parse_utc(calls[-1]["timestamp_utc"]) - (
                parse_utc(calls[0]["timestamp_utc"]) - float(calls[0]["elapsed_seconds"]))
            last_tps = sum(int(c["generated_tokens"]) for c in calls) / span if span > 0 else None
        atomic_write(root / "heartbeat.json", {
            "utc": datetime.now(timezone.utc).isoformat(), "generator_alive": True,
            "completed": {f: counts[f][0] for f in FRAMES}, "total_completed": total,
            "registered_total": REGISTERED_TRANSCRIPTS, "cumulative_hours": hours,
            "cumulative_usd_at_price": hours * args.price_per_hour,
            "generated_tokens_per_second_this_launch": last_tps, "output_bytes": output_bytes,
        })
        if now - last_progress >= 60:
            last_progress = now
            with (root / "progress.log").open("a", encoding="utf-8") as log:
                log.write(f"{datetime.now(timezone.utc).isoformat()} completed={total}/{REGISTERED_TRANSCRIPTS} "
                          f"hours={hours:.3f} tps={last_tps if last_tps is None else round(last_tps, 1)}\n")
        if (root / "STOP").exists():
            stop_reason = "manual_stop"
        elif hours >= MAX_HOURS:
            stop_reason = "wall_clock_cap"
        elif hours * args.price_per_hour >= MAX_USD:
            stop_reason = "dollar_cap"
        elif output_bytes > args.maximum_output_bytes:
            stop_reason = "output_cap"
        elif not gate_passed.exists():
            done = sum(counts[f][0] - baseline[f][0] for f in FRAMES)
            toks = sum(counts[f][1] - baseline[f][1] for f in FRAMES)
            decision = evaluate_gate(calls, done, toks, args.price_per_hour, now)
            if decision is not None:
                if decision["passed"]:
                    atomic_write(gate_passed, decision)
                else:
                    atomic_write(root / "throughput_abort.json", decision)
                    stop_reason = "throughput_gate"
        if stop_reason:
            (root / "stop_reason.txt").write_text(stop_reason + "\n", encoding="utf-8")
            os.kill(args.generator_pid, signal.SIGTERM)
            break
    atomic_write(root / "heartbeat.json", {
        "utc": datetime.now(timezone.utc).isoformat(), "generator_alive": False,
        "stop_reason": stop_reason})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
