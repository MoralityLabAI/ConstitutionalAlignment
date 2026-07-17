#!/usr/bin/env python3
"""Prove the reviewed packed training corpus contains no development/evaluation rows."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.adapter_training import audit_packed_curriculum_for_training
from alignment_harness.storyworlds import (
    read_json,
    sha256_file,
    sha256_json,
    validate_curriculum_package,
    write_json,
)
from alignment_harness.trajectory_curriculum import read_jsonl


def audit_nonleakage(package_path: Path, packing_manifest_path: Path) -> dict:
    package_path = package_path.resolve()
    packing_manifest_path = packing_manifest_path.resolve()
    package = read_json(package_path)
    package_receipt = validate_curriculum_package(REPO_ROOT, package_path)
    token_recipe = read_json(REPO_ROOT / package["token_recipe"])
    training_recipe = read_json(REPO_ROOT / package["adapter_training_recipe"])
    packing = read_json(packing_manifest_path)
    packed_audit = audit_packed_curriculum_for_training(
        packing_manifest_path, training_recipe, token_recipe
    )
    train_world_ids = {
        str(item["resolved_world_id"])
        for item in package["worlds"]
        if item["source_split"] == "train"
    }
    rows = 0
    world_rows = Counter()
    external_rows = Counter()
    for arm, arm_manifest in packing["arms"].items():
        arm_path = packing_manifest_path.parent / arm_manifest["path"]
        for row in read_jsonl(arm_path):
            rows += 1
            if row.get("source_split") != "train" or not row.get("training_approved"):
                raise ValueError("non-train or provisional row reached packed curriculum")
            if row.get("arm") != arm:
                raise ValueError("packed row arm mismatch during nonleakage audit")
            world_id = row.get("world_id")
            if world_id is None:
                provenance = row.get("external_provenance", {})
                source_id = str(provenance.get("source_id") or provenance.get("campaign_id") or "")
                if not source_id:
                    raise ValueError("external packed row lacks source provenance")
                external_rows[source_id] += 1
            else:
                base_world_id = str(world_id).split("__", 1)[0]
                if base_world_id not in train_world_ids:
                    raise ValueError(f"packed row references a non-train world: {world_id}")
                world_rows[base_world_id] += 1
    split = package_receipt["split_freeze"]
    if split.get("sealed_content_opened") or split["family_counts"]["evaluation"] != 6:
        raise ValueError("split receipt no longer proves six closed evaluation families")
    return {
        "schema_version": "storyworld_training_provenance_nonleakage_v1",
        "package_sha256": sha256_file(package_path),
        "packing_manifest_sha256": sha256_file(packing_manifest_path),
        "packed_curriculum_audit_sha256": sha256_json(packed_audit),
        "packed_rows": rows,
        "train_world_rows": dict(sorted(world_rows.items())),
        "approved_external_rows": dict(sorted(external_rows.items())),
        "source_splits_observed": ["train"],
        "development_rows": 0,
        "evaluation_rows": 0,
        "sealed_family_count": 6,
        "sealed_content_opened": False,
        "input_artifacts": packing["input_artifacts"],
        "claim_boundary": (
            "This proves split/provenance exclusion for the exact packed corpus. It does not "
            "inspect or characterize externally held sealed evaluation content."
        ),
        "passed": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package",
        type=Path,
        default=REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "package.json",
    )
    parser.add_argument("--packing-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = audit_nonleakage(args.package, args.packing_manifest)
    write_json(args.output.resolve(), receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
