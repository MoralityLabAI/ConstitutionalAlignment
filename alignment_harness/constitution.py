"""Load and validate the YAML front matter in the canonical constitution."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Tenet:
    id: str
    name: str
    description: str
    priority: str
    quran_refs: tuple[str, ...]
    needs_scholar_review: bool


@dataclass(frozen=True)
class Constitution:
    constitution_id: str
    version: str
    status: str
    needs_scholar_review: bool
    tenets: tuple[Tenet, ...]
    prohibitions: tuple[dict[str, str], ...]
    output_contract: dict[str, Any]
    evidence_policy: dict[str, Any]
    sha256: str
    path: Path

    @property
    def tenet_ids(self) -> tuple[str, ...]:
        return tuple(tenet.id for tenet in self.tenets)


def _front_matter(text: str, path: Path) -> dict[str, Any]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path} must start with YAML front matter")
    try:
        closing = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError(f"{path} has unterminated YAML front matter") from exc
    payload = yaml.safe_load("\n".join(lines[1:closing]))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} front matter must be a mapping")
    return payload


def _required_text(mapping: dict[str, Any], key: str, context: str) -> str:
    value = str(mapping.get(key, "") or "").strip()
    if not value:
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value


def load_constitution(path: str | Path) -> Constitution:
    resolved = Path(path).resolve()
    raw = resolved.read_bytes()
    data = _front_matter(raw.decode("utf-8-sig"), resolved)
    if data.get("schema_version") != "moralitylab_constitution_v1":
        raise ValueError(f"{resolved} has an unsupported schema_version")

    raw_tenets = data.get("tenets")
    if not isinstance(raw_tenets, list) or not raw_tenets:
        raise ValueError(f"{resolved} must define at least one tenet")
    tenets: list[Tenet] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw_tenets):
        if not isinstance(item, dict):
            raise ValueError(f"tenets[{index}] must be a mapping")
        tenet_id = _required_text(item, "id", f"tenets[{index}]")
        if tenet_id in seen_ids:
            raise ValueError(f"duplicate tenet id: {tenet_id}")
        seen_ids.add(tenet_id)
        refs = item.get("quran_refs", [])
        if not isinstance(refs, list) or not all(isinstance(ref, str) and ref.strip() for ref in refs):
            raise ValueError(f"tenets[{index}].quran_refs must be a list of non-empty strings")
        tenets.append(
            Tenet(
                id=tenet_id,
                name=_required_text(item, "name", f"tenets[{index}]"),
                description=_required_text(item, "description", f"tenets[{index}]"),
                priority=_required_text(item, "priority", f"tenets[{index}]"),
                quran_refs=tuple(ref.strip() for ref in refs),
                needs_scholar_review=bool(item.get("needs_scholar_review", True)),
            )
        )

    raw_prohibitions = data.get("prohibitions", [])
    if not isinstance(raw_prohibitions, list):
        raise ValueError("prohibitions must be a list")
    prohibitions: list[dict[str, str]] = []
    for index, item in enumerate(raw_prohibitions):
        if not isinstance(item, dict):
            raise ValueError(f"prohibitions[{index}] must be a mapping")
        prohibitions.append(
            {
                "id": _required_text(item, "id", f"prohibitions[{index}]"),
                "name": _required_text(item, "name", f"prohibitions[{index}]"),
            }
        )

    output_contract = data.get("output_contract", {})
    evidence_policy = data.get("evidence_policy", {})
    if not isinstance(output_contract, dict) or not isinstance(evidence_policy, dict):
        raise ValueError("output_contract and evidence_policy must be mappings")
    required_fields = output_contract.get("fields", [])
    expected_fields = {
        "decision",
        "reflection",
        "tenets_defended",
        "counterpressure",
        "constitutional_defense",
    }
    if set(required_fields) != expected_fields:
        raise ValueError(f"output_contract.fields must be exactly {sorted(expected_fields)}")

    return Constitution(
        constitution_id=_required_text(data, "constitution_id", "constitution"),
        version=_required_text(data, "version", "constitution"),
        status=_required_text(data, "status", "constitution"),
        needs_scholar_review=bool(data.get("needs_scholar_review", True)),
        tenets=tuple(tenets),
        prohibitions=tuple(prohibitions),
        output_contract=dict(output_contract),
        evidence_policy=dict(evidence_policy),
        sha256=hashlib.sha256(raw).hexdigest(),
        path=resolved,
    )
