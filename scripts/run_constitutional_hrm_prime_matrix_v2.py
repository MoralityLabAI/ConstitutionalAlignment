#!/usr/bin/env python3
"""Run the pinned Prime Hub evaluation matrix against a local HRM server."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIGS = (
    "constitutional_hrm_prime_moral_reasoner_v2.toml",
    "constitutional_hrm_prime_mesh_v2_development_jinn.toml",
    "constitutional_hrm_prime_mesh_v2_development_beast.toml",
    "constitutional_hrm_prime_mesh_v2_confirmatory_jinn.toml",
    "constitutional_hrm_prime_mesh_v2_confirmatory_beast.toml",
    "constitutional_hrm_prime_quranic_village_v2.toml",
)
CONDITIONS = (
    "constitution_metta_full",
    "constitution_hash_only",
    "constitution_removed",
)
CONDITION_SLUGS = {
    "constitution_metta_full": "full",
    "constitution_hash_only": "hash",
    "constitution_removed": "removed",
}


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
    parser.add_argument("--output-dir", required=True, type=Path)
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
        "--conditions",
        nargs="+",
        choices=CONDITIONS,
        default=list(CONDITIONS),
    )
    parser.add_argument(
        "--configs",
        nargs="+",
        choices=CONFIGS,
        default=list(CONFIGS),
    )
    parser.add_argument("--max-examples-per-eval", type=int)
    parser.add_argument("--include-contract-adapter", action="store_true")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--gpu-memory-fraction", type=float, default=0.80)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--server-python", default=sys.executable)
    parser.add_argument("--prime-command", default="prime")
    return parser.parse_args()


def wait_for_health(port: int, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 180
    url = f"http://127.0.0.1:{port}/health"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"HRM server exited with code {process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.5)
    raise TimeoutError("HRM server did not become healthy within 180 seconds")


def stop_server(port: int, process: subprocess.Popen[str]) -> None:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/shutdown",
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(request, timeout=5).read()
    except OSError:
        pass
    try:
        process.wait(timeout=60)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=30)


def materialize_config(
    *,
    source: Path,
    destination: Path,
    output_dir: Path,
    port: int,
    max_examples: int | None = None,
) -> None:
    text = source.read_text(encoding="utf-8")
    text = text.replace(
        'api_base_url = "http://127.0.0.1:8000/v1"',
        f'api_base_url = "http://127.0.0.1:{port}/v1"',
    )
    marker = "\n[[eval]]"
    if marker not in text:
        raise ValueError(f"Prime config has no eval table: {source}")
    escaped_output = str(output_dir.resolve()).replace("\\", "/")
    if max_examples is not None:
        if max_examples < 1:
            raise ValueError("max-examples-per-eval must be positive")
        lines = text.splitlines()
        replaced = False
        for index, line in enumerate(lines):
            if line.startswith("num_examples = "):
                lines[index] = f"num_examples = {max_examples}"
                replaced = True
                break
        if not replaced:
            raise ValueError(f"Prime config has no num_examples field: {source}")
        text = "\n".join(lines) + "\n"
    text = text.replace(
        marker,
        f'\noutput_dir = "{escaped_output}"\n{marker}',
        1,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def run_phase(
    *,
    args: argparse.Namespace,
    condition: str,
    response_mode: str,
    configs: tuple[str, ...],
    receipt: dict[str, Any],
) -> None:
    mode_slug = "raw" if response_mode == "raw_decode" else "contract"
    phase_root = (
        args.output_dir.resolve() / CONDITION_SLUGS[condition] / mode_slug
    )
    if phase_root.exists():
        raise FileExistsError(f"refusing to overwrite Prime phase: {phase_root}")
    phase_root.mkdir(parents=True)
    server_stdout = (phase_root / "server_stdout.log").open("w", encoding="utf-8")
    server_stderr = (phase_root / "server_stderr.log").open("w", encoding="utf-8")
    server_command = [
        args.server_python,
        str(REPO_ROOT / "scripts" / "serve_constitutional_hrm_prime_v2.py"),
        "--checkpoint",
        str(args.checkpoint.resolve()),
        "--official-root",
        str(args.official_root.resolve()),
        "--tokenizer",
        str(args.tokenizer.resolve()),
        "--prompt-bundle",
        str(args.prompt_bundle.resolve()),
        "--hub-data-dir",
        str(args.hub_data_dir.resolve()),
        "--condition",
        condition,
        "--moral-response-mode",
        response_mode,
        "--device",
        args.device,
        "--gpu-memory-fraction",
        str(args.gpu_memory_fraction),
        "--port",
        str(args.port),
        "--receipt",
        str(phase_root / "server_receipt.json"),
        "--request-log",
        str(phase_root / "server_requests.jsonl"),
    ]
    server = subprocess.Popen(
        server_command,
        cwd=REPO_ROOT,
        stdout=server_stdout,
        stderr=server_stderr,
        text=True,
    )
    phase_record: dict[str, Any] = {
        "condition": condition,
        "response_mode": response_mode,
        "path": str(phase_root),
        "status": "running",
        "server_command": server_command,
        "evals": {},
    }
    receipt["phases"][f"{condition}:{response_mode}"] = phase_record
    atomic_json(args.output_dir.resolve() / "matrix_receipt.json", receipt)
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment.setdefault("VLLM_API_KEY", "local")
    try:
        wait_for_health(args.port, server)
        for eval_index, filename in enumerate(configs):
            config_id = Path(filename).stem
            eval_slug = f"e{eval_index:02d}"
            eval_root = phase_root / "e" / eval_slug
            generated = phase_root / "c" / f"{eval_slug}.toml"
            materialize_config(
                source=REPO_ROOT / "configs" / "eval" / filename,
                destination=generated,
                output_dir=eval_root,
                port=args.port,
                max_examples=args.max_examples_per_eval,
            )
            command = [
                args.prime_command,
                "eval",
                "run",
                str(generated),
                "--skip-upload",
            ]
            completed = subprocess.run(
                command,
                check=False,
                cwd=REPO_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=3600,
            )
            (phase_root / f"{eval_slug}.out.log").write_text(
                completed.stdout,
                encoding="utf-8",
            )
            (phase_root / f"{eval_slug}.err.log").write_text(
                completed.stderr,
                encoding="utf-8",
            )
            metadata_files = list(eval_root.rglob("metadata.json"))
            if completed.returncode != 0:
                raise RuntimeError(
                    f"Prime eval {config_id} exited {completed.returncode}"
                )
            if len(metadata_files) != 1:
                raise RuntimeError(
                    f"Prime eval {config_id} emitted {len(metadata_files)} metadata files"
                )
            metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
            if metadata.get("version_info", {}).get("env_version") != "0.1.15":
                raise ValueError(f"Prime env version drift in {config_id}")
            if float(metadata.get("avg_error", 1.0)) != 0.0:
                raise RuntimeError(f"Prime eval {config_id} contains rollout errors")
            phase_record["evals"][config_id] = {
                "status": "completed",
                "metadata_path": str(metadata_files[0]),
                "avg_reward": metadata.get("avg_reward"),
                "avg_error": metadata.get("avg_error"),
                "num_examples": metadata.get("num_examples"),
                "env_version": metadata["version_info"]["env_version"],
            }
            atomic_json(args.output_dir.resolve() / "matrix_receipt.json", receipt)
        phase_record["status"] = "completed"
    except Exception as error:
        phase_record["status"] = "failed"
        phase_record["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        stop_server(args.port, server)
        server_stdout.close()
        server_stderr.close()
        atomic_json(args.output_dir.resolve() / "matrix_receipt.json", receipt)


def main() -> int:
    args = parse_args()
    output = args.output_dir.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output directory: {output}")
    output.mkdir(parents=True)
    receipt: dict[str, Any] = {
        "schema_version": "constitutional_hrm_prime_matrix_receipt_v2",
        "status": "running",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "checkpoint": str(args.checkpoint.resolve()),
        "conditions": args.conditions,
        "include_contract_adapter": args.include_contract_adapter,
        "phases": {},
    }
    atomic_json(output / "matrix_receipt.json", receipt)
    try:
        for condition in args.conditions:
            run_phase(
                args=args,
                condition=condition,
                response_mode="raw_decode",
                configs=tuple(args.configs),
                receipt=receipt,
            )
            if (
                args.include_contract_adapter
                and CONFIGS[0] in args.configs
            ):
                run_phase(
                    args=args,
                    condition=condition,
                    response_mode="decision_contract",
                    configs=(CONFIGS[0],),
                    receipt=receipt,
                )
        receipt["status"] = "completed"
        return_code = 0
    except Exception as error:  # noqa: BLE001
        receipt["status"] = "failed"
        receipt["error"] = f"{type(error).__name__}: {error}"
        return_code = 1
    receipt["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    atomic_json(output / "matrix_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
