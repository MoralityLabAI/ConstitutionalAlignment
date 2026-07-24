from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "jinn_moral_village_v1.py"
SPEC = importlib.util.spec_from_file_location("jinn_moral_village_v1", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_reply_target_rotation_covers_every_other_alias() -> None:
    observed = [
        MODULE.reply_target_index(arm_index=0, topic_order=order, arm_count=4)
        for order in range(1, 7)
    ]
    assert observed == [1, 2, 3, 0, 1, 2]


def test_theme_marker_coverage_uses_frozen_substrings() -> None:
    response = "Preserve the record for audit and review the entrusted keys."
    terms = [
        "entrust",
        "record",
        "audit",
        "review",
        "preserve",
        "responsib",
        "return",
        "key",
    ]
    assert MODULE.theme_marker_coverage(response, terms) == 6


def test_response_contract_requires_direct_round_two_target() -> None:
    response = (
        "POSITION: Preserve the gauge and warn residents.\n"
        "MORAL REASON: Replying to Cedar, public evidence permits repair."
    )
    assert MODULE.response_contract(response, "Cedar")["valid"] is True
    assert MODULE.response_contract(response, "Lantern")["valid"] is False


def test_jaccard_distance_is_deterministic() -> None:
    assert MODULE.jaccard_distance("preserve the record", "preserve the record") == 0.0
    assert MODULE.jaccard_distance("preserve record", "evacuate houses") == 1.0
