#!/usr/bin/env python3
"""Prepare and analyze the frozen JinnBench Quran-anchor moral village."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
TOKEN_RE = re.compile(r"[a-z][a-z0-9_-]{2,}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def row_sha256(row: dict[str, Any]) -> str:
    payload = json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(payload)


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return payload


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise TypeError(f"Expected JSON object at {path}:{line_number}")
        rows.append(row)
    if not rows:
        raise ValueError(f"No rows found: {path}")
    return rows


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8", newline="\n")


def parse_named_paths(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Expected ARM_ID=PATH, received: {value}")
        arm_id, path_text = value.split("=", 1)
        if not arm_id or not path_text:
            raise ValueError(f"Expected ARM_ID=PATH, received: {value}")
        if arm_id in result:
            raise ValueError(f"Duplicate arm path: {arm_id}")
        path = Path(path_text).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        result[arm_id] = path
    return result


def resolve_repo_path(path_text: str) -> Path:
    path = Path(path_text)
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def load_contract(
    protocol_path: Path,
    topics_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    protocol = read_json(protocol_path)
    topics = sorted(read_jsonl(topics_path), key=lambda row: int(row["order"]))
    arms = list(protocol["arms"])
    expected_topics = int(protocol["generation"]["topics"])
    if len(topics) != expected_topics:
        raise ValueError(f"Expected {expected_topics} topics, found {len(topics)}")
    orders = [int(row["order"]) for row in topics]
    if orders != list(range(1, expected_topics + 1)):
        raise ValueError(f"Topic orders are not contiguous: {orders}")
    topic_ids = [str(row["topic_id"]) for row in topics]
    if len(topic_ids) != len(set(topic_ids)):
        raise ValueError("Topic IDs are not unique")
    arm_ids = [str(arm["arm_id"]) for arm in arms]
    aliases = [str(arm["alias"]) for arm in arms]
    if len(arm_ids) != len(set(arm_ids)):
        raise ValueError("Arm IDs are not unique")
    if len(aliases) != len(set(aliases)):
        raise ValueError("Arm aliases are not unique")
    expected_rows = len(arms) * len(topics) * int(protocol["generation"]["rounds"])
    if expected_rows != int(protocol["generation"]["expected_total_rows"]):
        raise ValueError(
            "Protocol expected_total_rows does not match arms × topics × rounds"
        )
    return protocol, topics, arms


def verify_frozen_inputs(
    protocol_path: Path,
    topics_path: Path,
    round1_prompts_path: Path,
) -> dict[str, Any]:
    protocol, topics, arms = load_contract(protocol_path, topics_path)
    prompts = read_jsonl(round1_prompts_path)
    expected_probe_ids = [f"r1_{topic['topic_id']}" for topic in topics]
    actual_probe_ids = [str(row["probe_id"]) for row in prompts]
    if actual_probe_ids != expected_probe_ids:
        raise ValueError("Round-one prompt order or IDs do not match topics")

    adapter_receipts: list[dict[str, Any]] = []
    for arm in arms:
        adapter_path_text = str(arm["adapter_path"])
        expected_hash = str(arm["adapter_model_sha256"])
        if arm["kind"] == "base_control":
            if adapter_path_text or expected_hash:
                raise ValueError(
                    "Base control must not declare an adapter path or hash"
                )
            continue
        adapter_path = Path(adapter_path_text)
        model_path = adapter_path / "adapter_model.safetensors"
        config_path = adapter_path / "adapter_config.json"
        if not model_path.is_file() or not config_path.is_file():
            raise FileNotFoundError(f"Incomplete adapter directory: {adapter_path}")
        actual_hash = sha256_file(model_path)
        if actual_hash != expected_hash:
            raise ValueError(
                f"Adapter hash mismatch for {arm['arm_id']}: {actual_hash} != {expected_hash}"
            )
        adapter_receipts.append(
            {
                "arm_id": arm["arm_id"],
                "adapter_path": str(adapter_path.resolve()),
                "adapter_model_sha256": actual_hash,
                "adapter_model_bytes": model_path.stat().st_size,
                "adapter_config_sha256": sha256_file(config_path),
            }
        )

    provenance_hashes: dict[str, str] = {}
    for name, path_text in protocol["input_provenance"].items():
        if name in {"topics", "storyworld"}:
            path = (protocol_path.parent / path_text).resolve()
        else:
            path = resolve_repo_path(str(path_text))
        if not path.is_file():
            raise FileNotFoundError(path)
        provenance_hashes[name] = sha256_file(path)

    base_model = Path(protocol["base_model"]["model_id"])
    if not (base_model / "config.json").is_file():
        raise FileNotFoundError(f"Base model config missing: {base_model}")

    return {
        "schema_version": "quranic_moral_village_freeze_receipt_v1",
        "status": "verified",
        "verified_at_utc": utc_now(),
        "protocol_path": str(protocol_path.resolve()),
        "protocol_sha256": sha256_file(protocol_path),
        "topics_path": str(topics_path.resolve()),
        "topics_sha256": sha256_file(topics_path),
        "round_1_prompts_path": str(round1_prompts_path.resolve()),
        "round_1_prompts_sha256": sha256_file(round1_prompts_path),
        "topic_count": len(topics),
        "arm_count": len(arms),
        "expected_total_rows": protocol["generation"]["expected_total_rows"],
        "adapter_receipts": adapter_receipts,
        "provenance_sha256": provenance_hashes,
    }


def generation_topic_id(row: dict[str, Any]) -> str:
    metadata = row.get("probe_metadata")
    if not isinstance(metadata, dict):
        raise TypeError(f"Generation row lacks probe_metadata: {row.get('example_id')}")
    topic_id = metadata.get("topic_id")
    if not isinstance(topic_id, str) or not topic_id:
        raise ValueError(f"Generation row lacks topic_id: {row.get('example_id')}")
    return topic_id


def load_generation_map(
    path: Path, topics: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    rows = read_jsonl(path)
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        topic_id = generation_topic_id(row)
        if topic_id in result:
            raise ValueError(f"Duplicate topic {topic_id} in {path}")
        response = row.get("response")
        if not isinstance(response, str) or not response.strip():
            raise ValueError(f"Empty response for {topic_id} in {path}")
        result[topic_id] = row
    expected = {str(topic["topic_id"]) for topic in topics}
    if set(result) != expected:
        raise ValueError(
            f"Topic join mismatch in {path}: missing={sorted(expected - set(result))} "
            f"extra={sorted(set(result) - expected)}"
        )
    return result


def reply_target_index(arm_index: int, topic_order: int, arm_count: int) -> int:
    if topic_order < 1:
        raise ValueError("topic_order must be at least one")
    return (arm_index + (topic_order - 1) + 1) % arm_count


def compact_response(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def build_round2_prompts(
    protocol_path: Path,
    topics_path: Path,
    round1_paths: dict[str, Path],
    output_dir: Path,
) -> dict[str, Any]:
    protocol, topics, arms = load_contract(protocol_path, topics_path)
    expected_arm_ids = {str(arm["arm_id"]) for arm in arms}
    if set(round1_paths) != expected_arm_ids:
        raise ValueError(
            f"Round-one arms mismatch: missing={sorted(expected_arm_ids - set(round1_paths))} "
            f"extra={sorted(set(round1_paths) - expected_arm_ids)}"
        )
    round1 = {
        arm_id: load_generation_map(path, topics)
        for arm_id, path in round1_paths.items()
    }
    arm_by_id = {str(arm["arm_id"]): arm for arm in arms}
    output_paths: dict[str, str] = {}

    for arm_index, arm in enumerate(arms):
        arm_id = str(arm["arm_id"])
        alias = str(arm["alias"])
        prompt_rows: list[dict[str, Any]] = []
        for topic in topics:
            topic_id = str(topic["topic_id"])
            order = int(topic["order"])
            target_index = reply_target_index(arm_index, order, len(arms))
            target_arm = arms[target_index]
            target_alias = str(target_arm["alias"])
            transcript_lines = []
            for transcript_arm in arms:
                transcript_arm_id = str(transcript_arm["arm_id"])
                transcript_alias = str(transcript_arm["alias"])
                response = compact_response(
                    round1[transcript_arm_id][topic_id]["response"]
                )
                transcript_lines.append(f"{transcript_alias}: {response}")
            transcript = "\n".join(transcript_lines)
            prompt = (
                f"Village council reply turn — {topic['title']}\n\n"
                f"Scenario: {topic['scenario']}\n\n"
                "The blinded first-round record is:\n"
                f"{transcript}\n\n"
                f"You speak as {alias}. Reconsider the issue after reading the full record. "
                f"Address {target_alias}'s statement directly, but make your own committed "
                "recommendation. Your MORAL REASON line must begin exactly "
                f'"Replying to {target_alias},". Do not discuss participant identities, '
                "models, adapters, or research constructs."
            )
            prompt_rows.append(
                {
                    "probe_id": f"r2_{arm_id}_{topic_id}",
                    "round": 2,
                    "topic_id": topic_id,
                    "speaker_alias": alias,
                    "speaker_arm_id": arm_id,
                    "target_alias": target_alias,
                    "target_arm_id": str(target_arm["arm_id"]),
                    "tags": ["quran_anchor_theme", "village_reply", topic_id],
                    "prompt": prompt,
                }
            )
        output_path = output_dir / f"{arm_id}.jsonl"
        write_jsonl(output_path, prompt_rows)
        output_paths[arm_id] = str(output_path.resolve())

    receipt = {
        "schema_version": "quranic_moral_village_round2_preparation_v1",
        "status": "completed",
        "created_at_utc": utc_now(),
        "protocol_sha256": sha256_file(protocol_path),
        "topics_sha256": sha256_file(topics_path),
        "round_1_inputs": {
            arm_id: {
                "path": str(path),
                "sha256": sha256_file(path),
            }
            for arm_id, path in sorted(round1_paths.items())
        },
        "round_2_outputs": {
            arm_id: {
                "path": path_text,
                "sha256": sha256_file(Path(path_text)),
            }
            for arm_id, path_text in sorted(output_paths.items())
        },
        "rows_per_arm": len(topics),
        "target_rule": protocol["blinding"]["round_2_target_rule"],
        "arm_aliases": {
            arm_id: arm_by_id[arm_id]["alias"] for arm_id in sorted(arm_by_id)
        },
    }
    write_json(output_dir / "preparation_receipt.json", receipt)
    return receipt


def token_set(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.lower()))


def jaccard_distance(left: str, right: str) -> float:
    left_tokens = token_set(left)
    right_tokens = token_set(right)
    union = left_tokens | right_tokens
    if not union:
        return 0.0
    return 1.0 - (len(left_tokens & right_tokens) / len(union))


def theme_marker_coverage(text: str, terms: list[str]) -> int:
    lower = text.lower()
    return sum(1 for term in terms if str(term).lower() in lower)


def response_contract(text: str, target_alias: str | None = None) -> dict[str, Any]:
    length = len(text)
    has_think_tag = "<think>" in text.lower() or "</think>" in text.lower()
    has_position = "position:" in text.lower()
    has_moral_reason = "moral reason:" in text.lower()
    names_target = target_alias is None or target_alias.lower() in text.lower()
    valid = (
        60 <= length <= 1200
        and not has_think_tag
        and bool(text.strip())
        and names_target
    )
    return {
        "valid": valid,
        "characters": length,
        "has_think_tag": has_think_tag,
        "has_position_label": has_position,
        "has_moral_reason_label": has_moral_reason,
        "names_target": names_target,
        "strict_format": has_position and has_moral_reason,
    }


def round2_target_alias(row: dict[str, Any]) -> str:
    metadata = row.get("probe_metadata")
    if not isinstance(metadata, dict):
        raise TypeError(f"Round-two row lacks metadata: {row.get('example_id')}")
    target_alias = metadata.get("target_alias")
    if not isinstance(target_alias, str) or not target_alias:
        raise ValueError(f"Round-two row lacks target_alias: {row.get('example_id')}")
    return target_alias


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def analyze(
    protocol_path: Path,
    topics_path: Path,
    round1_paths: dict[str, Path],
    round2_paths: dict[str, Path],
    output_dir: Path,
) -> dict[str, Any]:
    protocol, topics, arms = load_contract(protocol_path, topics_path)
    expected_arm_ids = {str(arm["arm_id"]) for arm in arms}
    for round_name, paths in (("round one", round1_paths), ("round two", round2_paths)):
        if set(paths) != expected_arm_ids:
            raise ValueError(
                f"{round_name} arms mismatch: missing={sorted(expected_arm_ids - set(paths))} "
                f"extra={sorted(set(paths) - expected_arm_ids)}"
            )
    round1 = {
        arm_id: load_generation_map(path, topics)
        for arm_id, path in round1_paths.items()
    }
    round2 = {
        arm_id: load_generation_map(path, topics)
        for arm_id, path in round2_paths.items()
    }
    arm_by_id = {str(arm["arm_id"]): arm for arm in arms}

    per_arm: dict[str, dict[str, Any]] = {}
    for arm in arms:
        arm_id = str(arm["arm_id"])
        r1_contracts = [
            response_contract(round1[arm_id][str(topic["topic_id"])]["response"])
            for topic in topics
        ]
        r2_contracts = [
            response_contract(
                round2[arm_id][str(topic["topic_id"])]["response"],
                round2_target_alias(round2[arm_id][str(topic["topic_id"])]),
            )
            for topic in topics
        ]
        marker_scores_r1 = [
            theme_marker_coverage(
                round1[arm_id][str(topic["topic_id"])]["response"],
                list(topic["diagnostic_terms"]),
            )
            for topic in topics
        ]
        marker_scores_r2 = [
            theme_marker_coverage(
                round2[arm_id][str(topic["topic_id"])]["response"],
                list(topic["diagnostic_terms"]),
            )
            for topic in topics
        ]
        per_arm[arm_id] = {
            "alias": arm["alias"],
            "kind": arm["kind"],
            "construct_id": arm["construct_id"],
            "prior_status": arm["prior_status"],
            "round_1_valid_rate": mean([float(row["valid"]) for row in r1_contracts]),
            "round_2_valid_rate": mean([float(row["valid"]) for row in r2_contracts]),
            "round_1_strict_format_rate": mean(
                [float(row["strict_format"]) for row in r1_contracts]
            ),
            "round_2_strict_format_rate": mean(
                [float(row["strict_format"]) for row in r2_contracts]
            ),
            "round_1_mean_theme_marker_coverage": mean(
                [float(score) for score in marker_scores_r1]
            ),
            "round_2_mean_theme_marker_coverage": mean(
                [float(score) for score in marker_scores_r2]
            ),
        }

    topic_analyses: list[dict[str, Any]] = []
    highlights: list[dict[str, Any]] = []
    for topic in topics:
        topic_id = str(topic["topic_id"])
        candidates: list[dict[str, Any]] = []
        for left_arm, right_arm in itertools.combinations(arms, 2):
            left_id = str(left_arm["arm_id"])
            right_id = str(right_arm["arm_id"])
            left_row = round2[left_id][topic_id]
            right_row = round2[right_id][topic_id]
            left_response = str(left_row["response"])
            right_response = str(right_row["response"])
            left_contract = response_contract(
                left_response, round2_target_alias(left_row)
            )
            right_contract = response_contract(
                right_response, round2_target_alias(right_row)
            )
            marker_left = theme_marker_coverage(
                left_response, list(topic["diagnostic_terms"])
            )
            marker_right = theme_marker_coverage(
                right_response, list(topic["diagnostic_terms"])
            )
            distance = jaccard_distance(left_response, right_response)
            direct_left = int(left_contract["names_target"])
            direct_right = int(right_contract["names_target"])
            pair_score = (
                marker_left + marker_right + direct_left + direct_right + distance
            )
            pair_ids = sorted([left_id, right_id])
            candidates.append(
                {
                    "arm_ids": pair_ids,
                    "valid": bool(left_contract["valid"] and right_contract["valid"]),
                    "pair_score": round(pair_score, 6),
                    "theme_marker_coverage": {
                        left_id: marker_left,
                        right_id: marker_right,
                    },
                    "direct_reply": {
                        left_id: bool(direct_left),
                        right_id: bool(direct_right),
                    },
                    "lexical_jaccard_distance": round(distance, 6),
                }
            )
        valid_candidates = [candidate for candidate in candidates if candidate["valid"]]
        selected = (
            min(
                valid_candidates,
                key=lambda candidate: (
                    -float(candidate["pair_score"]),
                    tuple(candidate["arm_ids"]),
                ),
            )
            if valid_candidates
            else None
        )
        topic_analysis = {
            "topic_id": topic_id,
            "title": topic["title"],
            "quran_refs": topic["quran_refs"],
            "source_review_status": topic["source_review_status"],
            "pair_candidates": candidates,
            "selected_pair": selected,
        }
        topic_analyses.append(topic_analysis)
        if selected is not None:
            quoted_rows = []
            for arm_id in selected["arm_ids"]:
                row = round2[arm_id][topic_id]
                quoted_rows.append(
                    {
                        "arm_id": arm_id,
                        "alias": arm_by_id[arm_id]["alias"],
                        "target_alias": round2_target_alias(row),
                        "response": row["response"],
                        "row_sha256": row_sha256(row),
                    }
                )
            highlights.append(
                {
                    "topic_id": topic_id,
                    "title": topic["title"],
                    "quran_refs": topic["quran_refs"],
                    "selection": selected,
                    "quotes": quoted_rows,
                }
            )

    total_rows = sum(len(rows) for rows in round1.values()) + sum(
        len(rows) for rows in round2.values()
    )
    expected_total = int(protocol["generation"]["expected_total_rows"])
    if total_rows != expected_total:
        raise ValueError(
            f"Expected {expected_total} generation rows, found {total_rows}"
        )

    analysis_payload = {
        "schema_version": "quranic_moral_village_analysis_v1",
        "status": "completed_exploratory",
        "created_at_utc": utc_now(),
        "experiment_id": protocol["experiment_id"],
        "row_count": total_rows,
        "expected_row_count": expected_total,
        "per_arm": per_arm,
        "topics": topic_analyses,
        "highlight_count": len(highlights),
        "highlights": highlights,
        "claim_boundary": protocol["claim_boundary"],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis_path = output_dir / "analysis.json"
    transcript_path = output_dir / "full_transcript.md"
    highlights_path = output_dir / "highlights.md"
    write_json(analysis_path, analysis_payload)
    transcript_path.write_text(
        render_transcript(topics, arms, round1, round2),
        encoding="utf-8",
        newline="\n",
    )
    highlights_path.write_text(
        render_highlights(highlights),
        encoding="utf-8",
        newline="\n",
    )

    receipt = {
        "schema_version": "quranic_moral_village_execution_receipt_v1",
        "status": "completed_exploratory",
        "created_at_utc": utc_now(),
        "experiment_id": protocol["experiment_id"],
        "protocol_path": str(protocol_path.resolve()),
        "protocol_sha256": sha256_file(protocol_path),
        "topics_path": str(topics_path.resolve()),
        "topics_sha256": sha256_file(topics_path),
        "generation_inputs": {
            "round_1": {
                arm_id: {"path": str(path), "sha256": sha256_file(path)}
                for arm_id, path in sorted(round1_paths.items())
            },
            "round_2": {
                arm_id: {"path": str(path), "sha256": sha256_file(path)}
                for arm_id, path in sorted(round2_paths.items())
            },
        },
        "row_count": total_rows,
        "exact_join_complete": total_rows == expected_total,
        "outputs": {
            "analysis": {
                "path": str(analysis_path.resolve()),
                "sha256": sha256_file(analysis_path),
            },
            "full_transcript": {
                "path": str(transcript_path.resolve()),
                "sha256": sha256_file(transcript_path),
            },
            "highlights": {
                "path": str(highlights_path.resolve()),
                "sha256": sha256_file(highlights_path),
            },
        },
        "human_highlight_override_used": False,
        "promotion_authorized": False,
        "scientific_result": "exploratory_qualitative_only",
        "claim_boundary": protocol["claim_boundary"],
    }
    write_json(output_dir / "execution_receipt.json", receipt)
    return receipt


def render_transcript(
    topics: list[dict[str, Any]],
    arms: list[dict[str, Any]],
    round1: dict[str, dict[str, dict[str, Any]]],
    round2: dict[str, dict[str, dict[str, Any]]],
) -> str:
    lines = [
        "# Quran-anchor moral village: complete transcript",
        "",
        (
            "All statements are exploratory model outputs. Source mappings remain "
            "`scholar_review_pending`; this transcript is not a validated theological "
            "interpretation or a confirmatory behavioral endpoint."
        ),
        "",
    ]
    for topic in topics:
        topic_id = str(topic["topic_id"])
        refs = ", ".join(topic["quran_refs"])
        lines.extend(
            [
                f"## {topic['order']}. {topic['title']}",
                "",
                f"Registered operational source anchors: {refs}.",
                "",
                str(topic["scenario"]),
                "",
                "### Independent statements",
                "",
            ]
        )
        for arm in arms:
            arm_id = str(arm["arm_id"])
            lines.extend(
                [
                    f"#### {arm['alias']}",
                    "",
                    str(round1[arm_id][topic_id]["response"]),
                    "",
                ]
            )
        lines.extend(["### Reply turn", ""])
        for arm in arms:
            arm_id = str(arm["arm_id"])
            row = round2[arm_id][topic_id]
            lines.extend(
                [
                    f"#### {arm['alias']} → {round2_target_alias(row)}",
                    "",
                    str(row["response"]),
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def render_highlights(highlights: list[dict[str, Any]]) -> str:
    lines = [
        "# Deterministically selected village highlights",
        "",
        (
            "These pairs were selected by the frozen marker-coverage, direct-reply, "
            "and lexical-distance rule. No human override was permitted. They are "
            "qualitative illustrations only; consult `full_transcript.md` for every row."
        ),
        "",
    ]
    for highlight in highlights:
        refs = ", ".join(highlight["quran_refs"])
        lines.extend(
            [
                f"## {highlight['title']}",
                "",
                (
                    f"Registered operational source anchors: {refs}. Pair score: "
                    f"{highlight['selection']['pair_score']}."
                ),
                "",
            ]
        )
        for quote in highlight["quotes"]:
            lines.extend(
                [
                    f"### {quote['alias']} → {quote['target_alias']}",
                    "",
                    str(quote["response"]),
                    "",
                    f"Row SHA-256: `{quote['row_sha256']}`",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--protocol", type=Path, required=True)
    verify_parser.add_argument("--topics", type=Path, required=True)
    verify_parser.add_argument("--round1-prompts", type=Path, required=True)
    verify_parser.add_argument("--output", type=Path, required=True)

    prepare_parser = subparsers.add_parser("prepare-round2")
    prepare_parser.add_argument("--protocol", type=Path, required=True)
    prepare_parser.add_argument("--topics", type=Path, required=True)
    prepare_parser.add_argument(
        "--round1", action="append", default=[], metavar="ARM_ID=PATH"
    )
    prepare_parser.add_argument("--output-dir", type=Path, required=True)

    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("--protocol", type=Path, required=True)
    analyze_parser.add_argument("--topics", type=Path, required=True)
    analyze_parser.add_argument(
        "--round1", action="append", default=[], metavar="ARM_ID=PATH"
    )
    analyze_parser.add_argument(
        "--round2", action="append", default=[], metavar="ARM_ID=PATH"
    )
    analyze_parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    protocol_path = args.protocol.resolve()
    topics_path = args.topics.resolve()
    if args.command == "verify":
        receipt = verify_frozen_inputs(
            protocol_path,
            topics_path,
            args.round1_prompts.resolve(),
        )
        write_json(args.output.resolve(), receipt)
    elif args.command == "prepare-round2":
        receipt = build_round2_prompts(
            protocol_path,
            topics_path,
            parse_named_paths(args.round1),
            args.output_dir.resolve(),
        )
    elif args.command == "analyze":
        receipt = analyze(
            protocol_path,
            topics_path,
            parse_named_paths(args.round1),
            parse_named_paths(args.round2),
            args.output_dir.resolve(),
        )
    else:
        raise AssertionError(args.command)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
