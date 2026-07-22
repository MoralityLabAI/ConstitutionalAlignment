#!/usr/bin/env python3
"""Build a non-destructive, checksummed Jinn experiment-data collation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence


DEFAULT_REPO_METADATA_PATHS = (
    Path("experiments/qwen_soft_tests_v1"),
    Path(
        "experiments/frame_internalization_sft_v1/readiness/"
        "qwen3_1p7b_local_model_tokenizer_freeze_v2.json"
    ),
    Path(
        "experiments/frame_internalization_sft_v1/local_screen_v1/"
        "worldview_local_screen_result_v1.json"
    ),
    Path("experiments/local_storyworld_dag_v1/cycle_plan.json"),
    Path("experiments/local_storyworld_dag_v1/receipts/cycle_01b_20260722.json"),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def collect_source_files(source_root: Path, output_dir: Path) -> list[Path]:
    files = [
        path
        for path in source_root.rglob("*")
        if path.is_file() and not path.is_relative_to(output_dir)
    ]
    return sorted(files, key=lambda path: path.relative_to(source_root).as_posix())


def expand_repo_metadata(
    repo_root: Path,
    metadata_paths: Iterable[Path],
) -> list[tuple[str, Path]]:
    expanded: dict[str, Path] = {}
    for relative in metadata_paths:
        source = repo_root / relative
        if not source.exists():
            raise FileNotFoundError(f"Missing repository metadata: {source}")
        candidates = source.rglob("*") if source.is_dir() else (source,)
        for candidate in candidates:
            if candidate.is_file():
                key = candidate.relative_to(repo_root).as_posix()
                expanded[key] = candidate
    return sorted(expanded.items())


def build_catalog(source_root: Path, files: Sequence[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in files:
        stat = path.stat()
        rows.append(
            {
                "relative_path": path.relative_to(source_root).as_posix(),
                "bytes": stat.st_size,
                "modified_at_utc": datetime.fromtimestamp(
                    stat.st_mtime, tz=UTC
                ).isoformat(),
                "sha256": sha256_file(path),
            }
        )
    return rows


def copy_repo_metadata(
    output_dir: Path,
    repo_metadata: Sequence[tuple[str, Path]],
) -> None:
    target_root = output_dir / "repo_metadata"
    for relative, source in repo_metadata:
        target = target_root / Path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def write_archive(
    archive_path: Path,
    source_root: Path,
    source_files: Sequence[Path],
    repo_metadata: Sequence[tuple[str, Path]],
) -> int:
    temporary = archive_path.with_suffix(archive_path.suffix + ".tmp")
    with zipfile.ZipFile(
        temporary,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
        allowZip64=True,
    ) as archive:
        for source in source_files:
            relative = source.relative_to(source_root).as_posix()
            archive.write(source, arcname=f"data/{relative}")
        for relative, source in repo_metadata:
            archive.write(source, arcname=f"repo_metadata/{relative}")
    with zipfile.ZipFile(temporary, mode="r") as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise RuntimeError(f"Archive CRC verification failed at {bad_member}")
        member_count = len(archive.infolist())
    os.replace(temporary, archive_path)
    return member_count


def collate(
    source_root: Path,
    output_dir: Path,
    repo_root: Path,
    metadata_paths: Sequence[Path],
    archive_name: str,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    output_dir = output_dir.resolve()
    repo_root = repo_root.resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(f"Missing source root: {source_root}")
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing collation: {output_dir}")
    if not output_dir.is_relative_to(source_root):
        raise ValueError("The collation output must be inside the source root")

    source_files = collect_source_files(source_root, output_dir)
    if not source_files:
        raise ValueError("No experiment files found to collate")
    repo_metadata = expand_repo_metadata(repo_root, metadata_paths)
    output_dir.mkdir(parents=True)

    catalog_rows = build_catalog(source_root, source_files)
    catalog_path = output_dir / "source_catalog.jsonl"
    catalog_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in catalog_rows),
        encoding="utf-8",
    )
    copy_repo_metadata(output_dir, repo_metadata)

    archive_path = output_dir / archive_name
    member_count = write_archive(
        archive_path,
        source_root,
        source_files,
        repo_metadata,
    )
    summary = {
        "schema_version": "jinn_experiment_data_collation_v1",
        "status": "complete",
        "created_at_utc": datetime.now(tz=UTC).isoformat(),
        "source_root": str(source_root),
        "output_dir": str(output_dir),
        "non_destructive": True,
        "source_file_count": len(source_files),
        "source_total_bytes": sum(row["bytes"] for row in catalog_rows),
        "source_catalog": str(catalog_path),
        "source_catalog_sha256": sha256_file(catalog_path),
        "repo_metadata_file_count": len(repo_metadata),
        "archive": str(archive_path),
        "archive_member_count": member_count,
        "archive_sha256": sha256_file(archive_path),
        "archive_crc_check_passed": True,
        "claim_boundary": (
            "Artifact collation only. The archive preserves development outputs and "
            "does not change any scientific gate or authorize paid compute."
        ),
    }
    write_json(output_dir / "collation_summary.json", summary)
    (output_dir / "README.md").write_text(
        "# Jinn-or-Beast experiment-data collation\n\n"
        f"Source files: {summary['source_file_count']}\n\n"
        f"Source bytes: {summary['source_total_bytes']}\n\n"
        f"Archive: `{archive_path.name}`\n\n"
        f"Archive SHA-256: `{summary['archive_sha256']}`\n\n"
        "Original files remain in place. `source_catalog.jsonl` records the relative "
        "path, byte size, modification time, and SHA-256 of every source file. "
        "`repo_metadata/` contains the matching prospective contracts and closeout "
        "receipts from the repository.\n",
        encoding="utf-8",
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--repo-root", default=str(Path(__file__).resolve().parent.parent)
    )
    parser.add_argument(
        "--archive-name",
        default="jinn_or_beast_all_experiment_data_20260722.zip",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = collate(
        Path(args.source_root),
        Path(args.output_dir),
        Path(args.repo_root),
        DEFAULT_REPO_METADATA_PATHS,
        args.archive_name,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
