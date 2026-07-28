from __future__ import annotations

import hashlib
import json

import pytest

from scripts.run_constitutional_hrm_direct_matrix_v2 import (
    ARMS,
    SEEDS,
    discover_exports,
    summarize_matrix,
)


def _receipt(full: float, removed: float, digest: str) -> dict:
    return {
        "checkpoint": {"sha256": digest},
        "suites": {
            "constitutional_validation": {
                "metrics": {
                    "by_condition": {
                        "constitution_metta_full": {
                            "decision": {"rate": full}
                        },
                        "constitution_hash_only": {
                            "decision": {"rate": removed}
                        },
                        "constitution_removed": {
                            "decision": {"rate": removed}
                        },
                    }
                }
            }
        },
    }


def test_discover_exports_requires_all_hash_bound_jobs(tmp_path) -> None:
    for arm in ARMS:
        for seed in SEEDS:
            job = tmp_path / f"{arm}__seed_{seed}"
            job.mkdir()
            checkpoint = job / "model_step_0000001.pt"
            checkpoint.write_bytes(f"{arm}:{seed}".encode())
            digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
            (job / "model_export.json").write_text(
                json.dumps(
                    {
                        "path": f"/cluster/missing/{checkpoint.name}",
                        "sha256": digest,
                    }
                ),
                encoding="utf-8",
            )
    exports = discover_exports(tmp_path)
    assert len(exports) == 8
    assert all(path.is_file() for path in exports.values())


def test_summary_reports_thresholds_without_authorizing_overnight() -> None:
    receipts = {}
    for arm in ARMS:
        for seed in SEEDS:
            if arm == "constitutional_metta":
                receipts[(arm, seed)] = _receipt(0.85, 0.75, f"{arm}:{seed}")
            elif arm == "constitutional_text_only":
                receipts[(arm, seed)] = _receipt(0.70, 0.65, f"{arm}:{seed}")
            elif arm == "shuffled_control":
                receipts[(arm, seed)] = _receipt(0.50, 0.45, f"{arm}:{seed}")
            else:
                receipts[(arm, seed)] = _receipt(0.55, 0.50, f"{arm}:{seed}")
    summary = summarize_matrix(receipts)
    assert summary["pilot_thresholds_met_for_both_seeds"] is True
    assert summary["pilot_primary"]["713"][
        "metta_delta_over_text_only_removed"
    ] == pytest.approx(0.10)
    assert summary["overnight_spend_authorized"] is False
