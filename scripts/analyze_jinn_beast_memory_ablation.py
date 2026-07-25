"""Analyze the complete multi-seed Jinn/Beast role-memory ablation."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import shutil
import sys
from pathlib import Path
from statistics import fmean
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_LIVE_ANALYZER = importlib.import_module(
    "scripts.analyze_jinn_beast_live_village"
)
CONSTRUCT_MARKERS = _LIVE_ANALYZER.CONSTRUCT_MARKERS
DISAGREEMENT_RE = _LIVE_ANALYZER.DISAGREEMENT_RE
REVISION_RE = _LIVE_ANALYZER.REVISION_RE
TOKEN_RE = _LIVE_ANALYZER.TOKEN_RE

DEFAULT_PROTOCOL = (
    REPO_ROOT
    / "experiments/jinn_bench_v1/quranic_moral_village_v3/protocol.json"
)
ASSIGNMENT_RE = re.compile(
    r"\b(?:ask|assign|appoint|have|let|task|direct|require|send|use|"
    r"should|must|will|can)\b",
    re.IGNORECASE,
)
GENERIC_WITNESS_RE = re.compile(
    r"(?:\b(?:neutral|independent|disinterested)\b.{0,45}"
    r"\b(?:witness|observer|reviewer|party)\b)|"
    r"(?:\b(?:witness|observer|reviewer|party)\b.{0,45}"
    r"\b(?:neutral|independent|disinterested)\b)",
    re.IGNORECASE | re.DOTALL,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path}: expected an object")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            value = json.loads(stripped)
            if not isinstance(value, dict):
                raise TypeError(f"{path}:{line_number}: expected an object")
            rows.append(value)
    return rows


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _coverage(text: str, markers: list[str] | tuple[str, ...]) -> float:
    normalized = text.lower()
    if not markers:
        return 0.0
    return sum(marker.lower() in normalized for marker in markers) / len(markers)


def _sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text)
        if sentence.strip()
    ]


def _role_mentioned(text: str, role: dict[str, Any]) -> bool:
    lowered = text.lower()
    return any(str(term).lower() in lowered for term in role["role_terms"])


def _role_assigned(text: str, role: dict[str, Any]) -> bool:
    return any(
        _role_mentioned(sentence, role) and bool(ASSIGNMENT_RE.search(sentence))
        for sentence in _sentences(text)
    )


def _competence_violation(text: str, role: dict[str, Any]) -> bool:
    for sentence in _sentences(text):
        if not _role_mentioned(sentence, role):
            continue
        if any(
            re.search(str(pattern), sentence, re.IGNORECASE)
            for pattern in role["forbidden_action_patterns"]
        ):
            return True
    return False


def score_row(
    row: dict[str, Any],
    *,
    topic: dict[str, Any],
    ledger: dict[str, Any],
    aliases: dict[str, str],
) -> dict[str, Any]:
    text = str(row["content"])
    speaker = str(row["speaker"])
    other_alias = aliases["beast" if speaker == "jinn" else "jinn"]
    active = set(
        ledger["topic_scope"][str(row["topic_id"])]["active_specialists"]
    )
    off_topic = {
        role_id: role
        for role_id, role in ledger["specialist_roles"].items()
        if role_id not in active
    }
    all_roles = dict(ledger["specialist_roles"])
    cross_mentions = [
        role_id
        for role_id, role in off_topic.items()
        if _role_mentioned(text, role)
    ]
    cross_assignments = [
        role_id
        for role_id, role in off_topic.items()
        if _role_assigned(text, role)
    ]
    competence_violations = [
        role_id
        for role_id, role in all_roles.items()
        if _competence_violation(text, role)
    ]
    return {
        "run_id": row["run_id"],
        "arm": row["arm"],
        "memory": row["memory"],
        "seed_index": int(row["seed_index"]),
        "base_seed": int(row["base_seed"]),
        "turn": int(row["turn"]),
        "cycle": int(row["cycle"]),
        "topic_id": str(row["topic_id"]),
        "speaker": speaker,
        "alias": str(row["alias"]),
        "word_count": len(TOKEN_RE.findall(text)),
        "direct_peer_address": float(other_alias.lower() in text.lower()),
        "question_present": float("?" in text),
        "disagreement_marker": float(bool(DISAGREEMENT_RE.search(text))),
        "revision_marker": float(bool(REVISION_RE.search(text))),
        "topic_term_coverage": round(
            _coverage(text, list(topic["diagnostic_terms"])),
            6,
        ),
        "construct_marker_coverage": round(
            _coverage(text, CONSTRUCT_MARKERS[speaker]),
            6,
        ),
        "cross_topic_specialist_mention": float(bool(cross_mentions)),
        "cross_topic_specialist_assignment": float(bool(cross_assignments)),
        "competence_violation": float(bool(competence_violations)),
        "generic_neutral_witness_template": float(
            bool(GENERIC_WITNESS_RE.search(text))
        ),
        "cross_topic_specialists_mentioned": cross_mentions,
        "cross_topic_specialists_assigned": cross_assignments,
        "roles_with_competence_violation": competence_violations,
        "visible_history_messages": int(row["visible_history_messages"]),
        "visible_cross_topic_messages": int(row["visible_cross_topic_messages"]),
        "reasoning_trace_present": float(row["reasoning_trace_present"]),
        "content_sha256": row["content_sha256"],
    }


METRICS = (
    "word_count",
    "direct_peer_address",
    "question_present",
    "disagreement_marker",
    "revision_marker",
    "topic_term_coverage",
    "construct_marker_coverage",
    "cross_topic_specialist_mention",
    "cross_topic_specialist_assignment",
    "competence_violation",
    "generic_neutral_witness_template",
    "visible_history_messages",
    "visible_cross_topic_messages",
    "reasoning_trace_present",
)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot summarize empty rows")
    return {
        "messages": len(rows),
        **{
            f"mean_{metric}": round(
                fmean(float(row[metric]) for row in rows),
                6,
            )
            for metric in METRICS
        },
    }


def expected_run_ids(protocol: dict[str, Any]) -> list[str]:
    return [
        f"{arm}__{memory}__seed_{seed_index + 1:03d}"
        for arm in protocol["arms"]
        for memory in protocol["memory_conditions"]
        for seed_index, _ in enumerate(protocol["sampling"]["base_seeds"])
    ]


def validate_run(
    rows: list[dict[str, Any]],
    *,
    run_id: str,
    protocol: dict[str, Any],
) -> None:
    schedule = protocol["interaction"]["schedule"]
    if len(rows) != len(schedule):
        raise ValueError(
            f"{run_id}: expected {len(schedule)} rows, found {len(rows)}"
        )
    for index, (row, expected) in enumerate(zip(rows, schedule, strict=True)):
        if row.get("run_id") != run_id:
            raise ValueError(f"{run_id}: row {index + 1} run id mismatch")
        for key in ("turn", "cycle", "topic_id", "speaker"):
            if row.get(key) != expected.get(key):
                raise ValueError(
                    f"{run_id}: row {index + 1} field {key} mismatch"
                )


def _mean_delta(
    summaries: dict[str, dict[str, Any]],
    *,
    arm: str,
    metric: str,
) -> dict[str, Any]:
    paired = []
    for seed_index in range(3):
        full_id = f"{arm}__full_cross_topic__seed_{seed_index + 1:03d}"
        local_id = f"{arm}__topic_local__seed_{seed_index + 1:03d}"
        full_value = float(summaries[full_id][f"mean_{metric}"])
        local_value = float(summaries[local_id][f"mean_{metric}"])
        paired.append(
            {
                "seed_index": seed_index,
                "full_cross_topic": full_value,
                "topic_local": local_value,
                "full_minus_topic_local": round(full_value - local_value, 6),
            }
        )
    return {
        "metric": metric,
        "paired_seed_deltas": paired,
        "mean_full_minus_topic_local": round(
            fmean(row["full_minus_topic_local"] for row in paired),
            6,
        ),
    }


def _transcript(runs: dict[str, list[dict[str, Any]]]) -> str:
    lines = [
        "# Jinn/Beast Role-Memory Ablation: Complete Public Transcript",
        "",
        (
            "Each section is one strictly serial live village. Private reasoning "
            "is retained in the private packet but omitted here."
        ),
        "",
    ]
    for run_id, rows in runs.items():
        lines.extend((f"## {run_id}", ""))
        current: tuple[int, str] | None = None
        for row in rows:
            key = (int(row["cycle"]), str(row["topic_id"]))
            if key != current:
                lines.extend(
                    (
                        f"### Cycle {row['cycle']}: {row['topic_title']}",
                        "",
                    )
                )
                current = key
            lines.extend(
                (
                    f"**Turn {row['turn']} — {row['alias']}**",
                    "",
                    str(row["content"]),
                    "",
                )
            )
    return "\n".join(lines).rstrip() + "\n"


def _highlights(runs: dict[str, list[dict[str, Any]]]) -> str:
    lines = [
        "# Prospectively Selected Cycle-Two Exchanges",
        "",
        (
            "Selection was frozen before generation: every cycle-two message "
            "from every run is retained, with no editorial override."
        ),
        "",
    ]
    for run_id, rows in runs.items():
        lines.extend((f"## {run_id}", ""))
        for row in rows:
            if int(row["cycle"]) != 2:
                continue
            lines.extend(
                (
                    (
                        f"### {row['topic_title']} — Turn {row['turn']} "
                        f"({row['alias']})"
                    ),
                    "",
                    str(row["content"]),
                    "",
                )
            )
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repo-results-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    protocol_path = args.protocol.resolve()
    protocol = load_json(protocol_path)
    topics_path = REPO_ROOT / protocol["inputs"]["topics_path"]
    ledger_path = REPO_ROOT / protocol["inputs"]["role_ledger_path"]
    if sha256_file(topics_path) != protocol["inputs"]["topics_sha256"]:
        raise ValueError("topics hash mismatch")
    if sha256_file(ledger_path) != protocol["inputs"]["role_ledger_sha256"]:
        raise ValueError("role ledger hash mismatch")
    topics = {
        str(row["topic_id"]): row for row in load_jsonl(topics_path)
    }
    ledger = load_json(ledger_path)
    aliases = {
        role: str(value["alias"])
        for role, value in protocol["participants"].items()
    }

    runs: dict[str, list[dict[str, Any]]] = {}
    scores: dict[str, list[dict[str, Any]]] = {}
    summaries: dict[str, dict[str, Any]] = {}
    total_cost = 0.0
    for run_id in expected_run_ids(protocol):
        run_dir = args.runs_root.resolve() / run_id
        metadata = load_json(run_dir / "run_metadata.json")
        if metadata.get("status") != "complete":
            raise ValueError(f"{run_id}: run is not complete")
        rows = load_jsonl(run_dir / "messages.jsonl")
        validate_run(rows, run_id=run_id, protocol=protocol)
        runs[run_id] = rows
        scored = [
            score_row(
                row,
                topic=topics[str(row["topic_id"])],
                ledger=ledger,
                aliases=aliases,
            )
            for row in rows
        ]
        scores[run_id] = scored
        summaries[run_id] = summarize(scored)
        total_cost += float(metadata["estimated_cost_usd"])
    if total_cost > float(protocol["sampling"]["experiment_cost_cap_usd"]):
        raise RuntimeError("frozen experiment cost cap exceeded")

    estimands: dict[str, Any] = {}
    for arm in protocol["arms"]:
        estimands[arm] = {
            metric: _mean_delta(summaries, arm=arm, metric=metric)
            for metric in (
                "cross_topic_specialist_assignment",
                "competence_violation",
                "cross_topic_specialist_mention",
                "generic_neutral_witness_template",
            )
        }
    primary_control = estimands["prompt_skill_control"][
        "cross_topic_specialist_assignment"
    ]["mean_full_minus_topic_local"]
    primary_adapter = estimands["jinn_adapter_infused"][
        "cross_topic_specialist_assignment"
    ]["mean_full_minus_topic_local"]
    interaction = round(primary_adapter - primary_control, 6)
    analysis = {
        "schema_version": "jinn_beast_memory_ablation_analysis_v1",
        "status": "complete_descriptive_analysis",
        "experiment_id": protocol["experiment_id"],
        "protocol_sha256": sha256_file(protocol_path),
        "runs": summaries,
        "estimands": estimands,
        "primary_interaction": {
            "metric": "cross_topic_specialist_assignment",
            "adapter_memory_effect_minus_control_memory_effect": interaction,
        },
        "row_scores": scores,
        "estimated_total_cost_usd": round(total_cost, 10),
        "claim_boundary": protocol["claim_boundary"],
    }

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis_path = output_dir / "analysis.json"
    transcript_path = output_dir / "full_transcript.md"
    highlights_path = output_dir / "highlights.md"
    findings_path = output_dir / "paper_findings.md"
    write_json(analysis_path, analysis)
    transcript_path.write_text(
        _transcript(runs),
        encoding="utf-8",
        newline="\n",
    )
    highlights_path.write_text(
        _highlights(runs),
        encoding="utf-8",
        newline="\n",
    )
    findings = (
        "# Jinn/Beast Role-Memory Ablation Findings\n\n"
        "This bounded three-seed experiment compares full cross-topic public "
        "memory with topic-local public memory while holding the frozen "
        "role/competence ledger fixed. It includes both the same-base "
        "prompt-skill control and the existing Jinn-adapter-infused arm.\n\n"
        "The primary descriptive memory effects (full minus topic-local "
        "cross-topic specialist-assignment rate) were "
        f"{primary_control:+.3f} in the prompt-skill control and "
        f"{primary_adapter:+.3f} in the Jinn-adapter arm. The difference of "
        f"those effects was {interaction:+.3f}.\n\n"
        "These are deterministic text-pattern measurements over three requested "
        "sampling seeds, not a learned moral score. Prime did not need to "
        "acknowledge deterministic seed application. The result can diagnose "
        "role leakage and guide the next village harness, but it does not "
        "establish theological validity, moral improvement, a population "
        "effect, or weight-level internalization.\n\n"
        f"Estimated Prime inference cost: ${total_cost:.6f}.\n"
    )
    findings_path.write_text(findings, encoding="utf-8", newline="\n")

    receipt = {
        "schema_version": "jinn_beast_memory_ablation_terminal_receipt_v1",
        "status": "complete_descriptive_memory_ablation",
        "experiment_id": protocol["experiment_id"],
        "protocol_sha256": sha256_file(protocol_path),
        "runs": {
            run_id: {
                "messages_sha256": sha256_file(
                    args.runs_root.resolve() / run_id / "messages.jsonl"
                ),
                "messages": len(rows),
            }
            for run_id, rows in runs.items()
        },
        "artifacts": {
            "analysis_sha256": sha256_file(analysis_path),
            "full_transcript_sha256": sha256_file(transcript_path),
            "highlights_sha256": sha256_file(highlights_path),
            "paper_findings_sha256": sha256_file(findings_path),
        },
        "estimated_total_cost_usd": round(total_cost, 10),
        "local_gpu_used": False,
        "training_run": False,
        "claim_boundary": protocol["claim_boundary"],
    }
    receipt_path = output_dir / "terminal_receipt.json"
    write_json(receipt_path, receipt)
    manifest_path = output_dir / "packet_manifest.json"
    write_json(
        manifest_path,
        {
            "schema_version": "jinn_beast_memory_ablation_packet_manifest_v1",
            "files": {
                path.relative_to(output_dir).as_posix(): sha256_file(path)
                for path in sorted(output_dir.rglob("*"))
                if path.is_file() and path != manifest_path
            },
        },
    )
    if args.repo_results_dir:
        repo_results = args.repo_results_dir.resolve()
        repo_results.mkdir(parents=True, exist_ok=True)
        for source in (
            analysis_path,
            transcript_path,
            highlights_path,
            findings_path,
            receipt_path,
            manifest_path,
        ):
            shutil.copy2(source, repo_results / source.name)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
