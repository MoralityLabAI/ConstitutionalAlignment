"""Regression checks for historic CRLF-frozen files under LF Git checkout."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.frozen_line_endings import matches_frozen_sha256

ROOT = Path(__file__).resolve().parents[1]


class FrozenLineEndingTests(unittest.TestCase):
    def test_real_frozen_construct_matches_original_bytes(self):
        path = ROOT / "jinn_bench/data/construct_tasks_v1.jsonl"
        expected = "7c9a99771b44e91504c616c5be16279fbdf5eecce3b1ad7d721cdc400ca3845a"
        self.assertTrue(matches_frozen_sha256(path, expected))
        self.assertNotEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

    def test_reconstruction_and_tampering(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "jinn_bench/data") as temp:
            path = Path(temp) / "sample.jsonl"
            raw = b'{"id":1}\n{"id":2}\n'
            original_sha = hashlib.sha256(raw.replace(b"\n", b"\r\n")).hexdigest()
            path.write_bytes(raw)
            self.assertTrue(matches_frozen_sha256(path, original_sha))
            path.write_bytes(raw.replace(b'"id":2', b'"id":3'))
            self.assertFalse(matches_frozen_sha256(path, original_sha))

    def test_outside_legacy_scope_and_malformed_digest_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.jsonl"
            raw = b"one\ntwo\n"
            path.write_bytes(raw)
            self.assertTrue(matches_frozen_sha256(path, hashlib.sha256(raw).hexdigest()))
            self.assertFalse(matches_frozen_sha256(path, hashlib.sha256(raw.replace(b"\n", b"\r\n")).hexdigest()))
            self.assertFalse(matches_frozen_sha256(path, "not-a-digest"))


if __name__ == "__main__":
    unittest.main()
