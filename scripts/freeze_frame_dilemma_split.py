#!/usr/bin/env python3
"""Rebuild the recovered dilemma pool and freeze its cluster-disjoint split."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "experiments" / "frame_internalization_sft_v1"
EVAL_UNIVERSES = PACKAGE / "rerun_freeze" / "evaluation_universes_v1"
STORYWORLD = REPO_ROOT / "data" / "storyworld_sources" / "constitutional_alignment_20260715_v1"
DEFAULT_OUTPUT = PACKAGE / "rerun_freeze" / "curriculum_source_v1"
DEFAULT_RECEIPT = PACKAGE / "readiness" / "split_freeze_v1.json"

SEED = 42
TARGET_POOL = 5600
SOURCE_REVISION = "967df9976da45ee092189c769753b6c330bd3e9f"
SOURCE_SHA256 = "2c46727a6e403beeeb0dc435fc2dc5e65e231131abd57740c999da0f6aa47e6f"
BANNED = re.compile(
    r"free.tier|paid.tier|rlhf|anthropic|training data|reinforcement learning"
    r"|language model|helpful.only|scratchpad",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--moral-stories-parquet", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def ngrams(text: str, n: int = 8) -> set[str]:
    tokens = norm_text(text).split()
    return {" ".join(tokens[index:index + n]) for index in range(len(tokens) - n + 1)}


def relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def load_eval_ngrams() -> tuple[set[str], list[dict[str, Any]]]:
    grams: set[str] = set()
    sources: list[dict[str, Any]] = []
    for path in [
        EVAL_UNIVERSES / "harmful_queries.jsonl",
        EVAL_UNIVERSES / "benign_queries.jsonl",
        STORYWORLD / "evaluation" / "mihna_ca_eval_v2.encounter_prompts.jsonl",
    ]:
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            grams |= ngrams(row.get("text") or row["prompt_text"])
        sources.append({"path": relative(path), "sha256": sha256_file(path)})
    return grams, sources


def from_moral_stories(parquet_path: Path) -> list[dict[str, Any]]:
    dataset = pd.read_parquet(parquet_path, columns=["situation", "intention", "norm"])
    seen_situations: set[str] = set()
    output: list[dict[str, Any]] = []
    for row in dataset.itertuples(index=False):
        situation, intention, norm = row.situation, row.intention, row.norm
        if not isinstance(situation, str) or not isinstance(intention, str) or not isinstance(norm, str):
            continue
        if not situation or not intention or not norm:
            continue
        key = norm_text(situation)
        if key in seen_situations:
            continue
        seen_situations.add(key)
        prompt = (
            f"{situation} {intention} At the same time, there is a norm at stake: "
            f"{norm[0].lower()}{norm[1:]} "
            "Work through how the person should think about what to do here, "
            "including what makes this genuinely hard."
        )
        output.append({
            "source": "moral_stories",
            "cluster_key": "ms::" + norm_text(norm),
            "prompt_text": prompt,
        })
    return output


def from_storyworld_dev() -> list[dict[str, Any]]:
    path = STORYWORLD / "development" / "trust_ledger_ca_dev_v1.encounter_prompts.jsonl"
    output: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        text = row["prompt_text"]
        body = text.split("Scene:", 1)[1] if "Scene:" in text else text
        for stop in ("Options", "Choose one", "Respond with"):
            body = body.split(stop)[0]
        body = body.strip()
        prompt = (
            body
            + "\n\nReason through what the right course of action is here and what principles are in tension."
        )
        output.append({
            "source": "storyworld_dev",
            "cluster_key": "sw::" + row["encounter_id"],
            "prompt_text": prompt,
        })
    return output


def build_pool(parquet_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if sha256_file(parquet_path) != SOURCE_SHA256:
        raise ValueError("moral_stories parquet does not match the frozen source SHA-256")
    random.seed(SEED)
    rows = from_moral_stories(parquet_path) + from_storyworld_dev()

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        digest = hashlib.sha1(norm_text(row["prompt_text"]).encode("utf-8")).hexdigest()
        if digest not in seen:
            seen.add(digest)
            deduped.append(row)

    eval_grams, eval_sources = load_eval_ngrams()
    kept: list[dict[str, Any]] = []
    banned_count = 0
    overlap_count = 0
    for row in deduped:
        if BANNED.search(row["prompt_text"]):
            banned_count += 1
        elif ngrams(row["prompt_text"]) & eval_grams:
            overlap_count += 1
        else:
            kept.append(row)

    random.shuffle(kept)
    by_cluster: dict[str, list[dict[str, Any]]] = {}
    for row in kept:
        by_cluster.setdefault(row["cluster_key"], []).append(row)
    clusters = list(by_cluster.items())
    random.shuffle(clusters)
    pool: list[dict[str, Any]] = []
    total = 0
    for _, members in clusters:
        if total >= TARGET_POOL:
            break
        selected = members[:3]
        pool.extend(selected)
        total += len(selected)

    cluster_keys = sorted({row["cluster_key"] for row in pool})
    random.shuffle(cluster_keys)
    validation_clusters = set(cluster_keys[:max(1, int(len(cluster_keys) * 0.05))])
    for index, row in enumerate(sorted(pool, key=lambda item: item["cluster_key"])):
        row["scenario_id"] = f"d{index:05d}"
        row["cluster_id"] = hashlib.sha1(row["cluster_key"].encode("utf-8")).hexdigest()[:10]
        row["split"] = "val" if row["cluster_key"] in validation_clusters else "train"
    pool.sort(key=lambda row: row["scenario_id"])

    train_clusters = {row["cluster_id"] for row in pool if row["split"] == "train"}
    validation_cluster_ids = {row["cluster_id"] for row in pool if row["split"] == "val"}
    cluster_overlap = train_clusters & validation_cluster_ids
    manifest = {
        "schema_version": "frame_internalization_dilemma_pool.v1",
        "classification": "prospective_reconstruction_from_session_recovered_builder",
        "exact_historical_row_recovery": False,
        "seed": SEED,
        "total": len(pool),
        "train": sum(row["split"] == "train" for row in pool),
        "validation": sum(row["split"] == "val" for row in pool),
        "clusters": len({row["cluster_id"] for row in pool}),
        "by_source": {
            source: sum(row["source"] == source for row in pool)
            for source in sorted({row["source"] for row in pool})
        },
        "dropped_banned_vocab": banned_count,
        "dropped_eval_overlap": overlap_count,
        "cluster_overlap_count": len(cluster_overlap),
        "split_unit": "norm/storyworld cluster; cluster-disjoint train/validation",
        "source": {
            "repository": "demelin/moral_stories",
            "main_revision": "b830cf56eb00bc4edd1860dd544a192216eb3587",
            "parquet_conversion_revision": SOURCE_REVISION,
            "path": "full/train/0000.parquet",
            "sha256": SOURCE_SHA256,
            "license": "MIT",
        },
        "evaluation_sources": eval_sources,
    }
    return pool, manifest


def freeze(parquet_path: Path, output_dir: Path, receipt_path: Path) -> dict[str, Any]:
    pool, manifest = build_pool(parquet_path)
    expected = {
        "total": 5600,
        "train": 5320,
        "validation": 280,
        "clusters": 5600,
    }
    for key, value in expected.items():
        if manifest[key] != value:
            raise ValueError(f"recovered pool invariant mismatch for {key}: {manifest[key]!r} != {value!r}")
    if manifest["cluster_overlap_count"] != 0:
        raise ValueError("cluster overlap detected")
    manifest["recovered_run_comparison"] = {
        "reported_by_source": {"moral_stories": 5587, "storyworld_dev": 13},
        "prospective_by_source": manifest["by_source"],
        "matches_reported_by_source": manifest["by_source"]
        == {"moral_stories": 5587, "storyworld_dev": 13},
        "interpretation": (
            "The critical count and split invariants match, but the lost run did not pin its "
            "parquet conversion revision; the prospective pin is therefore a new immutable split."
        ),
    }

    dilemmas_path = output_dir / "dilemmas.jsonl"
    assignments_path = output_dir / "split_assignments.jsonl"
    manifest_path = output_dir / "dilemma_manifest.json"
    public_rows = [
        {key: row[key] for key in ("scenario_id", "cluster_id", "source", "split", "prompt_text")}
        for row in pool
    ]
    assignments = [
        {key: row[key] for key in ("scenario_id", "cluster_id", "source", "split")}
        for row in pool
    ]
    write_jsonl(dilemmas_path, public_rows)
    write_jsonl(assignments_path, assignments)
    manifest.update({
        "dilemmas_path": relative(dilemmas_path),
        "dilemmas_sha256": sha256_file(dilemmas_path),
        "assignments_path": relative(assignments_path),
        "assignments_sha256": sha256_file(assignments_path),
        "builder_path": relative(Path(__file__)),
        "builder_sha256": sha256_file(Path(__file__)),
    })
    write_json(manifest_path, manifest)

    receipt = {
        "schema_version": "frame_internalization_split_freeze.v1",
        "status": "passed",
        "passed": True,
        "frozen_at": "2026-07-17",
        "classification": "prospective_reconstruction_not_exact_historical_recovery",
        "cluster_overlap_count": 0,
        "scenario_count": manifest["total"],
        "train_count": manifest["train"],
        "validation_count": manifest["validation"],
        "cluster_count": manifest["clusters"],
        "manifest_path": relative(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "assignments_path": relative(assignments_path),
        "assignments_sha256": sha256_file(assignments_path),
        "dilemmas_path": relative(dilemmas_path),
        "dilemmas_sha256": sha256_file(dilemmas_path),
        "immutability_rule": "Any row, cluster, or split change requires a new version and invalidates downstream curriculum receipts.",
    }
    write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    args = parse_args()
    receipt = freeze(
        args.moral_stories_parquet.resolve(),
        args.output_dir.resolve(),
        args.receipt.resolve(),
    )
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
