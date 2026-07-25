"""Compile restricted MeTTa persona facts into live-village system prompts."""

from __future__ import annotations

import hashlib
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinn_bench.construct_scoring import load_metta_policy

SUPPORTED_FORMS = frozenset({"skill", "construct", "alias", "prompt-clause"})


@dataclass(frozen=True)
class VillageSkill:
    skill_id: str
    construct_id: str
    alias: str
    prompt_clauses: tuple[tuple[int, str], ...]
    source_path: Path
    source_sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tokens(line: str, path: Path, line_number: int) -> list[str]:
    stripped = line.strip()
    if not stripped or stripped.startswith(";"):
        return []
    if not stripped.startswith("(") or not stripped.endswith(")"):
        raise ValueError(f"{path}:{line_number}: expected one S-expression fact")
    tokens = shlex.split(stripped[1:-1].strip())
    if not tokens:
        raise ValueError(f"{path}:{line_number}: empty fact")
    if tokens[0] not in SUPPORTED_FORMS:
        raise ValueError(f"{path}:{line_number}: unsupported form {tokens[0]!r}")
    return tokens


def load_village_skill(path: Path) -> VillageSkill:
    """Load one auditable persona scaffold and fail on ambiguous declarations."""
    skill_ids: list[str] = []
    construct_ids: list[str] = []
    aliases: list[str] = []
    clauses: dict[int, str] = {}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        tokens = _tokens(line, path, line_number)
        if not tokens:
            continue
        form = tokens[0]
        if form in {"skill", "construct", "alias"}:
            if len(tokens) != 2:
                raise ValueError(f"{path}:{line_number}: {form} expects one value")
            if form == "skill":
                skill_ids.append(tokens[1])
            elif form == "construct":
                construct_ids.append(tokens[1])
            else:
                aliases.append(tokens[1])
            continue
        if len(tokens) != 3:
            raise ValueError(
                f"{path}:{line_number}: prompt-clause expects order and text"
            )
        order = int(tokens[1])
        text = tokens[2].strip()
        if order in clauses:
            raise ValueError(f"{path}:{line_number}: duplicate prompt order {order}")
        if order < 0 or not text:
            raise ValueError(f"{path}:{line_number}: invalid prompt clause")
        clauses[order] = text

    if len(skill_ids) != 1:
        raise ValueError(f"{path}: expected exactly one skill declaration")
    if len(construct_ids) != 1:
        raise ValueError(f"{path}: expected exactly one construct declaration")
    if len(aliases) != 1:
        raise ValueError(f"{path}: expected exactly one alias declaration")
    if len(clauses) < 4:
        raise ValueError(f"{path}: at least four prompt clauses are required")
    return VillageSkill(
        skill_id=skill_ids[0],
        construct_id=construct_ids[0],
        alias=aliases[0],
        prompt_clauses=tuple(sorted(clauses.items())),
        source_path=path,
        source_sha256=sha256_file(path),
    )


def _humanize(identifier: str) -> str:
    return identifier.replace("_", " ").replace("-", " ")


def compile_system_prompt(skill_path: Path, policy_path: Path) -> dict[str, Any]:
    """Bind a persona scaffold to its executable MeTTa construct policy."""
    skill = load_village_skill(skill_path)
    policy = load_metta_policy(policy_path)
    if skill.construct_id != policy["benchmark_id"]:
        raise ValueError(
            f"{skill_path}: construct {skill.construct_id!r} does not match "
            f"policy benchmark {policy['benchmark_id']!r}"
        )

    dimension_lines = [
        f"- {_humanize(dimension_id)} ({float(weight):.2f})"
        for dimension_id, weight in policy["dimensions"].items()
    ]
    boundary_lines = [
        f"- {_humanize(tag)}" for tag in policy["critical_tags"]
    ]
    clauses = "\n\n".join(text for _, text in skill.prompt_clauses)
    prompt = (
        f"{clauses}\n\n"
        "Internal MeTTa attention scaffold (use silently; do not recite):\n"
        + "\n".join(dimension_lines)
        + "\n\nCritical behavioral boundaries (use silently; do not recite):\n"
        + "\n".join(boundary_lines)
    )
    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return {
        "schema_version": "jinn_beast_village_prompt_bundle_v1",
        "skill_id": skill.skill_id,
        "construct_id": skill.construct_id,
        "alias": skill.alias,
        "system_prompt": prompt,
        "system_prompt_sha256": prompt_sha256,
        "skill_path": skill_path.as_posix(),
        "skill_sha256": skill.source_sha256,
        "policy_path": policy_path.as_posix(),
        "policy_sha256": policy["source_sha256"],
        "dimensions": policy["dimensions"],
        "critical_tags": policy["critical_tags"],
    }
