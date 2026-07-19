#!/usr/bin/env python3
"""Run one resumable Mizan Rooms condition/seed task."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.mizan_rooms import (
    CommandPolicy,
    OpenAICompatiblePolicy,
    ScriptedPolicy,
    run_experiment,
    sha256_file,
    validate_package,
)

DEFAULT_SUITE = "experiments/mizan_rooms_v1/suite.json"
DEFAULT_ANALYSIS_PLAN = "papers/mizan_rooms_preanalysis_v2.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default=DEFAULT_SUITE)
    parser.add_argument("--condition", required=True)
    parser.add_argument("--split", choices=("development", "evaluation"), default="development")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--blinding-seed", type=int, default=20260716)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--policy",
        choices=("scripted", "openai-compatible", "command"),
        default="scripted",
    )
    parser.add_argument("--scripted-strategy", choices=("first", "middle", "last"), default="first")
    parser.add_argument("--model-id", default=os.getenv("MIZAN_MODEL"))
    parser.add_argument("--api-base", default=os.getenv("MIZAN_API_BASE"))
    parser.add_argument("--api-key-env", default="MIZAN_API_KEY")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--max-tokens", type=int, default=180)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--no-response-format", action="store_true")
    parser.add_argument("--no-api-seed", action="store_true")
    parser.add_argument("--agent-command", default=os.getenv("MIZAN_AGENT_COMMAND"))
    parser.add_argument("--unseal-evaluation", action="store_true")
    parser.add_argument("--analysis-plan", default=DEFAULT_ANALYSIS_PLAN)
    parser.add_argument("--analysis-plan-sha256")
    return parser.parse_args()


def build_policy(args: argparse.Namespace):
    if args.policy == "scripted":
        return ScriptedPolicy(strategy=args.scripted_strategy)
    if not args.model_id:
        raise ValueError("--model-id or MIZAN_MODEL is required for non-scripted policies")
    if args.policy == "openai-compatible":
        if not args.api_base:
            raise ValueError("--api-base or MIZAN_API_BASE is required")
        return OpenAICompatiblePolicy(
            api_base=args.api_base,
            api_key=os.getenv(args.api_key_env),
            model_id=args.model_id,
            temperature=args.temperature,
            top_p=args.top_p,
            max_tokens=args.max_tokens,
            timeout_seconds=args.timeout_seconds,
            retries=args.retries,
            use_response_format=not args.no_response_format,
            use_generation_seed=not args.no_api_seed,
        )
    if not args.agent_command:
        raise ValueError("--agent-command or MIZAN_AGENT_COMMAND is required")
    return CommandPolicy.from_text(
        args.agent_command,
        model_id=args.model_id,
        timeout_seconds=args.timeout_seconds,
    )


def enforce_evaluation_gate(args: argparse.Namespace) -> None:
    if args.split != "evaluation":
        return
    if not args.unseal_evaluation:
        raise ValueError("evaluation split is sealed; pass --unseal-evaluation after freezing choices")
    plan_path = REPO_ROOT / args.analysis_plan
    if not plan_path.is_file():
        raise ValueError(f"analysis plan not found: {plan_path}")
    actual_hash = sha256_file(plan_path)
    if args.analysis_plan_sha256 != actual_hash:
        raise ValueError(
            "evaluation requires the exact frozen --analysis-plan-sha256; "
            f"current plan hash is {actual_hash}"
        )
    protected_paths = [
        args.suite,
        "experiments/mizan_rooms_v1",
        "schemas/mizan_room_v1.schema.json",
        "alignment_harness/mizan_rooms.py",
        "scripts/run_mizan_rooms.py",
        "scripts/analyze_mizan_rooms.py",
        args.analysis_plan,
    ]
    status = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            *protected_paths,
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if status.returncode != 0 or status.stdout.strip():
        raise ValueError(
            "evaluation requires every protected package path to be tracked and clean at HEAD"
        )


def main() -> int:
    args = parse_args()
    suite_path = REPO_ROOT / args.suite
    validate_package(REPO_ROOT, suite_path)
    enforce_evaluation_gate(args)
    manifest = run_experiment(
        repo_root=REPO_ROOT,
        suite_path=suite_path,
        output_dir=Path(args.output_dir),
        policy=build_policy(args),
        condition_id=args.condition,
        source_split=args.split,
        seed=args.seed,
        replicates=args.replicates,
        blinding_seed=args.blinding_seed,
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
