"""Score a complete Jinn/Beast construct benchmark response export."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from jinn_bench.construct_scoring import build_construct_run_receipt  # noqa: E402
from jinn_bench.scoring import load_json, load_jsonl, sha256_file  # noqa: E402

DEFAULT_REGISTRY = REPO_ROOT / "jinn_bench" / "data" / "construct_benchmarks_v1.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Score exact-JSON model completions against the separate Jinn-ness "
            "and Beast-from-the-Earth construct tasks."
        )
    )
    parser.add_argument("responses", type=Path)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument(
        "--split",
        choices=("development", "candidate_train"),
        default="development",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _bound_tasks(registry: dict[str, Any], registry_path: Path) -> list[dict[str, Any]]:
    if registry.get("schema_version") != "jinn_beast_construct_benchmarks_registry_v1":
        raise ValueError(f"{registry_path}: unsupported construct registry")
    task_path = REPO_ROOT / registry["data"]["task_path"]
    if sha256_file(task_path) != registry["data"]["task_sha256"]:
        raise ValueError("construct task data hash drift")
    return load_jsonl(task_path)


def main() -> None:
    args = _parse_args()
    registry = load_json(args.registry)
    tasks = _bound_tasks(registry, args.registry)
    responses = load_jsonl(args.responses)
    receipt = build_construct_run_receipt(tasks, responses, split=args.split)
    receipt["bindings"] = {
        "registry_path": args.registry.resolve().as_posix(),
        "registry_sha256": sha256_file(args.registry),
        "responses_path": args.responses.resolve().as_posix(),
        "responses_sha256": sha256_file(args.responses),
        "task_sha256": registry["data"]["task_sha256"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": args.output.resolve().as_posix(),
                "rollouts": receipt["rollouts"],
                "metrics_by_construct": receipt["metrics_by_construct"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
