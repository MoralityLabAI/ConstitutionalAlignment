from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_experiment_archive_manifest import build_manifest


class ExperimentArchiveManifestTests(unittest.TestCase):
    def test_hashes_nested_files_and_excludes_receipt_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "nested").mkdir()
            (root / "a.txt").write_text("alpha", encoding="utf-8")
            (root / "nested" / "b.txt").write_text("beta", encoding="utf-8")
            (root / "manifest.json").write_text("excluded", encoding="utf-8")
            (root / "run_receipt.json").write_text("excluded", encoding="utf-8")

            manifest = build_manifest(root, "run-1")

        self.assertEqual(manifest["file_count"], 2)
        self.assertEqual(manifest["total_bytes"], 9)
        self.assertEqual(
            [item["path"] for item in manifest["files"]],
            ["a.txt", "nested/b.txt"],
        )
        self.assertTrue(all(len(item["sha256"]) == 64 for item in manifest["files"]))


if __name__ == "__main__":
    unittest.main()
