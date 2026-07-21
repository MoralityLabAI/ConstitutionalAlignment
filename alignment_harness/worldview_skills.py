"""Deterministic Python bridge for the MeTTa worldview-skill map."""

from __future__ import annotations

import hashlib
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GRAPH = REPO_ROOT / "metta" / "worldview_scale_skills_v1.metta"


def _tokens(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped or stripped.startswith(";"):
        return []
    if not (stripped.startswith("(") and stripped.endswith(")")):
        raise ValueError(f"invalid MeTTa fact: {line}")
    lexer = shlex.shlex(stripped[1:-1], posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


@dataclass(frozen=True)
class Skill:
    skill_id: str
    minimum_scale: int
    description: str


@dataclass(frozen=True)
class WorldviewSkillGraph:
    graph_id: str
    scales: dict[str, int]
    skills: dict[str, Skill]
    levels: dict[str, tuple[str, ...]]
    expectations: dict[str, dict[str, str]]
    interference_pairs: tuple[tuple[str, str], ...]
    commutator_axes: tuple[str, ...]
    evaluations: tuple[tuple[str, str], ...]
    source_path: Path
    source_sha256: str


def load_skill_graph(path: str | Path = DEFAULT_GRAPH) -> WorldviewSkillGraph:
    source_path = Path(path).resolve()
    source_bytes = source_path.read_bytes()
    graph_id = ""
    scales: dict[str, int] = {}
    skills: dict[str, Skill] = {}
    levels: dict[str, list[str]] = {}
    expectations: dict[str, dict[str, str]] = {}
    interference: list[tuple[str, str]] = []
    axes: list[str] = []
    evaluations: list[tuple[str, str]] = []

    for line_no, line in enumerate(source_bytes.decode("utf-8").splitlines(), start=1):
        values = _tokens(line)
        if not values:
            continue
        kind = values[0]
        try:
            if kind == "skill-graph" and len(values) == 2:
                graph_id = values[1]
            elif kind == "scale" and len(values) == 3:
                scales[values[1]] = int(values[2])
            elif kind == "skill" and len(values) == 4:
                skills[values[1]] = Skill(values[1], int(values[2]), values[3])
            elif kind == "level" and len(values) == 3:
                levels.setdefault(values[1], []).append(values[2])
            elif kind == "expect" and len(values) == 4:
                expectations.setdefault(values[1], {})[values[2]] = values[3]
            elif kind == "interference" and len(values) == 3:
                interference.append((values[1], values[2]))
            elif kind == "commutator-axis" and len(values) == 2:
                axes.append(values[1])
            elif kind == "evaluation" and len(values) == 3:
                evaluations.append((values[1], values[2]))
            else:
                raise ValueError("unknown or malformed fact")
        except Exception as exc:
            raise ValueError(f"invalid skill fact {source_path}:{line_no}: {line}") from exc

    if not graph_id or not scales or not skills:
        raise ValueError("skill graph requires an id, scales, and skills")
    missing = {
        skill_id for level_skills in levels.values() for skill_id in level_skills if skill_id not in skills
    }
    if missing:
        raise ValueError(f"levels reference missing skills: {sorted(missing)}")
    return WorldviewSkillGraph(
        graph_id=graph_id,
        scales=scales,
        skills=skills,
        levels={key: tuple(value) for key, value in levels.items()},
        expectations=expectations,
        interference_pairs=tuple(interference),
        commutator_axes=tuple(axes),
        evaluations=tuple(evaluations),
        source_path=source_path,
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
    )


def derive_scale_profile(scale_id: str, path: str | Path = DEFAULT_GRAPH) -> dict:
    graph = load_skill_graph(path)
    if scale_id not in graph.scales:
        raise ValueError(f"unknown scale: {scale_id}")
    scale_value = graph.scales[scale_id]
    available = sorted(
        skill.skill_id for skill in graph.skills.values() if skill.minimum_scale <= scale_value
    )
    levels = {
        level: {
            "required_skills": list(required),
            "all_skills_in_capacity_set": set(required).issubset(available),
            "classification": "prospective_screen_only",
        }
        for level, required in graph.levels.items()
    }
    return {
        "schema_version": "worldview_scale_profile.v1",
        "backend": "python_metta_worldview_skill_bridge",
        "claim_boundary": "MeTTa-file-backed deterministic derivation; not native Hyperon proof execution.",
        "graph_id": graph.graph_id,
        "graph_path": str(graph.source_path),
        "graph_sha256": graph.source_sha256,
        "scale_id": scale_id,
        "scale_value": scale_value,
        "capacity_hypothesis_not_result": True,
        "available_skill_hypotheses": available,
        "expectations": graph.expectations.get(scale_id, {}),
        "levels": levels,
        "interference_pairs": [list(item) for item in graph.interference_pairs],
        "commutator_axes": list(graph.commutator_axes),
        "evaluations": [list(item) for item in graph.evaluations],
    }


def render_skill_scaffold(
    scale_id: str,
    level: str,
    *,
    include_skills: Iterable[str] | None = None,
    path: str | Path = DEFAULT_GRAPH,
) -> str:
    graph = load_skill_graph(path)
    profile = derive_scale_profile(scale_id, path)
    if level not in graph.levels:
        raise ValueError(f"unknown reasoning level: {level}")
    selected = list(include_skills) if include_skills is not None else list(graph.levels[level])
    unavailable = sorted(set(selected) - set(profile["available_skill_hypotheses"]))
    if unavailable:
        raise ValueError(f"skills exceed the {scale_id} capacity hypothesis: {unavailable}")
    return "\n".join(
        f"- {graph.skills[skill_id].description}" for skill_id in selected
    )

