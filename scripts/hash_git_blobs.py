#!/usr/bin/env python3
"""Hash canonical Git blobs at an exact source revision."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent


def resolve_commit(revision: str, repo_root: Path = REPO_ROOT) -> str:
    commit = subprocess.check_output(
        ["git", "rev-parse", "--verify", f"{revision}^{{commit}}"],
        cwd=repo_root,
        text=True,
    ).strip()
    if len(commit) != 40:
        raise RuntimeError(f"expected a full Git commit ID, received: {commit}")
    return commit


def repo_relative_path(path: Path, repo_root: Path = REPO_ROOT) -> str:
    resolved_root = repo_root.resolve()
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise ValueError(f"path is outside the repository: {path}") from exc


def git_blob_bytes(
    path: Path,
    revision: str,
    repo_root: Path = REPO_ROOT,
) -> bytes:
    relative = repo_relative_path(path, repo_root)
    commit = resolve_commit(revision, repo_root)
    return subprocess.check_output(
        ["git", "cat-file", "blob", f"{commit}:{relative}"],
        cwd=repo_root,
    )


def git_blob_sha256(
    path: Path,
    revision: str,
    repo_root: Path = REPO_ROOT,
) -> str:
    return hashlib.sha256(git_blob_bytes(path, revision, repo_root)).hexdigest()


def build_receipt(
    paths: list[Path],
    revision: str,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    commit = resolve_commit(revision, repo_root)
    bindings = [
        {
            "path": repo_relative_path(path, repo_root),
            "sha256": git_blob_sha256(path, commit, repo_root),
        }
        for path in paths
    ]
    return {
        "schema_version": "canonical_git_blob_bindings.v1",
        "source_commit": commit,
        "hash_algorithm": "sha256",
        "byte_source": "git_cat_file_blob",
        "bindings": bindings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("paths", nargs="+", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = build_receipt(args.paths, args.revision)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
