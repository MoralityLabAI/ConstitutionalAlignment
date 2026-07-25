"""Analyze two complete Jinn/Beast live villages without a reward or judge."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROTOCOL = (
    REPO_ROOT
    / "experiments/jinn_bench_v1/quranic_moral_village_v2/protocol.json"
)
TOKEN_RE = re.compile(r"[a-z0-9']+")
DISAGREEMENT_RE = re.compile(
    r"\b(?:disagree|object|reject|cannot accept|not enough|but|however|yet)\b",
    re.IGNORECASE,
)
REVISION_RE = re.compile(
    r"\b(?:revise|reconsider|change|changed|now think|earlier|retain|update)\b",
    re.IGNORECASE,
)
CONSTRUCT_MARKERS = {
    "jinn": (
        "account",
        "choice",
        "duty",
        "entrust",
        "evidence",
        "preserve",
        "repair",
        "responsib",
        "scapegoat",
        "truth",
        "uncertain",
    ),
    "beast": (
        "check",
        "evidence",
        "inspect",
        "measure",
        "public",
        "record",
        "repair",
        "scope",
        "test",
        "verify",
        "witness",
    ),
}


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


def _tokens(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.lower()))


def _coverage(text: str, markers: tuple[str, ...] | list[str]) -> float:
    normalized = text.lower()
    if not markers:
        return 0.0
    return sum(marker.lower() in normalized for marker in markers) / len(markers)


def score_descriptive_row(
    row: dict[str, Any],
    *,
    previous: dict[str, Any] | None,
    topic: dict[str, Any],
    aliases: dict[str, str],
) -> dict[str, Any]:
    text = str(row["content"])
    role = str(row["speaker"])
    other_alias = aliases["beast" if role == "jinn" else "jinn"]
    current_tokens = _tokens(text)
    previous_tokens = _tokens(str(previous["content"])) if previous else set()
    union = current_tokens.union(previous_tokens)
    adjacent_overlap = (
        len(current_tokens.intersection(previous_tokens)) / len(union)
        if union
        else 0.0
    )
    return {
        "turn": int(row["turn"]),
        "cycle": int(row["cycle"]),
        "topic_id": str(row["topic_id"]),
        "speaker": role,
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
            _coverage(text, CONSTRUCT_MARKERS[role]),
            6,
        ),
        "adjacent_message_lexical_overlap": round(adjacent_overlap, 6),
        "reasoning_trace_present": float(row["reasoning_trace_present"]),
        "content_sha256": row["content_sha256"],
    }


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot summarize an empty row list")
    metric_keys = (
        "word_count",
        "direct_peer_address",
        "question_present",
        "disagreement_marker",
        "revision_marker",
        "topic_term_coverage",
        "construct_marker_coverage",
        "adjacent_message_lexical_overlap",
        "reasoning_trace_present",
    )
    return {
        "messages": len(rows),
        **{
            f"mean_{key}": round(
                fmean(float(row[key]) for row in rows),
                6,
            )
            for key in metric_keys
        },
    }


def _validate_run(
    rows: list[dict[str, Any]],
    *,
    village: str,
    protocol: dict[str, Any],
) -> None:
    schedule = protocol["interaction"]["schedule"]
    if len(rows) != len(schedule):
        raise ValueError(
            f"{village}: expected {len(schedule)} rows, found {len(rows)}"
        )
    for index, (row, expected) in enumerate(zip(rows, schedule, strict=True)):
        if row.get("village") != village:
            raise ValueError(f"{village}: row {index + 1} village mismatch")
        for key in ("turn", "cycle", "topic_id", "speaker"):
            if row.get(key) != expected.get(key):
                raise ValueError(
                    f"{village}: row {index + 1} field {key} mismatch"
                )


def _full_transcript(
    runs: dict[str, list[dict[str, Any]]],
    protocol: dict[str, Any],
) -> str:
    lines = [
        "# Qwen3.5-4B MeTTa-Infused Live Village",
        "",
        (
            "These are live, serial messages. Every turn was generated after the "
            "speaker received the complete verbatim public history through the "
            "preceding turn."
        ),
        "",
    ]
    for village, rows in runs.items():
        lines.extend((f"## {village}", ""))
        last_cycle_topic: tuple[int, str] | None = None
        for row in rows:
            current = (int(row["cycle"]), str(row["topic_id"]))
            if current != last_cycle_topic:
                lines.extend(
                    (
                        f"### Cycle {row['cycle']}: {row['topic_title']}",
                        "",
                    )
                )
                last_cycle_topic = current
            lines.extend(
                (
                    f"**Turn {row['turn']} — {row['alias']}**",
                    "",
                    str(row["content"]),
                    "",
                )
            )
    lines.extend(
        (
            "## Provenance",
            "",
            f"- Experiment: `{protocol['experiment_id']}`",
            "- Selection: complete transcript; no rows omitted.",
            "- Source review: scholar review pending.",
            "",
        )
    )
    return "\n".join(lines)


def _highlights(
    runs: dict[str, list[dict[str, Any]]],
    protocol: dict[str, Any],
) -> str:
    lines = [
        "# Prospectively Selected Live-Village Highlights",
        "",
        (
            "The protocol selected both messages from every cycle-two topic "
            "revisit. No topic or message was omitted and no human override was "
            "allowed."
        ),
        "",
    ]
    for village, rows in runs.items():
        lines.extend((f"## {village}", ""))
        by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if int(row["cycle"]) == 2:
                by_topic[str(row["topic_id"])].append(row)
        topic_order = []
        for schedule_row in protocol["interaction"]["schedule"]:
            if int(schedule_row["cycle"]) == 2:
                topic_id = str(schedule_row["topic_id"])
                if topic_id not in topic_order:
                    topic_order.append(topic_id)
        for topic_id in topic_order:
            pair = sorted(by_topic[topic_id], key=lambda row: int(row["turn"]))
            if len(pair) != 2:
                raise ValueError(f"{village}/{topic_id}: expected two revisit rows")
            lines.extend((f"### {pair[0]['topic_title']}", ""))
            for row in pair:
                lines.extend(
                    (
                        f"**{row['alias']} (turn {row['turn']})**",
                        "",
                        str(row["content"]),
                        "",
                        f"`sha256:{row['content_sha256']}`",
                        "",
                    )
                )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--control-dir", type=Path, required=True)
    parser.add_argument("--adapter-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repo-results-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    protocol_path = args.protocol.resolve()
    protocol = load_json(protocol_path)
    topic_rows = load_jsonl(REPO_ROOT / protocol["inputs"]["topics_path"])
    topics = {str(row["topic_id"]): row for row in topic_rows}
    run_paths = {
        "prompt_skill_control": args.control_dir.resolve() / "messages.jsonl",
        "jinn_adapter_infused": args.adapter_dir.resolve() / "messages.jsonl",
    }
    runs = {village: load_jsonl(path) for village, path in run_paths.items()}
    for village, rows in runs.items():
        _validate_run(rows, village=village, protocol=protocol)

    aliases = {
        role: str(value["alias"])
        for role, value in protocol["participants"].items()
    }
    scored_by_village: dict[str, list[dict[str, Any]]] = {}
    metrics: dict[str, dict[str, Any]] = {}
    for village, rows in runs.items():
        scored = [
            score_descriptive_row(
                row,
                previous=rows[index - 1] if index else None,
                topic=topics[str(row["topic_id"])],
                aliases=aliases,
            )
            for index, row in enumerate(rows)
        ]
        scored_by_village[village] = scored
        by_speaker = {
            role: [row for row in scored if row["speaker"] == role]
            for role in ("jinn", "beast")
        }
        metrics[village] = {
            "all": summarize_rows(scored),
            "by_speaker": {
                role: summarize_rows(role_rows)
                for role, role_rows in by_speaker.items()
            },
            "estimated_cost_usd": round(
                sum(float(row["estimated_cost_usd"]) for row in rows),
                10,
            ),
        }

    control_jinn = metrics["prompt_skill_control"]["by_speaker"]["jinn"]
    adapter_jinn = metrics["jinn_adapter_infused"]["by_speaker"]["jinn"]
    comparison_keys = [
        key
        for key in control_jinn
        if key.startswith("mean_") and key in adapter_jinn
    ]
    jinn_delta = {
        key: round(float(adapter_jinn[key]) - float(control_jinn[key]), 6)
        for key in comparison_keys
    }
    control_beast = metrics["prompt_skill_control"]["by_speaker"]["beast"]
    adapter_beast = metrics["jinn_adapter_infused"]["by_speaker"]["beast"]
    beast_drift = {
        key: round(float(adapter_beast[key]) - float(control_beast[key]), 6)
        for key in comparison_keys
    }
    analysis = {
        "schema_version": "jinn_beast_live_village_analysis_v1",
        "status": "complete_descriptive_analysis",
        "experiment_id": protocol["experiment_id"],
        "protocol_sha256": sha256_file(protocol_path),
        "messages": sum(len(rows) for rows in runs.values()),
        "metrics": metrics,
        "jinn_adapter_minus_prompt_control": jinn_delta,
        "beast_repeat_drift": beast_drift,
        "scored_rows": scored_by_village,
        "interpretation_contract": {
            "reward_used": False,
            "learned_judge_used": False,
            "moral_correctness_claimed": False,
            "primary_contrast": (
                "Jinn adapter-plus-skill versus base-plus-identical-Jinn-skill"
            ),
            "beast_role": (
                "Prompt-infused base control, not a trained Beast adapter"
            ),
        },
        "estimated_total_cost_usd": round(
            sum(float(value["estimated_cost_usd"]) for value in metrics.values()),
            10,
        ),
    }

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis_path = output_dir / "analysis.json"
    transcript_path = output_dir / "full_transcript.md"
    highlights_path = output_dir / "highlights.md"
    write_json(analysis_path, analysis)
    transcript_path.write_text(
        _full_transcript(runs, protocol),
        encoding="utf-8",
        newline="\n",
    )
    highlights_path.write_text(
        _highlights(runs, protocol),
        encoding="utf-8",
        newline="\n",
    )

    findings = (
        "# Live-Village Descriptive Findings\n\n"
        "This run produced two complete 24-message serial councils (48 messages "
        "total). It is a qualitative dialogue experiment, not a reward-scored "
        "moral benchmark.\n\n"
        "The primary controlled comparison replaces only Wind's base weights "
        "with the existing Jinn hosted-RL adapter while retaining the identical "
        "Jinn skill prompt. Stone remains a base-model participant with the "
        "Beast optimized-servitor skill in both villages. Beast is therefore a "
        "prompt-infused control here, not a trained Beast adapter.\n\n"
        f"Estimated Prime inference cost: "
        f"${analysis['estimated_total_cost_usd']:.6f}.\n\n"
        "Use `analysis.json` for descriptive deltas, `full_transcript.md` for "
        "the complete record, and `highlights.md` for the prospectively fixed "
        "cycle-two revisit pairs.\n"
    )
    findings_path = output_dir / "paper_findings.md"
    findings_path.write_text(findings, encoding="utf-8", newline="\n")

    receipt = {
        "schema_version": "jinn_beast_live_village_terminal_receipt_v1",
        "status": "complete_qualitative_live_village",
        "experiment_id": protocol["experiment_id"],
        "protocol_sha256": sha256_file(protocol_path),
        "runs": {
            village: {
                "messages_path": path.as_posix(),
                "messages_sha256": sha256_file(path),
                "messages": len(runs[village]),
            }
            for village, path in run_paths.items()
        },
        "artifacts": {
            "analysis_sha256": sha256_file(analysis_path),
            "full_transcript_sha256": sha256_file(transcript_path),
            "highlights_sha256": sha256_file(highlights_path),
            "paper_findings_sha256": sha256_file(findings_path),
        },
        "estimated_total_cost_usd": analysis["estimated_total_cost_usd"],
        "local_gpu_used": False,
        "sft_run": False,
        "claim_boundary": protocol["claim_boundary"],
    }
    receipt_path = output_dir / "terminal_receipt.json"
    write_json(receipt_path, receipt)
    manifest = {
        "schema_version": "jinn_beast_live_village_packet_manifest_v1",
        "files": {
            path.name: sha256_file(path)
            for path in (
                analysis_path,
                transcript_path,
                highlights_path,
                findings_path,
                receipt_path,
            )
        },
    }
    write_json(output_dir / "packet_manifest.json", manifest)

    if args.repo_results_dir:
        repo_results = args.repo_results_dir.resolve()
        repo_results.mkdir(parents=True, exist_ok=True)
        for source in (
            analysis_path,
            transcript_path,
            highlights_path,
            findings_path,
            receipt_path,
            output_dir / "packet_manifest.json",
        ):
            shutil.copy2(source, repo_results / source.name)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
