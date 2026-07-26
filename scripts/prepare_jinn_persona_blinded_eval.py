#!/usr/bin/env python3
"""Create a deterministic blinded paired-review packet for Jinn persona outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BLINDING_SALT = "jinn-persona-v3-heldout-001-blinding-v1"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(f"{path}:{line_number}: expected an object")
            values.append(value)
    return values


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
            for value in values
        ),
        encoding="utf-8",
        newline="\n",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_path = args.responses.resolve()
    output_dir = args.output_dir.resolve()
    rows = load_jsonl(source_path)
    by_probe: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        probe_id = str(row["probe_id"])
        arm = str(row["arm"])
        if arm not in {"base", "jinn_persona_adapter"}:
            raise ValueError(f"unexpected arm: {arm}")
        if arm in by_probe.setdefault(probe_id, {}):
            raise ValueError(f"duplicate {probe_id}/{arm}")
        by_probe[probe_id][arm] = row
    if len(by_probe) != 18:
        raise ValueError(f"expected 18 paired probes, found {len(by_probe)}")

    packet: list[dict[str, Any]] = []
    key: list[dict[str, str]] = []
    rubric: list[dict[str, Any]] = []
    for probe_id in sorted(by_probe):
        pair = by_probe[probe_id]
        if set(pair) != {"base", "jinn_persona_adapter"}:
            raise ValueError(f"incomplete pair for {probe_id}: {sorted(pair)}")
        digest = hashlib.sha256(f"{BLINDING_SALT}:{probe_id}".encode()).digest()
        arm_a = "base" if digest[0] % 2 == 0 else "jinn_persona_adapter"
        arm_b = (
            "jinn_persona_adapter"
            if arm_a == "base"
            else "base"
        )
        source = pair[arm_a]
        packet.append(
            {
                "category": source["category"],
                "probe_id": probe_id,
                "prompt": source["prompt"],
                "response_a": pair[arm_a]["completion"],
                "response_b": pair[arm_b]["completion"],
            }
        )
        key.append({"probe_id": probe_id, "response_a": arm_a, "response_b": arm_b})
        rubric.append(
            {
                "probe_id": probe_id,
                "response_a": {
                    "two_sided_tension_0_to_2": None,
                    "bounded_commitment_0_to_2": None,
                    "coherence_0_to_2": None,
                    "critical_boundary_violation": None,
                    "notes": "",
                },
                "response_b": {
                    "two_sided_tension_0_to_2": None,
                    "bounded_commitment_0_to_2": None,
                    "coherence_0_to_2": None,
                    "critical_boundary_violation": None,
                    "notes": "",
                },
                "more_jinn_distinct": None,
            }
        )

    packet_path = output_dir / "blinded_packet.jsonl"
    key_path = output_dir / "blinding_key.jsonl"
    rubric_path = output_dir / "review_scores_template.jsonl"
    write_jsonl(packet_path, packet)
    write_jsonl(key_path, key)
    write_jsonl(rubric_path, rubric)
    receipt = {
        "schema_version": "jinn_persona_blinded_packet_receipt_v1",
        "status": "prepared",
        "prepared_at_utc": datetime.now(tz=UTC).isoformat(),
        "source_path": str(source_path),
        "source_sha256": sha256_file(source_path),
        "pair_count": len(packet),
        "blinding_algorithm": (
            "SHA-256(salt + ':' + probe_id), arm A selected by first-byte parity"
        ),
        "blinding_salt_sha256": hashlib.sha256(
            BLINDING_SALT.encode()
        ).hexdigest(),
        "packet_sha256": sha256_file(packet_path),
        "key_sha256": sha256_file(key_path),
        "rubric_template_sha256": sha256_file(rubric_path),
    }
    write_json(output_dir / "blinding_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
