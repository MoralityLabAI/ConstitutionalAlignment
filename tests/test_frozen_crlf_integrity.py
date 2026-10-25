"""Guard historically frozen artifact hashes against Git newline conversion."""
from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTROL = {
    "experiments/frame_internalization_sft_v1/rerun_freeze/model_tokenizer_remote_inventory_v1.json": "852f19dfb0d4dd36effb42b1c5440e0f34dad3fdf2b62020754f9df34524962d",
    "experiments/frame_internalization_sft_v1/rerun_freeze/judge_classifier_inputs_v1.json": "148de221f10221b97fd8ec69d26ba4f79d0a600ebdded95ed85f5ce2f5597fdc",
    "experiments/frame_internalization_sft_v1/rerun_freeze/predecessor_reanchor_progress_v1.json": "b3b7148cb443c3ea2b13608501a16370685274a371bf0178ef36b44b077f2036",
    "experiments/jinn_beast_metta_rl_v1/hosted_thinking_baseline_traces_20260723.jsonl": "4e9aae8df664bb23293faa506d317a59a155339925bb9fc6387b6af912a38e94",
}
REGISTRIES = (
    "jinn_bench/data/construct_benchmarks_v1.json",
    "jinn_bench/data/jinn_moral_reasoner_registry_v2.json",
)


class FrozenBytesTests(unittest.TestCase):
    def check_exact(self, name: str, expected: str) -> None:
        data = (ROOT / name).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), expected, name)

    def test_frozen_control_files(self) -> None:
        for name, expected in CONTROL.items():
            with self.subTest(file=name):
                self.check_exact(name, expected)

    def test_registered_benchmark_artifacts(self) -> None:
        construct = json.loads((ROOT / REGISTRIES[0]).read_text(encoding="utf-8"))
        for key in ("task", "candidate_sft", "candidate_preferences", "source_anchors"):
            self.check_exact(construct["data"][key + "_path"], construct["data"][key + "_sha256"])
        for item in construct["constructs"].values():
            for kind in ("constitution", "policy"):
                self.check_exact(item[kind + "_path"], item[kind + "_sha256"])
            for world in item["storyworlds"]:
                self.check_exact(world["path"], world["sha256"])
        reasoner = json.loads((ROOT / REGISTRIES[1]).read_text(encoding="utf-8"))
        for key in ("task", "environment_task"):
            self.check_exact(reasoner["data"][key + "_path"], reasoner["data"][key + "_sha256"])
        for world in reasoner["data"]["storyworlds"]:
            self.check_exact(world["path"], world["sha256"])

    def test_selected_files_preserve_original_crlf_and_git_attributes(self) -> None:
        for name in (
            "jinn_bench/data/construct_tasks_v1.jsonl",
            "jinn_bench/data/jinn_moral_reasoner_tasks_v2.jsonl",
            *CONTROL,
        ):
            with self.subTest(file=name):
                data = (ROOT / name).read_bytes()
                self.assertIn(b"\r\n", data)
                self.assertNotIn(b"\n", data.replace(b"\r\n", b""))
                result = subprocess.run(
                    ["git", "check-attr", "text", "eol", "--", name],
                    cwd=ROOT, text=True, capture_output=True, check=True,
                )
                self.assertEqual(
                    result.stdout.splitlines(),
                    [f"{name}: text: unset", f"{name}: eol: unset"],
                )


if __name__ == "__main__":
    unittest.main()
