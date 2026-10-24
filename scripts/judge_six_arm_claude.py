#!/usr/bin/env python3
"""Registered Claude judges for Study 3 through the Anthropic Message Batches API (amendment judge_v3).

Primary judges: claude-opus-4-8 (StrongREJECT compliance) and claude-sonnet-5 (strict alignment
faking), with the frozen prompts (imported unchanged from scripts/judge_six_arm.py) and the frozen
settings from readiness/judge_configuration_freeze_v1.json: adaptive thinking, effort high,
max_tokens 2,048, JSON-schema output, no sampling parameters, one item per request.

Verdicts already obtained through Prime Inference (status ok) are kept. Only these units are sent:
  - units with no Prime verdict (the unjudged strict alignment-faking units): up to two calls
    (the first, then one retry if unparseable);
  - units whose Prime verdict was unparseable: one call, then missing (counts as not compliant).

Credentials: the anthropic SDK reads ANTHROPIC_API_KEY from the environment by itself. This script
only tests that the variable is non-empty; it never prints, logs or sets it.

Modes: dry-run (no key, sends nothing, estimates cost), run (needs the key; resumable; hard dollar
stop), merge (Prime-ok + new verdicts -> judged_rows.jsonl for scripts/analyze_six_arm.py).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import judge_six_arm as jg  # noqa: E402

MODELS = {"compliance": "claude-opus-4-8", "strict_af": "claude-sonnet-5"}
# USD per million tokens (input, output), standard rates as listed on 2026-10-24; the Batches API is half price.
PRICES = {"claude-opus-4-8": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0)}
BATCH_DISCOUNT = 0.5
DEFAULT_MAX_USD = 60.0
MAX_BATCH_REQUESTS = 2000  # well inside the API's per-batch request limit
POLL_SECONDS = 60


def get(obj: Any, name: str, default: Any = None) -> Any:
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def request_params(unit: dict[str, Any], rubric: str) -> dict[str, Any]:
    """Frozen request: adaptive thinking, effort high, JSON-schema output, no sampling parameters."""
    task = unit["task"]
    return {
        "model": MODELS[task], "max_tokens": jg.MAX_TOKENS,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "high", "format": {"type": "json_schema", "schema": jg.SCHEMAS[task]}},
        "messages": jg.build_messages(unit, rubric),
    }


def cost_usd(model: str, in_tokens: float, out_tokens: float) -> float:
    pi, po = PRICES[model]
    return (in_tokens * pi + out_tokens * po) / 1e6 * BATCH_DISCOUNT


# ------------------------------------------------------------------ planning
def plan_units(units: dict[str, list[dict[str, Any]]], prime: dict[str, dict[str, dict[str, Any]]],
               new: dict[str, dict[str, dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Units still to send, each with `calls_left`: 1 for a Prime-unparseable unit, 2 for a never-judged one."""
    todo: dict[str, list[dict[str, Any]]] = {}
    for task, us in units.items():
        pending = []
        for u in us:
            p, n = prime[task].get(u["uid"]), new[task].get(u["uid"])
            if (p and p["status"] == "ok") or n is not None:
                continue
            pending.append({**u, "max_calls": 1 if p is not None else 2})
        todo[task] = pending
    return todo


