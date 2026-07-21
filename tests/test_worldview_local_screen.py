import json
from pathlib import Path

from scripts.analyze_worldview_local_screen_v1 import DECISION


def test_decision_parser_accepts_frozen_contract() -> None:
    match = DECISION.search("Decision: record_and_triage_reserve\nRationale: The record stays reviewable.")
    assert match is not None
    assert match.group(1) == "record_and_triage_reserve"


def test_frozen_probe_suite_is_complete_after_builder_runs() -> None:
    root = Path(__file__).resolve().parent.parent
    manifest_path = root / "experiments/frame_internalization_sft_v1/local_screen_v1/worldview_commutator_probe_manifest_v1.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["probe_count"] == 56
    assert manifest["storyworld_group_count"] == 12
    assert manifest["factual_control_count"] == 8
    assert manifest["interpretation"]["worldview_native_reasoning_claim_available"] is False

