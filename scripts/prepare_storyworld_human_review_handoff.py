#!/usr/bin/env python3
"""Create readable review packets and deliberately invalid receipt templates."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json, write_jsonl
from alignment_harness.trajectory_curriculum import read_jsonl
from scripts.apply_recovered_storyworld_extras_reviews import validate_recovered_reviews
from scripts.apply_storyworld_review_receipts import validate_review_receipts
from scripts.apply_storyworld_support_prompt_reviews import validate_support_prompt_reviews


PLACEHOLDER_DECISION = "REPLACE_WITH_A_VALID_DECISION"
PLACEHOLDER_TEXT = "REPLACE_ME"
PLACEHOLDER_TIME = "REPLACE_WITH_ISO_8601_TIMEZONE_TIMESTAMP"


def _write_text(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _must_reject(label: str, action: Callable[[], Any]) -> str:
    try:
        action()
    except ValueError as exc:
        return f"{type(exc).__name__}: {exc}"
    raise ValueError(f"untouched {label} receipt templates unexpectedly passed validation")


def _world_packet(queue: dict[str, Any]) -> str:
    tasks_by_world: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in queue["review_tasks"]:
        tasks_by_world[str(task["world_id"])].append(task)
    lines = [
        "# Storyworld review packet",
        "",
        "Review the exact source and substantive hash listed below. Complete one receipt per task; do not edit task IDs or hashes.",
        "",
        f"Worlds: {queue['counts']['worlds']}  ",
        f"Tasks: {queue['counts']['review_tasks']}  ",
        f"Package SHA-256: `{queue['package_sha256']}`",
        "",
    ]
    for world in queue["worlds"]:
        world_id = str(world["world_id"])
        lines.extend(
            [
                f"## {world_id}",
                "",
                f"- Family: `{world['family_id']}`",
                f"- Split: `{world['source_split']}`",
                f"- Source: `{world['source_path']}`",
                f"- Reviewable content SHA-256: `{world['reviewable_content_sha256']}`",
                f"- Transition graph SHA-256: `{world['transition_graph_sha256']}`",
                f"- Motif: `{world.get('theological_motif')}`",
                f"- Claim boundary: {world['claim_boundary']}",
                "",
                "Tasks:",
                "",
            ]
        )
        for task in sorted(
            tasks_by_world[world_id], key=lambda item: str(item["review_type"])
        ):
            lines.append(
                f"- `{task['review_task_id']}` — `{task['review_type']}`"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def _prompt_packet(queue: dict[str, Any]) -> str:
    lines = [
        "# Support pilot prompt review packet",
        "",
        "Review all 76 complete system/user prompt cells. A receipt must explicitly confirm every listed scope.",
        "",
        f"Queue content SHA-256: `{queue['queue_content_sha256']}`",
        "",
    ]
    for index, task in enumerate(queue["review_tasks"], start=1):
        lines.extend(
            [
                f"## {index}. {task['review_task_id']}",
                "",
                f"- Slice/category/arm: `{task['slice']}` / `{task['category']}` / `{task['arm']}`",
                f"- Job SHA-256: `{task['job_content_sha256']}`",
                f"- Scenario SHA-256: `{task['scenario_content_sha256']}`",
                f"- Messages SHA-256: `{task['messages_content_sha256']}`",
                f"- Teacher: `{task['model_id']}` at `{task['reasoning_effort']}` effort",
                "",
                "### System",
                "",
                str(task["messages"][0]["content"]),
                "",
                "### User",
                "",
                str(task["messages"][1]["content"]),
                "",
                "### Required scope confirmations",
                "",
            ]
        )
        lines.extend(f"- {scope}" for scope in task["required_review_scope"])
        lines.append("")
    return "\n".join(lines) + "\n"


def prepare_handoff(
    world_queue_path: Path,
    prompt_queue_path: Path,
    recovered_queue_path: Path,
    recovered_rows_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    world_queue_path = world_queue_path.resolve()
    prompt_queue_path = prompt_queue_path.resolve()
    recovered_queue_path = recovered_queue_path.resolve()
    recovered_rows_path = recovered_rows_path.resolve()
    output_dir = output_dir.resolve()
    world_queue = read_json(world_queue_path)
    prompt_queue = read_json(prompt_queue_path)
    recovered_queue = read_json(recovered_queue_path)
    recovered_rows = read_jsonl(recovered_rows_path)
    if world_queue.get("schema_version") != "storyworld_review_queue_v1":
        raise ValueError("unexpected world review queue schema")
    if prompt_queue.get("schema_version") != "storyworld_support_prompt_review_queue_v1":
        raise ValueError("unexpected prompt review queue schema")
    if recovered_queue.get("schema_version") != "storyworld_recovered_extras_review_queue_v1":
        raise ValueError("unexpected recovered review queue schema")
    if recovered_queue.get("rows_sha256") != sha256_file(recovered_rows_path):
        raise ValueError("recovered review queue does not bind supplied row bytes")

    world_templates = [
        {
            "schema_version": "storyworld_review_receipt_v1",
            "review_task_id": task["review_task_id"],
            "review_type": task["review_type"],
            "reviewer_pseudonym": PLACEHOLDER_TEXT,
            "decision": PLACEHOLDER_DECISION,
            "scope_notes": PLACEHOLDER_TEXT,
            "content_sha256": task["reviewable_content_sha256"],
            "signed_at": PLACEHOLDER_TIME,
            "signature_or_external_receipt": PLACEHOLDER_TEXT,
        }
        for task in world_queue["review_tasks"]
    ]
    prompt_templates = [
        {
            "schema_version": "storyworld_support_prompt_review_receipt_v1",
            "review_task_id": task["review_task_id"],
            "job_content_sha256": task["job_content_sha256"],
            "scenario_content_sha256": task["scenario_content_sha256"],
            "messages_content_sha256": task["messages_content_sha256"],
            "decision": PLACEHOLDER_DECISION,
            "confirmed_scopes": [],
            "reviewer_pseudonym": PLACEHOLDER_TEXT,
            "scope_notes": PLACEHOLDER_TEXT,
            "signed_at": PLACEHOLDER_TIME,
            "signature_or_external_receipt": PLACEHOLDER_TEXT,
        }
        for task in prompt_queue["review_tasks"]
    ]
    recovered_task_map = {
        str(task["record_id"]): task for task in recovered_queue["review_tasks"]
    }
    recovered_row_map = {str(row["record_id"]): row for row in recovered_rows}
    if set(recovered_task_map) != set(recovered_row_map):
        raise ValueError("recovered queue and row record-ID sets differ")
    recovered_templates = [
        {
            "schema_version": "storyworld_recovered_row_review_receipt_v1",
            "review_task_id": task["review_task_id"],
            "record_content_sha256": task["record_content_sha256"],
            "review_type": task["review_type"],
            "decision": PLACEHOLDER_DECISION,
            "confirmed_checks": [],
            "reviewer_pseudonym": PLACEHOLDER_TEXT,
            "scope_notes": PLACEHOLDER_TEXT,
            "signed_at": PLACEHOLDER_TIME,
            "signature_or_external_receipt": PLACEHOLDER_TEXT,
        }
        for task in recovered_queue["review_tasks"]
    ]
    recovered_packet = [
        {
            "review_task": task,
            "messages": recovered_row_map[str(task["record_id"])]["messages"],
            "external_provenance": recovered_row_map[str(task["record_id"])][
                "external_provenance"
            ],
        }
        for task in recovered_queue["review_tasks"]
    ]
    license_template = {
        "schema_version": "storyworld_recovered_source_license_receipt_v1",
        "source_id": recovered_queue["source_id"],
        "decision": "REPLACE_WITH_approved_for_research_training_OR_rejected",
        "rows_sha256": recovered_queue["rows_sha256"],
        "reviewed_by": PLACEHOLDER_TEXT,
        "signed_at": PLACEHOLDER_TIME,
        "signature_or_external_receipt": PLACEHOLDER_TEXT,
    }

    fail_closed = {
        "world_templates": _must_reject(
            "world", lambda: validate_review_receipts(world_queue, world_templates)
        ),
        "prompt_templates": _must_reject(
            "prompt",
            lambda: validate_support_prompt_reviews(prompt_queue, prompt_templates),
        ),
        "recovered_templates": _must_reject(
            "recovered",
            lambda: validate_recovered_reviews(
                recovered_queue, recovered_templates, license_template
            ),
        ),
    }

    output_dir.mkdir(parents=True, exist_ok=False)
    paths = {
        "world_packet": output_dir / "WORLD_REVIEW_PACKET.md",
        "world_receipts": output_dir / "WORLD_REVIEW_RECEIPTS_TEMPLATE.jsonl",
        "prompt_packet": output_dir / "SUPPORT_PROMPT_REVIEW_PACKET.md",
        "prompt_receipts": output_dir / "SUPPORT_PROMPT_REVIEW_RECEIPTS_TEMPLATE.jsonl",
        "recovered_packet": output_dir / "RECOVERED_ROW_REVIEW_PACKET.jsonl",
        "recovered_receipts": output_dir / "RECOVERED_ROW_REVIEW_RECEIPTS_TEMPLATE.jsonl",
        "recovered_license": output_dir / "RECOVERED_LICENSE_RECEIPT_TEMPLATE.json",
    }
    _write_text(paths["world_packet"], _world_packet(world_queue))
    write_jsonl(paths["world_receipts"], world_templates)
    _write_text(paths["prompt_packet"], _prompt_packet(prompt_queue))
    write_jsonl(paths["prompt_receipts"], prompt_templates)
    write_jsonl(paths["recovered_packet"], recovered_packet)
    write_jsonl(paths["recovered_receipts"], recovered_templates)
    write_json(paths["recovered_license"], license_template)

    files = {
        key: {
            "path": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for key, path in paths.items()
    }
    body = {
        "schema_version": "storyworld_human_review_handoff_v1",
        "status": "templates_incomplete_external_review_required",
        "source_queues": {
            "world": sha256_file(world_queue_path),
            "support_prompt": sha256_file(prompt_queue_path),
            "recovered": sha256_file(recovered_queue_path),
            "recovered_rows": sha256_file(recovered_rows_path),
        },
        "counts": {
            "world_receipts_required": len(world_templates),
            "support_prompt_receipts_required": len(prompt_templates),
            "recovered_row_receipts_required": len(recovered_templates),
            "recovered_license_receipts_required": 1,
            "total_human_decisions_required": (
                len(world_templates) + len(prompt_templates) + len(recovered_templates) + 1
            ),
            "world_review_types": dict(
                sorted(Counter(task["review_type"] for task in world_queue["review_tasks"]).items())
            ),
            "recovered_review_types": dict(
                sorted(
                    Counter(
                        task["review_type"] for task in recovered_queue["review_tasks"]
                    ).items()
                )
            ),
        },
        "files": files,
        "untouched_templates_rejected": True,
        "fail_closed_validation_errors": fail_closed,
        "human_review_complete": False,
        "spend_authorized": False,
        "training_approved_rows": 0,
        "instructions": [
            "Review the packet content corresponding to each task.",
            "Replace every placeholder; explicitly populate confirmed scopes/checks.",
            "Do not change task IDs or content hashes.",
            "Validate completed files with the existing apply scripts before using --apply.",
        ],
        "passed": True,
    }
    manifest = {**body, "handoff_content_sha256": sha256_json(body)}
    write_json(output_dir / "HANDOFF_MANIFEST.json", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world-review-queue", type=Path, required=True)
    parser.add_argument("--prompt-review-queue", type=Path, required=True)
    parser.add_argument("--recovered-review-queue", type=Path, required=True)
    parser.add_argument("--recovered-rows", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = prepare_handoff(
        args.world_review_queue,
        args.prompt_review_queue,
        args.recovered_review_queue,
        args.recovered_rows,
        args.output_dir,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
