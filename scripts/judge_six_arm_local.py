#!/usr/bin/env python3
"""Local Qwen3-8B judge for Study 3 (amendment frame_internalization_judge_v2_local).

Replaces the Prime Inference judges of scripts/judge_six_arm.py. Units, rubrics, message text and
verdict parsing are imported from that script unchanged; only the model call differs. One local
judge scores every unit. The earlier Claude verdicts are used only by `--mode agree` (Cohen's kappa).

Modes:
  plan    count units per task; loads no model
  run     judge all units with the local model; resumable (append-only verdicts, fsync per batch)
  merge   write judged_rows.jsonl from the local verdicts only
  agree   Cohen's kappa of local verdicts against the existing Claude verdicts, per task
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent))
import judge_six_arm as jg  # noqa: E402

MODEL_ID = "Qwen/Qwen3-8B"
REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
CACHE_DIR = Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen3-8B"
MAX_NEW_TOKENS = {"compliance": 1024, "strict_af": 64}
RETRY_LINE = "\n\nReply with the JSON object only."
MAX_BATCH_SEQS = 16
MAX_BATCH_TOKENS = 20000  # padded prompt tokens per generate call


class Generator(Protocol):
    def generate(self, messages_batch: list[list[dict[str, str]]], max_new_tokens: int) -> list[str]: ...


# ------------------------------------------------------------------ judging
def judge_batch(generator: Generator, units: list[dict[str, Any]], rubric: str, task: str) -> list[dict[str, Any]]:
    """Greedy pass, then one retry (prompt plus a final instruction line) for unparseable replies."""
    messages = [jg.build_messages(u, rubric) for u in units]
    replies = generator.generate(messages, MAX_NEW_TOKENS[task])
    verdicts = [jg.parse_verdict(task, r) for r in replies]
    attempts = [1] * len(units)
    bad = [i for i, v in enumerate(verdicts) if v is None]
    if bad:
        retry_messages = []
        for i in bad:
            m = [dict(x) for x in messages[i]]
            m[-1]["content"] += RETRY_LINE
            retry_messages.append(m)
        retry_replies = generator.generate(retry_messages, MAX_NEW_TOKENS[task])
        for i, reply in zip(bad, retry_replies):
            attempts[i] = 2
            replies[i] = reply
            verdicts[i] = jg.parse_verdict(task, reply)
    out = []
    for u, reply, verdict, n in zip(units, replies, verdicts, attempts):
        record: dict[str, Any] = {"uid": u["uid"], "task": task, "model": MODEL_ID, "revision": REVISION,
                                  "status": "ok" if verdict is not None else "missing", "attempts": n,
                                  "raw_output": reply[:4000]}
        if verdict is not None:
            record["verdict"] = verdict
        else:
            record["error"] = "unparseable or empty verdict after one retry"
        out.append(record)
    return out


def run_units(generator: Generator, units: list[dict[str, Any]], rubric: str, task: str, verdict_path: Path, *,
              batch_size: int = MAX_BATCH_SEQS, log: Callable[[str], None] = print) -> dict[str, Any]:
    done = jg.load_done(verdict_path)
    todo = sorted((u for u in units if u["uid"] not in done), key=lambda u: (-len(u.get("response") or u.get("scratchpad") or ""), u["uid"]))
    started = time.monotonic()
    counts = {"ok": 0, "missing": 0, "retried": 0}
    for start in range(0, len(todo), batch_size):
        chunk = todo[start : start + batch_size]
        records = judge_batch(generator, chunk, rubric, task)
        with verdict_path.open("ab") as handle:
            for r in records:
                handle.write((json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        for r in records:
            counts[r["status"]] += 1
            counts["retried"] += r["attempts"] == 2
        elapsed = time.monotonic() - started
        finished = start + len(chunk)
        log(json.dumps({"task": task, "done_now": finished, "of": len(todo), "elapsed_s": round(elapsed),
                        "eta_s": round(elapsed / finished * (len(todo) - finished)), **counts}))
    return {"requested": len(units), "already_done": len(units) - len(todo), "judged_now": counts["ok"],
            "missing_now": counts["missing"], "retried_now": counts["retried"], "remaining": 0}


# ------------------------------------------------------------------ agreement
def agree(local_dir: Path, claude_dir: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for task, field in (("compliance", "refusal"), ("strict_af", "label")):
        local = jg.load_verdicts(local_dir / f"verdicts_{task}.jsonl")
        claude = jg.load_verdicts(claude_dir / f"verdicts_{task}.jsonl")
        both = sorted(u for u in local if u in claude and local[u]["status"] == "ok" and claude[u]["status"] == "ok")
        res = jg.agreement(local, claude, task, field)
        table: dict[str, int] = {}
        for u in both:
            key = f"local={local[u]['verdict'][field]}|claude={claude[u]['verdict'][field]}"
            table[key] = table.get(key, 0) + 1
        res.update({"table": dict(sorted(table.items())), "field": field,
                    "local_ok": sum(r["status"] == "ok" for r in local.values()),
                    "claude_ok": sum(r["status"] == "ok" for r in claude.values()),
                    "local_units": len(local), "claude_units": len(claude)})
        res.pop("units_missing_in_either", None)
        res["note"] = ("local judge vs the earlier Claude verdicts on units where both parse; the Claude verdicts are "
                       "never part of the analysis input (amendment frame_internalization_judge_v2_local)")
        if task == "compliance" and res.get("n"):
            res["below_registered_validity_floor_0_60"] = bool(res["kappa"] < 0.60)
        out[task] = res
    return out


# ------------------------------------------------------------------ real model
def locate_snapshot(cache_dir: Path = CACHE_DIR, revision: str = REVISION) -> Path:
    snap = cache_dir / "snapshots" / revision
    if not (snap / "model.safetensors.index.json").is_file():
        raise SystemExit(f"Qwen3-8B revision {revision} has no weights at {snap}; fetch that revision first")
    index = json.loads((snap / "model.safetensors.index.json").read_text(encoding="utf-8"))
    missing = sorted({f for f in index["weight_map"].values() if not (snap / f).is_file()})
    if missing:
        raise SystemExit(f"missing shards at {snap}: {missing}")
    return snap


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 24), b""):
            h.update(block)
    return h.hexdigest()


class HfGenerator:
    """Qwen3-8B in NF4 on the GPU, greedy decoding, chat template with thinking off."""

    def __init__(self, snapshot: Path) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(snapshot, padding_side="left")
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16,
                                   bnb_4bit_use_double_quant=False)
        self.model = AutoModelForCausalLM.from_pretrained(snapshot, quantization_config=quant, dtype=torch.bfloat16,
                                                          device_map={"": 0}, low_cpu_mem_usage=True)
        self.model.eval()

    def _texts(self, messages_batch: list[list[dict[str, str]]]) -> list[str]:
        return [self.tokenizer.apply_chat_template(m, tokenize=False, add_generation_prompt=True, enable_thinking=False)
                for m in messages_batch]

    def generate(self, messages_batch: list[list[dict[str, str]]], max_new_tokens: int) -> list[str]:
        texts = self._texts(messages_batch)
        lengths = [len(self.tokenizer(t, add_special_tokens=False)["input_ids"]) for t in texts]
        order = sorted(range(len(texts)), key=lambda i: -lengths[i])
        results: dict[int, str] = {}
        group: list[int] = []
        for i in order:
            if group and (len(group) + 1) * lengths[group[0]] > MAX_BATCH_TOKENS:
                results.update(self._run(group, texts, max_new_tokens))
                group = []
            group.append(i)
        if group:
            results.update(self._run(group, texts, max_new_tokens))
        return [results[i] for i in range(len(texts))]

    def _run(self, idx: list[int], texts: list[str], max_new_tokens: int) -> dict[int, str]:
        torch = self.torch
        oom = False
        try:
            enc = self.tokenizer([texts[i] for i in idx], return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")
            with torch.inference_mode():
                out = self.model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False, temperature=None,
                                          top_p=None, top_k=None, pad_token_id=self.tokenizer.pad_token_id)
            new = out[:, enc["input_ids"].shape[1]:]
            return {i: self.tokenizer.decode(row, skip_special_tokens=True) for i, row in zip(idx, new)}
        except torch.cuda.OutOfMemoryError:
            if len(idx) == 1:
                raise
            oom = True
        assert oom
        torch.cuda.empty_cache()  # outside the except block so the failed batch's tensors can be freed
        half = len(idx) // 2
        return {**self._run(idx[:half], texts, max_new_tokens), **self._run(idx[half:], texts, max_new_tokens)}


def receipt(snapshot: Path, args: argparse.Namespace) -> dict[str, Any]:
    import torch
    import transformers

    index = json.loads((snapshot / "model.safetensors.index.json").read_text(encoding="utf-8"))
    shards = sorted(set(index["weight_map"].values()))
    return {"model": MODEL_ID, "revision": REVISION, "snapshot": str(snapshot),
            "shard_sha256": {s: sha256_file(snapshot / s) for s in shards},
            "quantization": "bitsandbytes NF4, bf16 compute, no double quant", "decoding": "greedy, enable_thinking=False",
            "max_new_tokens": MAX_NEW_TOKENS, "max_batch_seqs": args.batch_size, "max_batch_tokens": MAX_BATCH_TOKENS,
            "torch": torch.__version__, "transformers": transformers.__version__,
            "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


# ------------------------------------------------------------------ cli
def main(argv: list[str] | None = None, generator_factory: Callable[[Path], Generator] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["plan", "run", "merge", "agree"], default="plan")
    parser.add_argument("--eval-dir", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--claude-dir", type=Path, help="the Prime run's verdict directory (agree only)")
    parser.add_argument("--task", choices=["compliance", "strict_af", "both"], default="both")
    parser.add_argument("--batch-size", type=int, default=MAX_BATCH_SEQS)
    parser.add_argument("--limit", type=int, default=0, help="judge only the first N units per task (smoke runs)")
    parser.add_argument("--snapshot", type=Path, default=None)
    args = parser.parse_args(argv)
    tasks = ["compliance", "strict_af"] if args.task == "both" else [args.task]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.mode == "agree":
        if args.claude_dir is None:
            raise SystemExit("--claude-dir is required")
        result = agree(args.out_dir, args.claude_dir)
        (args.out_dir / "judge_agreement.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0

    if args.eval_dir is None:
        raise SystemExit("--eval-dir is required")
    rows = jg.load_eval_rows(args.eval_dir)
    texts = jg.question_texts()
    units = {t: jg.select_units(rows, t, texts) for t in tasks}
    if args.limit:
        units = {t: u[: args.limit] for t, u in units.items()}

    if args.mode == "plan":
        print(json.dumps({t: len(u) for t, u in units.items()}))
        return 0

    if args.mode == "merge":
        merged = jg.merge_rows(rows, jg.load_verdicts(args.out_dir / "verdicts_compliance.jsonl"),
                               jg.load_verdicts(args.out_dir / "verdicts_strict_af.jsonl"))
        with (args.out_dir / "judged_rows.jsonl").open("wb") as handle:
            for r in merged:
                handle.write((json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        accepted = [r for r in merged if r.get("valid") and r.get("tag_accepted")]
        print(json.dumps({"rows": len(merged), "accepted_valid": len(accepted),
                          "accepted_missing_judge": sum(r["judge_refusal"] is None for r in accepted)}))
        return 0

    rubrics = {t: jg.rubric_text(t) for t in tasks}
    snapshot = args.snapshot or (locate_snapshot() if generator_factory is None else Path("."))
    if generator_factory is None and snapshot.name != REVISION:
        raise SystemExit(f"snapshot folder {snapshot.name} is not the registered revision {REVISION}")
    if generator_factory is None:
        rec_path = args.out_dir / "local_judge_receipt.json"
        if not rec_path.is_file():
            rec_path.write_text(json.dumps(receipt(snapshot, args), indent=2) + "\n", encoding="utf-8")
        generator = HfGenerator(snapshot)
    else:
        generator = generator_factory(snapshot)
    summary = {}
    for task in tasks:
        summary[task] = run_units(generator, units[task], rubrics[task], task, args.out_dir / f"verdicts_{task}.jsonl",
                                  batch_size=args.batch_size)
        print(json.dumps({task: summary[task]}), flush=True)
    (args.out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
