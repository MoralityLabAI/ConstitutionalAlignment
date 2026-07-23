"""Score candidate storyworld rollouts and emit fail-closed training lanes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from jinn_bench.construct_training import collate_candidate_rollouts  # noqa: E402
from jinn_bench.scoring import load_json, load_jsonl, sha256_file  # noqa: E402

DEFAULT_REGISTRY = REPO_ROOT / "jinn_bench" / "data" / "construct_benchmarks_v1.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert repeated candidate storyworld rollouts into scored gold, "
            "repair, SFT, and preference lanes."
        )
    )
    parser.add_argument("rollouts", type=Path)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--minimum-preference-margin", type=float, default=0.1)
    return parser.parse_args()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def main() -> None:
    args = _parse_args()
    registry = load_json(args.registry)
    if registry.get("schema_version") != "jinn_beast_construct_benchmarks_registry_v1":
        raise ValueError("unsupported construct benchmark registry")
    task_path = REPO_ROOT / registry["data"]["task_path"]
    if sha256_file(task_path) != registry["data"]["task_sha256"]:
        raise ValueError("construct task data hash drift")
    tasks = load_jsonl(task_path)
    rollouts = load_jsonl(args.rollouts)
    result = collate_candidate_rollouts(
        tasks,
        rollouts,
        minimum_preference_margin=args.minimum_preference_margin,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    scored_path = args.output_dir / "scored_rollouts.jsonl"
    sft_path = args.output_dir / "candidate_sft.jsonl"
    preference_path = args.output_dir / "candidate_preferences.jsonl"
    receipt_path = args.output_dir / "collation_receipt.json"
    _write_jsonl(scored_path, result["scored_rollouts"])
    _write_jsonl(sft_path, result["candidate_sft_rows"])
    _write_jsonl(preference_path, result["candidate_preference_rows"])
    receipt = {
        key: value
        for key, value in result.items()
        if key
        not in {
            "scored_rollouts",
            "candidate_sft_rows",
            "candidate_preference_rows",
        }
    }
    receipt["bindings"] = {
        "registry_sha256": sha256_file(args.registry),
        "task_sha256": registry["data"]["task_sha256"],
        "rollouts_sha256": sha256_file(args.rollouts),
    }
    receipt["outputs"] = {
        "scored_rollouts": {
            "path": scored_path.resolve().as_posix(),
            "sha256": sha256_file(scored_path),
            "rows": len(result["scored_rollouts"]),
        },
        "candidate_sft": {
            "path": sft_path.resolve().as_posix(),
            "sha256": sha256_file(sft_path),
            "rows": len(result["candidate_sft_rows"]),
        },
        "candidate_preferences": {
            "path": preference_path.resolve().as_posix(),
            "sha256": sha256_file(preference_path),
            "rows": len(result["candidate_preference_rows"]),
        },
    }
    _write_json(receipt_path, receipt)
    print(receipt_path.resolve().as_posix())


if __name__ == "__main__":
    main()
