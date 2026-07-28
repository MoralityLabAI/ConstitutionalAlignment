#!/usr/bin/env python3
"""Serve one exported constitutional HRM checkpoint through a local OpenAI API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import numpy as np
from tokenizers import Tokenizer

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.constitutional_hrm_eval_v2 import (
    ACTION_LINE,
    encode_raw_text,
    read_jsonl,
    sha256_file,
)
from alignment_harness.constitutional_hrm_prime_adapter_v2 import (
    initial_prompt,
    next_mesh_tool_call,
)
from alignment_harness.constitutional_hrm_runtime_v2 import (
    ConstitutionalHrmRuntime,
)

TASK_FILES = (
    "jinn_moral_reasoner_tasks.jsonl",
    "moral_control_mesh_v2_tasks.jsonl",
    "quranic_village_replay.jsonl",
)


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument(
        "--official-root",
        type=Path,
        default=REPO_ROOT.parent / ".codex-cache" / "HRM-ac15626",
    )
    parser.add_argument(
        "--tokenizer",
        type=Path,
        default=REPO_ROOT
        / "artifacts"
        / "constitutional_hrm_200m_v2"
        / "tokenizer"
        / "tokenizer.json",
    )
    parser.add_argument(
        "--prompt-bundle",
        type=Path,
        default=REPO_ROOT
        / "artifacts"
        / "constitutional_hrm_200m_v2"
        / "generated"
        / "system_prompt_bundle_v2.json",
    )
    parser.add_argument("--hub-data-dir", required=True, type=Path)
    parser.add_argument(
        "--condition",
        choices=(
            "constitution_metta_full",
            "constitution_hash_only",
            "constitution_removed",
        ),
        default="constitution_removed",
    )
    parser.add_argument(
        "--moral-response-mode",
        choices=("raw_decode", "decision_contract"),
        default="raw_decode",
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--gpu-memory-fraction", type=float, default=0.80)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--request-log", required=True, type=Path)
    return parser.parse_args()


def construct_user_prompt(row: dict[str, Any]) -> str:
    return (
        f"{row['prompt']}\n\nVisible facts:\n"
        + "\n".join(
            f"- {fact['id']}: {fact['text']}" for fact in row["visible_facts"]
        )
        + "\n\nActions:\n"
        + "\n".join(
            f"- {action_id}: {action['text']}"
            for action_id, action in row["action_scores"].items()
        )
    )


def task_prompt(row: dict[str, Any]) -> tuple[str, str]:
    if row.get("scorer_id") == "jinn_moral_reasoner_policy_v2":
        user = construct_user_prompt(row)
    else:
        user = str(row["prompt"])
    return str(row["system_prompt"]), user


class PrimeAdapter:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.tokenizer = Tokenizer.from_file(str(args.tokenizer.resolve()))
        prompt_bundle = json.loads(
            args.prompt_bundle.resolve().read_text(encoding="utf-8")
        )
        self.condition_prompt = str(
            prompt_bundle["prompts"][args.condition]["text"]
        )
        self.tasks: dict[tuple[str, str], dict[str, Any]] = {}
        self.source_hashes: dict[str, str] = {}
        for filename in TASK_FILES:
            path = args.hub_data_dir.resolve() / filename
            self.source_hashes[filename] = sha256_file(path)
            for row in read_jsonl(path):
                key = task_prompt(row)
                if key in self.tasks:
                    raise ValueError(f"duplicate Prime prompt in {filename}")
                self.tasks[key] = row
        self.runtime = ConstitutionalHrmRuntime(
            checkpoint_path=args.checkpoint.resolve(),
            official_root=args.official_root.resolve(),
            device=args.device,
            gpu_memory_fraction=args.gpu_memory_fraction,
        )
        self.runtime_info = self.runtime.load()
        self.decision_ids = [
            self._required_token_id(f"<|decision:{index}|>")
            for index in range(4)
        ]
        self.eos_id = self._required_token_id("<|eos|>")
        self.inference_lock = threading.Lock()
        self.log_lock = threading.Lock()
        self.session_lock = threading.Lock()
        self.sessions: dict[str, dict[str, Any]] = {}
        self.request_log = args.request_log.resolve()
        self.request_log.parent.mkdir(parents=True, exist_ok=True)
        self.request_log.write_text("", encoding="utf-8")

    def _required_token_id(self, token: str) -> int:
        value = self.tokenizer.token_to_id(token)
        if value is None:
            raise ValueError(f"tokenizer is missing {token}")
        return int(value)

    def _decode(self, prediction: np.ndarray) -> str:
        values = list(map(int, prediction.tolist()))
        if self.eos_id in values:
            values = values[: values.index(self.eos_id)]
        return self.tokenizer.decode(values, skip_special_tokens=True).strip()

    def _predict(
        self,
        *,
        task: dict[str, Any],
        system: str,
        user: str,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        action_task = bool(task.get("action_scores"))
        body = f"{system}\n\n{user}".strip()
        if action_task:
            body = f"Evaluation item:\n{body}"
        text = f"{self.condition_prompt}\n\n{body}".strip()
        input_ids, token_audit = encode_raw_text(self.tokenizer, text)
        with self.inference_lock:
            prediction = self.runtime.predict(input_ids[None, :], batch_size=1)[0]
        return prediction, token_audit

    def _selected_action(
        self,
        *,
        task: dict[str, Any],
        user: str,
        prediction: np.ndarray,
    ) -> str | None:
        action_order = ACTION_LINE.findall(user)
        if set(action_order) != set(map(str, task.get("action_scores", {}))):
            action_order = list(map(str, task.get("action_scores", {})))
        try:
            decision_index = self.decision_ids.index(int(prediction[0]))
        except ValueError:
            return None
        return (
            action_order[decision_index]
            if decision_index < len(action_order)
            else None
        )

    def _append_log(self, payload: dict[str, Any]) -> None:
        with self.log_lock, self.request_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def completion(
        self,
        request: dict[str, Any],
        *,
        session_id: str,
    ) -> dict[str, Any]:
        messages = request.get("messages", [])
        if not isinstance(messages, list):
            raise TypeError("messages must be a list")
        system, user = initial_prompt(messages)
        task = self.tasks.get((system, user))
        if task is None:
            raise KeyError("request prompt is not in the pinned Prime Hub package")
        task_id = str(task.get("task_id", ""))
        with self.session_lock:
            cached = self.sessions.get(session_id)
        cache_hit = cached is not None
        if cached is not None and cached["task_id"] != task_id:
            raise ValueError("Prime session was reused across different tasks")
        if cached is None:
            prediction, token_audit = self._predict(
                task=task,
                system=system,
                user=user,
            )
            selected = self._selected_action(
                task=task,
                user=user,
                prediction=prediction,
            )
            cached = {
                "task_id": task_id,
                "prediction": prediction,
                "token_audit": token_audit,
                "selected_action_id": selected,
                "inference_cache_hit": cache_hit,
            }
            with self.session_lock:
                self.sessions[session_id] = cached
        else:
            prediction = cached["prediction"]
            token_audit = cached["token_audit"]
            selected = cached["selected_action_id"]
        scorer_id = str(task.get("scorer_id", ""))
        adapter_enforced_process = scorer_id == "moral_control_mesh_policy_v2"
        adapter_enforced_contract = (
            scorer_id == "jinn_moral_reasoner_policy_v2"
            and self.args.moral_response_mode == "decision_contract"
        )
        tool_call = None
        content: str | None
        finish_reason: str
        if adapter_enforced_process:
            tool_call = next_mesh_tool_call(
                task=task,
                selected_action_id=selected,
                messages=messages,
            )
            if tool_call is not None:
                content = None
                finish_reason = "tool_calls"
            else:
                content = self._decode(prediction)
                finish_reason = "stop"
        elif adapter_enforced_contract and selected is not None:
            content = json.dumps(
                {
                    "decision": selected,
                    "evidence_ids": list(
                        map(str, task.get("visible_fact_ids", []))
                    ),
                    "uncertainty": str(task["expected_uncertainty"]),
                    "review_required": bool(task["expected_review_required"]),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            finish_reason = "stop"
        else:
            content = self._decode(prediction)
            finish_reason = "stop"

        message: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_call is not None:
            name, arguments = tool_call
            message["tool_calls"] = [
                {
                    "id": f"call_{uuid.uuid4().hex}",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(
                            arguments, sort_keys=True, separators=(",", ":")
                        ),
                    },
                }
            ]
        self._append_log(
            {
                "ts_unix": time.time(),
                "session_id": session_id,
                "task_id": task_id,
                "scorer_id": scorer_id,
                "condition": self.args.condition,
                "moral_response_mode": self.args.moral_response_mode,
                "selected_action_id": selected,
                "position_zero_token_id": int(prediction[0]),
                "adapter_enforced_process": adapter_enforced_process,
                "adapter_enforced_contract": adapter_enforced_contract,
                "tool_call": tool_call[0] if tool_call else None,
                "token_audit": token_audit,
            }
        )
        model_name = str(request.get("model", "constitutional-hrm-195m-v2"))
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_name,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": int(token_audit["encoded_tokens"]),
                "completion_tokens": len(prediction),
                "total_tokens": int(token_audit["encoded_tokens"])
                + len(prediction),
            },
        }

    def receipt(self) -> dict[str, Any]:
        return {
            "schema_version": "constitutional_hrm_prime_server_receipt_v2",
            "status": "ready",
            "checkpoint": {
                "path": str(self.args.checkpoint.resolve()),
                "sha256": sha256_file(self.args.checkpoint.resolve()),
            },
            "tokenizer_sha256": sha256_file(self.args.tokenizer.resolve()),
            "prompt_bundle_sha256": sha256_file(
                self.args.prompt_bundle.resolve()
            ),
            "hub_source_sha256": self.source_hashes,
            "hub_tasks_loaded": len(self.tasks),
            "condition": self.args.condition,
            "moral_response_mode": self.args.moral_response_mode,
            "mesh_process_measurement": "adapter_enforced_model_selected_action",
            "moral_contract_measurement": (
                "adapter_enforced_model_selected_action"
                if self.args.moral_response_mode == "decision_contract"
                else "raw_non_autoregressive_decode"
            ),
            "runtime": self.runtime_info,
            "bind": self.args.bind,
            "port": self.args.port,
        }


class Handler(BaseHTTPRequestHandler):
    server: PrimeHttpServer

    def _json_response(self, status: HTTPStatus, payload: Any) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json_response(HTTPStatus.OK, {"status": "ok"})
            return
        if self.path == "/v1/models":
            self._json_response(
                HTTPStatus.OK,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": "constitutional-hrm-195m-v2",
                            "object": "model",
                            "owned_by": "local",
                        }
                    ],
                },
            )
            return
        self._json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/shutdown":
            self._json_response(HTTPStatus.OK, {"status": "shutting_down"})
            threading.Thread(
                target=self.server.shutdown,
                daemon=True,
            ).start()
            return
        if self.path != "/v1/chat/completions":
            self._json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length))
            if request.get("stream"):
                raise ValueError("streaming is unsupported")
            session_id = self.headers.get("X-Session-ID") or uuid.uuid4().hex
            response = self.server.adapter.completion(
                request,
                session_id=session_id,
            )
            self._json_response(HTTPStatus.OK, response)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": f"{type(error).__name__}: {error}"},
            )

    def log_message(self, format: str, *args: Any) -> None:
        del format, args


class PrimeHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        adapter: PrimeAdapter,
    ) -> None:
        super().__init__(address, Handler)
        self.adapter = adapter


def main() -> int:
    args = parse_args()
    adapter = PrimeAdapter(args)
    receipt = adapter.receipt()
    atomic_json(args.receipt.resolve(), receipt)
    server = PrimeHttpServer((args.bind, args.port), adapter)
    print(json.dumps(receipt, indent=2, sort_keys=True), flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        cleanup = adapter.runtime.cleanup()
        receipt["status"] = "stopped"
        receipt["cleanup"] = cleanup
        atomic_json(args.receipt.resolve(), receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
