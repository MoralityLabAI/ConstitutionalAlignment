#!/usr/bin/env python3
"""Issue an explicit F09A spend authorization bound to a passed F08A package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--f08a-receipt", required=True, type=Path)
    parser.add_argument("--authorized-by", required=True)
    parser.add_argument("--gpu-resource-id", required=True)
    parser.add_argument("--price-per-hour-usd", required=True, type=float)
    parser.add_argument("--max-hours", type=float, default=2.0)
    parser.add_argument("--max-spend-usd", required=True, type=float)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.f08a_receipt.resolve()
    f08a = json.loads(source.read_text(encoding="utf-8"))
    if f08a.get("gate_id") != "F08A_OFFLINE_CLUSTER_PACKAGE":
        raise ValueError("source is not an F08A receipt")
    if f08a.get("status") != "passed":
        raise ValueError("F08A must pass before spend authorization")
    if f08a.get("dataset", {}).get("mode") != "production":
        raise ValueError("authorization must bind the production curriculum")
    computed_ceiling = round(args.price_per_hour_usd * args.max_hours, 2)
    if args.max_hours <= 0 or args.max_hours > 2:
        raise ValueError("max-hours must be in (0, 2]")
    if args.max_spend_usd <= 0 or args.max_spend_usd > computed_ceiling:
        raise ValueError(
            f"max-spend-usd must be positive and no greater than {computed_ceiling}"
        )
    receipt = {
        "schema_version": "constitutional_hrm_f09a_spend_authorization_v2",
        "gate_id": "F09A_TWO_HOUR_SPEND_AUTHORIZATION",
        "status": "authorized",
        "optimizer_launch_authorized": True,
        "authorized_at_utc": datetime.now(timezone.utc).isoformat(),
        "authorized_by": args.authorized_by,
        "resource": {
            "gpu_resource_id": args.gpu_resource_id,
            "gpu_type": "A100_80GB",
            "gpu_count": 8,
            "price_per_hour_usd": args.price_per_hour_usd,
            "max_hours": args.max_hours,
            "max_spend_usd": args.max_spend_usd,
            "computed_two_hour_ceiling_usd": computed_ceiling,
        },
        "sequence": [
            "create capped pod",
            "run F08B one-step live drill on all eight GPUs",
            "verify checkpoints, cgroups, swap, owned PID cleanup, and GPU cleanup",
            "only then launch the two-hour pilot in the same capped pod",
        ],
        "f08a_receipt": {
            "path": str(source),
            "sha256": sha256_file(source),
        },
        "authorized_sha256": f08a["authorized_sha256"],
    }
    atomic_json(args.output.resolve(), receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
