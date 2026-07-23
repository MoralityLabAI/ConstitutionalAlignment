#!/usr/bin/env python3
"""Register a hosted evaluation as a frozen Jinn Bench run."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from jinn_bench import build_run_receipt, load_json, load_registry  # noqa: E402
from jinn_bench.scoring import compare_run_receipts  # noqa: E402

DEFAULT_REGISTRY = REPO_ROOT / "jinn_bench/data/jinn_bench_v1.json"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--traces", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tier", choices=("diagnostic", "promotion"), required=True)
    parser.add_argument("--comparison-protocol-id", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-role", choices=("base", "adapter"), required=True)
    parser.add_argument(
        "--training-method",
        choices=("none", "grpo", "sft", "qlora"),
        required=True,
    )
    parser.add_argument("--checkpoint-step", type=int, required=True)
    parser.add_argument("--adapter-id")
    parser.add_argument("--max-output-tokens", type=int, required=True)
    parser.add_argument("--temperature", type=float, required=True)
    reasoning = parser.add_mutually_exclusive_group(required=True)
    reasoning.add_argument("--thinking", action="store_true")
    reasoning.add_argument("--no-thinking", action="store_true")
    parser.add_argument("--ablation", action="append", required=True)
    parser.add_argument("--incumbent")
    parser.add_argument("--comparison-output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry_path = Path(args.registry).resolve()
    registry = load_registry(registry_path)
    protocol = registry["comparison_protocols"].get(args.comparison_protocol_id)
    if not isinstance(protocol, dict):
        raise ValueError("comparison protocol is not registered")
    expected = {
        "tier": args.tier,
        "thinking_enabled": bool(args.thinking),
        "max_output_tokens": args.max_output_tokens,
        "temperature": args.temperature,
    }
    for key, value in expected.items():
        if protocol.get(key) != value:
            raise ValueError(f"run differs from comparison protocol on {key}")
    receipt = build_run_receipt(
        registry=registry,
        registry_path=registry_path,
        repo_root=REPO_ROOT,
        analysis_path=Path(args.analysis).resolve(),
        trace_path=Path(args.traces).resolve(),
        run_id=args.run_id,
        tier_id=args.tier,
        comparison_protocol_id=args.comparison_protocol_id,
        model_id=args.model_id,
        model_role=args.model_role,
        training_method=args.training_method,
        checkpoint_step=args.checkpoint_step,
        adapter_id=args.adapter_id,
        thinking_enabled=bool(args.thinking),
        max_output_tokens=args.max_output_tokens,
        temperature=args.temperature,
        ablation_ids=list(args.ablation),
    )
    output_path = Path(args.output).resolve()
    write_json(output_path, receipt)
    result: dict = {"run": receipt}
    if args.incumbent:
        if not args.comparison_output:
            raise ValueError("--comparison-output is required with --incumbent")
        incumbent = load_json(Path(args.incumbent).resolve())
        comparison = compare_run_receipts(receipt, incumbent, registry)
        write_json(Path(args.comparison_output).resolve(), comparison)
        result["comparison"] = comparison
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
