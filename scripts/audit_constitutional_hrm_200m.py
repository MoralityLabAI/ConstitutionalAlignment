#!/usr/bin/env python3
"""Audit the v2 HRM architecture without allocating model weights."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.constitutional_metta import (  # noqa: E402
    HrmArchitecture,
    audit_hrm_architecture,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("experiments/constitutional_hrm_200m_v2/model_config.json"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.config.read_text(encoding="utf-8"))
    audit = audit_hrm_architecture(HrmArchitecture.from_mapping(payload["architecture"]))
    receipt = {
        **audit,
        "config_path": str(args.config),
        "architecture_id": payload["architecture_id"],
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if audit["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
