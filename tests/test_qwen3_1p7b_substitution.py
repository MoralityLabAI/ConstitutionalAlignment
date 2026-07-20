import hashlib
import json
from pathlib import Path

from scripts.audit_qwen3_1p7b_local_runtime import verify_artifacts
from scripts.freeze_qwen3_1p7b_inventory import EXPECTED_FILES, artifact_kind
from scripts.validate_frame_prompt_sft_contrast_v3 import validate


def test_qwen_inventory_file_universe_and_kinds_are_exact():
    assert len(EXPECTED_FILES) == 12
    assert len(set(EXPECTED_FILES)) == len(EXPECTED_FILES)
    assert [name for name in EXPECTED_FILES if artifact_kind(name) == "weight"] == [
        "model-00001-of-00002.safetensors",
        "model-00002-of-00002.safetensors",
    ]
    assert artifact_kind("tokenizer.json") == "tokenizer"
    assert artifact_kind("LICENSE") == "license"


def test_local_artifact_verifier_fails_closed_on_hash_drift(tmp_path: Path):
    payload = b"exact model bytes"
    path = tmp_path / "model.safetensors"
    path.write_bytes(payload)
    inventory = {
        "artifact_count": 1,
        "artifacts": [
            {
                "path": path.name,
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        ],
    }
    checks = verify_artifacts(inventory, tmp_path)
    assert checks == [
        {
            "path": path.name,
            "expected_size_bytes": len(payload),
            "observed_size_bytes": len(payload),
            "expected_sha256": hashlib.sha256(payload).hexdigest(),
            "observed_sha256": hashlib.sha256(payload).hexdigest(),
            "passed": True,
        }
    ]
    path.write_bytes(b"drift model bytes")
    drifted = verify_artifacts(inventory, tmp_path)
    assert drifted[0]["passed"] is False


def test_generated_qwen_inventory_has_expected_identity_when_present():
    path = (
        Path(__file__).resolve().parents[1]
        / "experiments/frame_internalization_sft_v1/rerun_freeze/qwen3_1p7b_v1/"
        "model_tokenizer_remote_inventory_v1.json"
    )
    if not path.is_file():
        return
    inventory = json.loads(path.read_text(encoding="utf-8"))
    assert inventory["repository"] == "Qwen/Qwen3-1.7B"
    assert inventory["revision"] == "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
    assert inventory["license"] == "apache-2.0"
    assert inventory["artifact_count"] == 12
    assert inventory["weight_shard_count"] == 2
    assert inventory["chat_template"]["supports_enable_thinking"] is True
    assert inventory["historical_boundary"]["reproduces_historical_intellect_3_result"] is False


def test_qwen_prompt_sft_contract_and_substitution_validate_when_present():
    root = Path(__file__).resolve().parents[1]
    contract = (
        root
        / "experiments/frame_internalization_sft_v1/"
        "prompt_sft_contrast_v3_qwen3_1p7b.json"
    )
    if not contract.is_file():
        return
    receipt = validate(contract)
    assert receipt["passed"] is True, receipt["failures"]
    assert all(receipt["checks"].values())