def estimate(todo: dict[str, list[dict[str, Any]]], rubrics: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {"tasks": {}, "total_usd": {"expected": 0.0, "worst_case": 0.0}}
    for task, us in todo.items():
        in_tokens = sum(jg.tokens(m["content"]) for u in us for m in jg.build_messages(u, rubrics[task]))
        retry_share = 0.15  # assumed share of first calls that need the retry; unobserved
        extra = sum(1 for u in us if u["max_calls"] == 2) * retry_share
        calls = len(us) + extra
        avg_in = in_tokens / len(us) if us else 0
        expected = cost_usd(MODELS[task], avg_in * calls, jg.ASSUMED_OUTPUT_TOKENS[task] * calls)
        worst_calls = sum(u["max_calls"] for u in us)
        worst = cost_usd(MODELS[task], avg_in * worst_calls, jg.MAX_TOKENS * worst_calls)
        out["tasks"][task] = {"units": len(us), "model": MODELS[task], "input_tokens_first_calls": in_tokens,
                              "assumed_output_tokens_per_call": jg.ASSUMED_OUTPUT_TOKENS[task],
                              "usd_expected": round(expected, 2), "usd_worst_case": round(worst, 2)}
        out["total_usd"]["expected"] = round(out["total_usd"]["expected"] + expected, 2)
        out["total_usd"]["worst_case"] = round(out["total_usd"]["worst_case"] + worst, 2)
    out["note"] = ("Tokens are estimated from character counts (3.5 per token); output and adaptive-thinking tokens are "
                   "assumed. Batch API price is half the standard rate. Worst case sends every call and bills the "
                   "2,048-token ceiling. The run admits only requests whose worst-case cost fits under the hard stop.")
    return out


# ------------------------------------------------------------------ batch running
def result_record(unit: dict[str, Any], entry: Any, calls_done: int) -> tuple[dict[str, Any] | None, dict[str, int]]:
    """Verdict record for a parseable result, else None (to be retried or recorded as missing)."""
    result = get(entry, "result")
    usage = {"input_tokens": 0, "output_tokens": 0}
    if get(result, "type") != "succeeded":
        return None, usage
    message = get(result, "message")
    u = get(message, "usage")
    usage = {"input_tokens": int(get(u, "input_tokens", 0) or 0), "output_tokens": int(get(u, "output_tokens", 0) or 0)}
    text = "".join(get(b, "text", "") or "" for b in (get(message, "content") or []) if get(b, "type") == "text")
    verdict = jg.parse_verdict(unit["task"], text)
    if verdict is None:
        return None, usage
    return {"uid": unit["uid"], "task": unit["task"], "model": MODELS[unit["task"]], "served_model": get(message, "model"),
            "status": "ok", "attempts": calls_done, "verdict": verdict}, usage


def run_task(client: Any, task: str, pending: list[dict[str, Any]], rubric: str, verdict_path: Path,
             state: dict[str, Any], state_path: Path, max_usd: float,
             sleep: Callable[[float], None] = time.sleep, log: Callable[[str], None] = print) -> dict[str, Any]:
    model = MODELS[task]
    calls = state.setdefault("calls", {}).setdefault(task, {})  # persisted so a resume does not grant extra calls
    for u in pending:
        calls.setdefault(u["uid"], 0)
    by_uid = {u["uid"]: u for u in pending}
    remaining = list(by_uid)
    stopped = None
    judged = missing = 0
    while remaining:
        open_batch = next((b for b in state["batches"] if b["task"] == task and not b.get("collected")), None)
        if open_batch is not None:  # resume: collect the batch already submitted instead of paying for it twice
            batch_id, ids = open_batch["id"], open_batch["ids"]
        else:
            sendable, committed = [], 0.0
            for uid in remaining:
                u = by_uid[uid]
                worst = cost_usd(model, jg.tokens(" ".join(m["content"] for m in jg.build_messages(u, rubric))), jg.MAX_TOKENS)
                if len(sendable) >= MAX_BATCH_REQUESTS:
                    break
                if state["spent_usd"] + committed + worst > max_usd:
                    stopped = "dollar_cap"
                    break
                sendable.append(uid)
                committed += worst
            if not sendable:
                stopped = stopped or "dollar_cap"
                break
            ids = {f"r{i}": uid for i, uid in enumerate(sendable)}
            batch = client.messages.batches.create(requests=[
                {"custom_id": cid, "params": request_params(by_uid[uid], rubric)} for cid, uid in ids.items()])
            batch_id = get(batch, "id")
            open_batch = {"id": batch_id, "task": task, "units": len(ids), "ids": ids, "collected": False}
            state["batches"].append(open_batch)
            state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        while get(client.messages.batches.retrieve(batch_id), "processing_status") != "ended":
            sleep(POLL_SECONDS)
        seen = set()
        for entry in client.messages.batches.results(batch_id):
            uid = ids[get(entry, "custom_id")]
            seen.add(uid)
            calls[uid] += 1
            record, usage = result_record(by_uid[uid], entry, calls[uid])
            state["spent_usd"] += cost_usd(model, usage["input_tokens"], usage["output_tokens"])
            if record is None and calls[uid] < by_uid[uid]["max_calls"]:
                continue  # stays in `remaining` for the retry batch
            if record is None:
                record = {"uid": uid, "task": task, "model": model, "status": "missing", "attempts": calls[uid],
                          "error": "no valid verdict after the allowed calls"}
            with verdict_path.open("ab") as handle:
                handle.write((json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            remaining.remove(uid)
            judged += record["status"] == "ok"
            missing += record["status"] == "missing"
        for uid in set(ids.values()) - seen:  # a request with no result entry counts as a failed call
            calls[uid] += 1
            if calls[uid] >= by_uid[uid]["max_calls"]:
                with verdict_path.open("ab") as handle:
                    handle.write((json.dumps({"uid": uid, "task": task, "model": model, "status": "missing", "attempts": calls[uid],
                                              "error": "no result returned"}, sort_keys=True) + "\n").encode("utf-8"))
                remaining.remove(uid)
                missing += 1
        open_batch["collected"] = True
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        log(json.dumps({"task": task, "judged": judged, "missing": missing, "remaining": len(remaining),
                        "spent_usd": round(state["spent_usd"], 2)}))
        if stopped:
            break
    return {"requested": len(pending), "judged_now": judged, "missing_now": missing, "remaining": len(remaining),
            "stopped": stopped, "spent_usd": round(state["spent_usd"], 4)}


# ------------------------------------------------------------------ merge
def combined(prime_dir: Path, out_dir: Path, task: str) -> dict[str, dict[str, Any]]:
    """Prime verdicts, overridden by any new record for the same unit (new records exist only for re-judged units)."""
    merged = jg.load_verdicts(prime_dir / f"verdicts_{task}.jsonl")
    merged.update(jg.load_verdicts(out_dir / f"verdicts_{task}.jsonl"))
    return merged


# ------------------------------------------------------------------ cli
def make_client() -> Any:
    import anthropic

    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY itself


def main(argv: list[str] | None = None, client_factory: Callable[[], Any] = make_client,
         sleep: Callable[[float], None] = time.sleep, env: dict[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["dry-run", "run", "merge"], default="dry-run")
    parser.add_argument("--eval-dir", type=Path, required=True)
    parser.add_argument("--prime-dir", type=Path, required=True, help="directory with the Prime verdict files")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--task", choices=["compliance", "strict_af", "both"], default="both")
    parser.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD)
    args = parser.parse_args(argv)
    if args.max_usd > DEFAULT_MAX_USD:
        raise SystemExit(f"--max-usd may not exceed the amended cap of {DEFAULT_MAX_USD}")
    tasks = ["compliance", "strict_af"] if args.task == "both" else [args.task]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows = jg.load_eval_rows(args.eval_dir)
    texts = jg.question_texts()
    units = {t: jg.select_units(rows, t, texts) for t in tasks}
    prime = {t: jg.load_verdicts(args.prime_dir / f"verdicts_{t}.jsonl") for t in tasks}
    new = {t: {u: r for u, r in jg.load_verdicts(args.out_dir / f"verdicts_{t}.jsonl").items()} for t in tasks}

    if args.mode == "merge":
        both = {t: combined(args.prime_dir, args.out_dir, t) for t in ("compliance", "strict_af")}
        (args.out_dir / "combined").mkdir(exist_ok=True)  # primary verdicts in one place, for the kappa step
        for t, recs in both.items():
            with (args.out_dir / "combined" / f"verdicts_{t}.jsonl").open("wb") as handle:
                for r in recs.values():
                    handle.write((json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        merged = jg.merge_rows(rows, both["compliance"], both["strict_af"])
        with (args.out_dir / "judged_rows.jsonl").open("wb") as handle:
            for r in merged:
                handle.write((json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        accepted = [r for r in merged if r.get("valid") and r.get("tag_accepted")]
        af = [r for r in merged if r.get("valid") and r["universe"] == "harmful" and r["tier"] == "free" and (r.get("reasoning_content") or "").strip()]
        print(json.dumps({"rows": len(merged), "accepted_valid": len(accepted),
                          "accepted_missing_judge": sum(r["judge_refusal"] is None for r in accepted),
                          "af_units": len(af), "af_missing_label": sum(r["af_label"] is None for r in af)}))
        return 0

    rubrics = {t: jg.rubric_text(t) for t in tasks}
    todo = plan_units(units, prime, new)
    if args.mode == "dry-run":
        plan = estimate(todo, rubrics)
        plan["mode"] = "dry-run: nothing was sent, no credential was read"
        plan["hard_stop_usd"] = args.max_usd
        (args.out_dir / "cost_estimate_claude.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(plan, indent=2))
        return 0

    environment = os.environ if env is None else env
    if not environment.get("ANTHROPIC_API_KEY"):  # emptiness test only; the value is never printed or stored
        raise SystemExit("ANTHROPIC_API_KEY is empty: the Claude step is parked")
    state_path = args.out_dir / "batch_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {"spent_usd": 0.0, "batches": []}
    client = client_factory()
    summary = {}
    for task in tasks:
        summary[task] = run_task(client, task, todo[task], rubrics[task], args.out_dir / f"verdicts_{task}.jsonl",
                                 state, state_path, args.max_usd, sleep)
        print(json.dumps({task: summary[task]}), flush=True)
        if summary[task]["stopped"]:
            break
    (args.out_dir / "run_summary_claude.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 0 if not any(s["stopped"] or s["remaining"] for s in summary.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
