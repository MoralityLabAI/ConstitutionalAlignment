#!/usr/bin/env python3
"""Create a deterministic three-arm blinded packet for persona evaluation v4."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARMS = ("base", "checkpoint_40", "checkpoint_100")
LABELS = ("A", "B", "C")
BLINDING_SALT = "jinn-persona-v4-expanded-three-arm-blinding-410729"


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(f"{path}:{line_number}: expected an object")
            rows.append(value)
    return rows


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def atomic_write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_path = args.responses.resolve()
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"blinding output directory is not empty: {output_dir}")

    rows = load_jsonl(source_path)
    if len(rows) != 288:
        raise ValueError(f"expected 288 response rows, found {len(rows)}")

    by_family: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        family_id = str(row["family_id"])
        arm = str(row["arm"])
        if arm not in ARMS:
            raise ValueError(f"{family_id}: unexpected arm {arm}")
        family = by_family.setdefault(family_id, {})
        if arm in family:
            raise ValueError(f"duplicate response for {family_id}/{arm}")
        family[arm] = row
    if len(by_family) != 96:
        raise ValueError(f"expected 96 independent families, found {len(by_family)}")

    packet_rows: list[dict[str, Any]] = []
    key_rows: list[dict[str, Any]] = []
    for family_id in sorted(by_family):
        family = by_family[family_id]
        if set(family) != set(ARMS):
            raise ValueError(f"incomplete family {family_id}: {sorted(family)}")
        ordered_arms = sorted(
            ARMS,
            key=lambda arm: hashlib.sha256(
                f"{BLINDING_SALT}:{family_id}:{arm}".encode("utf-8")
            ).digest(),
        )
        reference = family[ordered_arms[0]]
        invariant_fields = ("category", "subdimension", "prompt")
        for field in invariant_fields:
            values = {str(row[field]) for row in family.values()}
            if len(values) != 1:
                raise ValueError(f"{family_id}: arm mismatch in {field}")
        packet_rows.append(
            {
                "family_id": family_id,
                "category": reference["category"],
                "subdimension": reference["subdimension"],
                "prompt": reference["prompt"],
                "responses": {
                    label: family[arm]["completion"]
                    for label, arm in zip(LABELS, ordered_arms, strict=True)
                },
            }
        )
        key_rows.append(
            {
                "family_id": family_id,
                "labels": {
                    label: arm
                    for label, arm in zip(LABELS, ordered_arms, strict=True)
                },
            }
        )

    packet_path = output_dir / "blinded_packet.jsonl"
    key_path = output_dir / "blinding_key.jsonl"
    atomic_write_jsonl(packet_path, packet_rows)
    atomic_write_jsonl(key_path, key_rows)
    label_arm_counts = Counter(
        (label, arm)
        for row in key_rows
        for label, arm in row["labels"].items()
    )
    receipt = {
        "schema_version": "jinn_persona_expanded_blinding_receipt_v4",
        "status": "prepared",
        "prepared_at_utc": utc_now(),
        "source_path": str(source_path),
        "source_sha256": sha256_file(source_path),
        "source_rows": len(rows),
        "family_count": len(packet_rows),
        "arm_count": len(ARMS),
        "blinding_algorithm": (
            "For each family, sort arms by SHA-256(salt:family_id:arm), "
            "then map the resulting order to A, B, and C."
        ),
        "blinding_salt_sha256": hashlib.sha256(
            BLINDING_SALT.encode("utf-8")
        ).hexdigest(),
        "packet_sha256": sha256_file(packet_path),
        "key_sha256": sha256_file(key_path),
        "label_arm_counts": {
            label: {
                arm: label_arm_counts[(label, arm)]
                for arm in ARMS
            }
            for label in LABELS
        },
        "response_content_inspected_before_blinding": False,
    }
    atomic_write_json(output_dir / "blinding_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
