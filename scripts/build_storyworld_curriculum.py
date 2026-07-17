#!/usr/bin/env python3
"""Build canonical training views and optionally pack per-arm token quotas."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import read_json, read_world
from alignment_harness.storyworlds import sha256_file, sha256_json
from alignment_harness.trajectory_curriculum import (
    HuggingFaceTokenCounter,
    TiktokenCounter,
    VIEW_FILENAMES,
    build_canonical_release,
    pack_curriculum,
    read_jsonl,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traces", action="append", required=True)
    parser.add_argument(
        "--trace-manifest",
        action="append",
        default=[],
        help=(
            "Approved harvest release manifest corresponding positionally to each "
            "--traces file. Required for a nonprovisional release."
        ),
    )
    parser.add_argument("--world", action="append", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--allow-provisional", action="store_true")
    parser.add_argument("--recipe")
    parser.add_argument("--pack-output-dir")
    parser.add_argument("--extra-rows", action="append", default=[])
    parser.add_argument(
        "--extra-manifest",
        action="append",
        default=[],
        help="Approved release manifest corresponding positionally to each --extra-rows file.",
    )
    parser.add_argument("--tokenizer-backend", choices=("tiktoken", "huggingface"), default="tiktoken")
    parser.add_argument("--tiktoken-encoding", default="cl100k_base")
    parser.add_argument("--hf-tokenizer")
    parser.add_argument("--allow-shortfall", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.trace_manifest and len(args.trace_manifest) != len(args.traces):
        raise ValueError(
            "--trace-manifest must be omitted or supplied positionally for every --traces file"
        )
    if not args.allow_provisional and len(args.trace_manifest) != len(args.traces):
        raise ValueError("every production trace input requires an approved release manifest")
    traces = []
    trace_input_artifacts = []
    for index, source in enumerate(args.traces):
        trace_path = Path(source).resolve()
        source_traces = read_jsonl(trace_path)
        traces.extend(source_traces)
        if args.trace_manifest:
            source_manifest_path = Path(args.trace_manifest[index]).resolve()
            source_manifest = read_json(source_manifest_path)
            if source_manifest.get("schema_version") != (
                "storyworld_harvest_approved_release_manifest_v1"
            ) or source_manifest.get("status") != (
                "approved_real_teacher_traces_for_canonical_derivation"
            ):
                raise ValueError("unexpected or unapproved harvest release manifest")
            if (
                source_manifest.get("approved_traces_sha256")
                != sha256_file(trace_path)
                or int(source_manifest.get("traces", -1)) != len(source_traces)
                or int(source_manifest.get("training_approved_traces", -1))
                != len(source_traces)
                or source_manifest.get("trace_content_sha256")
                != [sha256_json(trace) for trace in source_traces]
                or source_manifest.get("passed") is not True
            ):
                raise ValueError("harvest release manifest does not bind every trace")
            trace_input_artifacts.append(
                {
                    "kind": "approved_harvest_traces",
                    "path": str(trace_path),
                    "rows": len(source_traces),
                    "sha256": sha256_file(trace_path),
                    "source_manifest_path": str(source_manifest_path),
                    "source_manifest_sha256": sha256_file(source_manifest_path),
                }
            )
    worlds = {}
    for source in args.world:
        world = read_world(Path(source).resolve())
        worlds[world["world_id"]] = world
    output_dir = Path(args.output_dir).resolve()
    manifest = build_canonical_release(
        traces,
        worlds,
        output_dir,
        allow_provisional=args.allow_provisional,
        trace_input_artifacts=trace_input_artifacts,
    )
    result = {"canonical_release": manifest}
    if args.recipe:
        if not args.pack_output_dir:
            raise ValueError("--pack-output-dir is required with --recipe")
        rows = []
        input_artifacts = []
        canonical_manifest_path = output_dir / "MANIFEST.json"
        canonical_manifest_sha256 = sha256_file(canonical_manifest_path)
        for view in ("sft_policy", "sft_world_model", "sft_interrogation", "sft_repair"):
            view_path = output_dir / VIEW_FILENAMES[view]
            view_rows = read_jsonl(view_path)
            rows.extend(view_rows)
            input_artifacts.append(
                {
                    "kind": "canonical_training_view",
                    "view": view,
                    "path": str(view_path),
                    "rows": len(view_rows),
                    "sha256": sha256_file(view_path),
                    "source_manifest_path": str(canonical_manifest_path),
                    "source_manifest_sha256": canonical_manifest_sha256,
                }
            )
        if len(args.extra_rows) != len(args.extra_manifest):
            if not args.allow_provisional or args.extra_rows:
                raise ValueError(
                    "every --extra-rows artifact requires a positional --extra-manifest"
                )
        for source, manifest_source in zip(args.extra_rows, args.extra_manifest):
            source_path = Path(source).resolve()
            source_rows = read_jsonl(source_path)
            source_sha256 = sha256_file(source_path)
            source_manifest_path = Path(manifest_source).resolve()
            source_manifest = read_json(source_manifest_path)
            if source_manifest.get("schema_version") not in {
                "storyworld_support_approved_release_manifest_v1",
                "storyworld_recovered_extras_approved_release_v1",
            }:
                raise ValueError(
                    f"unexpected extra-row release manifest schema: {source_manifest_path}"
                )
            if source_manifest.get("approved_rows_sha256") != source_sha256:
                raise ValueError(
                    f"extra-row release manifest does not bind its artifact hash: {source_path}"
                )
            if int(source_manifest.get("training_approved_rows", -1)) != len(source_rows):
                raise ValueError(f"extra-row release manifest does not approve every row: {source_path}")
            if not source_manifest.get("passed"):
                raise ValueError(f"extra-row release manifest did not pass: {source_path}")
            rows.extend(source_rows)
            input_artifacts.append(
                {
                    "kind": "approved_extra_rows",
                    "path": str(source_path),
                    "rows": len(source_rows),
                    "sha256": source_sha256,
                    "source_manifest_path": str(source_manifest_path),
                    "source_manifest_sha256": sha256_file(source_manifest_path),
                }
            )
        if args.tokenizer_backend == "huggingface":
            if not args.hf_tokenizer:
                raise ValueError("--hf-tokenizer is required for the Hugging Face backend")
            counter = HuggingFaceTokenCounter(args.hf_tokenizer)
        else:
            counter = TiktokenCounter(args.tiktoken_encoding)
        result["packed_curriculum"] = pack_curriculum(
            rows,
            read_json(Path(args.recipe).resolve()),
            Path(args.pack_output_dir).resolve(),
            counter,
            allow_shortfall=args.allow_shortfall,
            allow_provisional=args.allow_provisional,
            input_artifacts=input_artifacts,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
