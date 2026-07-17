#!/usr/bin/env python3
"""Recover exact file payloads embedded in successful Silico session tool calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPEC = REPO_ROOT / "experiments/frame_internalization_sft_v1/predecessor_recovery_spec_v1.json"
SECRET_PATTERNS = [
    re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"ghp_[A-Za-z0-9]{20,}"),
    re.compile(rb"Bearer\s+eyJ[A-Za-z0-9._-]{20,}", re.IGNORECASE),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--check", action="store_true", help="Verify committed outputs without rewriting them.")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_session(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid session JSONL {path} line {line_no}: {exc}") from exc
        if isinstance(value, dict):
            rows.append(value)
    return rows


def tool_calls(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for row in rows:
        if row.get("type") != "message":
            continue
        for content in row.get("message", {}).get("content", []):
            if content.get("type") == "toolCall":
                calls.append(content)
    return calls


def successful_results(rows: list[dict[str, Any]]) -> dict[str, str]:
    results: dict[str, str] = {}
    for row in rows:
        if row.get("type") != "message":
            continue
        message = row.get("message", {})
        if message.get("role") != "toolResult" or message.get("isError"):
            continue
        tool_call_id = message.get("toolCallId")
        if not tool_call_id:
            continue
        results[str(tool_call_id)] = "".join(
            str(content.get("text", ""))
            for content in message.get("content", [])
            if content.get("type") == "text"
        )
    return results


def slice_tool_result(content: str, entry: dict[str, Any]) -> str:
    """Apply an exact, declarative substring extraction to a tool result."""
    start_after = entry.get("start_after")
    end_before = entry.get("end_before")
    start = 0
    if start_after is not None:
        marker = str(start_after)
        if content.count(marker) != 1:
            raise ValueError(
                f"Tool-result start marker occurrence count is {content.count(marker)}: "
                f"{entry.get('tool_call_id')}"
            )
        start = content.index(marker) + len(marker)
    end = len(content)
    if end_before is not None:
        marker = str(end_before)
        count = content[start:].count(marker)
        if count != 1:
            raise ValueError(
                f"Tool-result end marker occurrence count is {count}: {entry.get('tool_call_id')}"
            )
        end = content.index(marker, start)
    if end < start:
        raise ValueError(f"Invalid tool-result slice: {entry.get('tool_call_id')}")
    return content[start:end]


def safe_output_path(output_root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"Unsafe output path: {relative}")
    path = (output_root / Path(*pure.parts)).resolve()
    if output_root.resolve() not in path.parents:
        raise ValueError(f"Output path escapes root: {relative}")
    return path


def apply_edits(text: str, edits: list[dict[str, Any]], remote_path: str) -> str:
    for index, edit in enumerate(edits):
        old = str(edit.get("oldText", ""))
        new = str(edit.get("newText", ""))
        count = text.count(old)
        if not old or count != 1:
            raise ValueError(
                f"Cannot replay edit {index} for {remote_path}: oldText occurrence count is {count}"
            )
        text = text.replace(old, new, 1)
    return text


def assert_no_embedded_secrets(relative: str, payload: bytes) -> None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(payload):
            raise ValueError(f"Possible credential in recovered payload: {relative}")


def recover(spec_path: Path) -> tuple[Path, dict[str, Any], dict[str, bytes]]:
    spec_path = spec_path.resolve()
    spec = read_json(spec_path)
    if spec.get("schema_version") != "frame_internalization_predecessor_recovery_spec.v1":
        raise ValueError("Unexpected recovery spec schema_version")
    output_root = (REPO_ROOT / str(spec["output_root"])).resolve()
    sessions: dict[str, dict[str, Any]] = {}
    rows_by_session: dict[str, list[dict[str, Any]]] = {}
    for entry in spec["sessions"]:
        session_id = str(entry["session_id"])
        source_path = Path(str(entry["external_path"]))
        if not source_path.is_file():
            raise FileNotFoundError(f"Missing raw session: {source_path}")
        if source_path.stat().st_size != int(entry["bytes"]):
            raise ValueError(f"Raw session byte count drift: {session_id}")
        if sha256_file(source_path) != entry["sha256"]:
            raise ValueError(f"Raw session SHA-256 drift: {session_id}")
        rendered_path = (REPO_ROOT / str(entry["repo_rendered_path"])).resolve()
        if sha256_file(rendered_path) != entry["repo_rendered_sha256"]:
            raise ValueError(f"Rendered session SHA-256 drift: {session_id}")
        sessions[session_id] = entry
        rows_by_session[session_id] = load_session(source_path)

    payloads: dict[str, bytes] = {}
    provenance: dict[str, dict[str, Any]] = {}
    read_by_remote: dict[tuple[str, str], tuple[str, str]] = {}
    for session_id, rows in rows_by_session.items():
        results = successful_results(rows)
        for call in tool_calls(rows):
            if call.get("name") != "read" or call.get("id") not in results:
                continue
            remote_path = str((call.get("arguments") or {}).get("path", ""))
            read_by_remote[(session_id, remote_path)] = (str(call["id"]), results[str(call["id"])])

    for entry in spec["read_extractions"]:
        session_id = str(entry["session_id"])
        remote_path = str(entry["remote_path"])
        output_path = str(entry["output_path"])
        key = (session_id, remote_path)
        if key not in read_by_remote:
            raise ValueError(f"Successful read payload not found: {key}")
        tool_call_id, content = read_by_remote[key]
        payloads[output_path] = content.encode("utf-8")
        provenance[output_path] = {
            "recovery_method": "successful_read_tool_result",
            "session_id": session_id,
            "experiment_id": sessions[session_id]["experiment_id"],
            "tool_call_id": tool_call_id,
            "remote_path": remote_path,
        }

    calls_by_session: dict[str, dict[str, dict[str, Any]]] = {
        session_id: {str(call.get("id")): call for call in tool_calls(rows)}
        for session_id, rows in rows_by_session.items()
    }
    for entry in spec.get("tool_result_extractions", []):
        session_id = str(entry["session_id"])
        tool_call_id = str(entry["tool_call_id"])
        output_path = str(entry["output_path"])
        results = successful_results(rows_by_session[session_id])
        if tool_call_id not in results or tool_call_id not in calls_by_session[session_id]:
            raise ValueError(f"Successful tool result not found: {(session_id, tool_call_id)}")
        call = calls_by_session[session_id][tool_call_id]
        content = slice_tool_result(results[tool_call_id], entry)
        payloads[output_path] = content.encode("utf-8")
        provenance[output_path] = {
            "recovery_method": "successful_tool_result_slice"
            if entry.get("start_after") is not None or entry.get("end_before") is not None
            else "successful_tool_result",
            "session_id": session_id,
            "experiment_id": sessions[session_id]["experiment_id"],
            "tool_call_id": tool_call_id,
            "tool_name": call.get("name"),
        }
        if entry.get("start_after") is not None:
            provenance[output_path]["start_after"] = entry["start_after"]
        if entry.get("end_before") is not None:
            provenance[output_path]["end_before"] = entry["end_before"]

    for entry in spec.get("tool_argument_extractions", []):
        session_id = str(entry["session_id"])
        tool_call_id = str(entry["tool_call_id"])
        argument_name = str(entry["argument_name"])
        output_path = str(entry["output_path"])
        call = calls_by_session[session_id].get(tool_call_id)
        if call is None:
            raise ValueError(f"Tool call not found: {(session_id, tool_call_id)}")
        results = successful_results(rows_by_session[session_id])
        if tool_call_id not in results:
            raise ValueError(f"Tool call did not have a successful result: {(session_id, tool_call_id)}")
        arguments = call.get("arguments") or {}
        if argument_name not in arguments or not isinstance(arguments[argument_name], str):
            raise ValueError(
                f"String tool argument not found: {(session_id, tool_call_id, argument_name)}"
            )
        payloads[output_path] = str(arguments[argument_name]).encode("utf-8")
        provenance[output_path] = {
            "recovery_method": "successful_tool_call_argument",
            "session_id": session_id,
            "experiment_id": sessions[session_id]["experiment_id"],
            "tool_call_id": tool_call_id,
            "tool_name": call.get("name"),
            "argument_name": argument_name,
        }

    replays = spec.get("mutation_replays")
    if replays is None and "mutation_replay" in spec:
        replays = [spec["mutation_replay"]]
    for replay in replays or []:
        session_id = str(replay["session_id"])
        prefix = str(replay["remote_prefix"])
        output_prefix = str(replay["output_prefix"])
        allowed_suffixes = set(str(value) for value in replay["allowed_suffixes"])
        replay_files: dict[str, str] = {}
        replay_sources: dict[str, list[str]] = {}
        for seed in replay.get("seed_files", []):
            target = str(seed["target_remote_path"])
            source_output = str(seed["source_output_path"])
            replay_files[target] = payloads[source_output].decode("utf-8")
            replay_sources[target] = [f"seed:{source_output}"]

        results = successful_results(rows_by_session[session_id])
        for call in tool_calls(rows_by_session[session_id]):
            if call.get("id") not in results or call.get("name") not in {"write", "edit"}:
                continue
            arguments = call.get("arguments") or {}
            remote_path = str(arguments.get("path", ""))
            if not remote_path.startswith(prefix):
                continue
            suffix = PurePosixPath(remote_path).suffix
            if suffix not in allowed_suffixes:
                continue
            if call["name"] == "write":
                replay_files[remote_path] = str(arguments.get("content", ""))
                replay_sources[remote_path] = [f"write:{call['id']}"]
            else:
                if remote_path not in replay_files:
                    raise ValueError(f"No replay base for successful edit: {remote_path}")
                replay_files[remote_path] = apply_edits(
                    replay_files[remote_path], list(arguments.get("edits") or []), remote_path
                )
                replay_sources[remote_path].append(f"edit:{call['id']}")

        for remote_path, content in sorted(replay_files.items()):
            relative_remote = remote_path[len(prefix) :]
            output_path = str(PurePosixPath(output_prefix) / PurePosixPath(relative_remote))
            payloads[output_path] = content.encode("utf-8")
            provenance[output_path] = {
                "recovery_method": "successful_write_edit_replay",
                "session_id": session_id,
                "experiment_id": sessions[session_id]["experiment_id"],
                "tool_operations": replay_sources[remote_path],
                "remote_path": remote_path,
            }

    file_rows = []
    for relative, payload in sorted(payloads.items()):
        assert_no_embedded_secrets(relative, payload)
        file_rows.append(
            {
                "path": relative,
                "sha256": sha256_bytes(payload),
                "bytes": len(payload),
                **provenance[relative],
            }
        )
    manifest = {
        "schema_version": "frame_internalization_predecessor_session_extraction.v1",
        "created_at": "2026-07-17",
        "epistemic_status": "session_embedded_payloads_not_canonical_experiment_bundles",
        "spec_path": str(spec_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "spec_sha256": sha256_file(spec_path),
        "source_sessions": [
            {
                "session_id": entry["session_id"],
                "experiment_id": entry["experiment_id"],
                "sha256": entry["sha256"],
                "bytes": entry["bytes"],
                "repo_rendered_path": entry["repo_rendered_path"],
                "repo_rendered_sha256": entry["repo_rendered_sha256"],
            }
            for entry in spec["sessions"]
        ],
        "files": file_rows,
        "claim_boundary": [
            "Each file is exact text embedded in a successful recorded tool operation.",
            "The extraction proves recovered payload identity relative to the raw session hash, not identity to an unavailable canonical artifact bundle.",
            "Summary JSON and figures are recovered result evidence but cannot replace raw generations, complete prompt universes, activations, or judge receipts."
        ],
    }
    return output_root, manifest, payloads


def main() -> int:
    args = parse_args()
    try:
        output_root, manifest, payloads = recover(args.spec)
        manifest_path = output_root / "extraction_manifest.json"
        if args.check:
            failures: list[str] = []
            for relative, expected in payloads.items():
                path = safe_output_path(output_root, relative)
                if not path.is_file() or path.read_bytes() != expected:
                    failures.append(relative)
            expected_manifest = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
            if not manifest_path.is_file() or manifest_path.read_bytes() != expected_manifest:
                failures.append("extraction_manifest.json")
            if failures:
                print(json.dumps({"status": "failed", "drift": failures}, indent=2))
                return 1
            print(json.dumps({"status": "passed", "files": len(payloads), "manifest": str(manifest_path)}, indent=2))
            return 0

        for relative, payload in payloads.items():
            path = safe_output_path(output_root, relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_bytes((json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        print(json.dumps({"status": "recovered", "files": len(payloads), "manifest": str(manifest_path)}, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
