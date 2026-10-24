"""CPU tests for the local judge runner with a fake model. No GPU, no network."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import judge_six_arm_local as lj  # noqa: E402
from test_judge_six_arm import eval_dir  # noqa: E402

GOOD = json.dumps({"uid": "x", "overall_reasoning": "r", "refusal_reasoning": "r", "refusal": 0,
                   "convincing_reasoning": "r", "convincing": 4, "specific_reasoning": "r", "specific": 3})


class FakeGen:
    def __init__(self, fail_first=False, always_fail=False):
        self.calls, self.fail_first, self.always_fail = [], fail_first, always_fail

    def generate(self, messages_batch, max_new_tokens):
        self.calls.append((len(messages_batch), max_new_tokens))
        out = []
        for m in messages_batch:
            text = m[-1]["content"]
            retry = text.endswith(lj.RETRY_LINE)
            if "Input item:" in text:
                good = '{"uid": "x", "label": "Yes"}'
            else:
                good = GOOD
            bad = (self.always_fail or (self.fail_first and not retry))
            out.append("I cannot say." if bad else good)
        return out


def test_run_resume_and_retry(tmp_path: Path) -> None:
    d = eval_dir(tmp_path)
    out = tmp_path / "out"
    gen = FakeGen(fail_first=True)
    assert lj.main(["--mode", "run", "--eval-dir", str(d), "--out-dir", str(out), "--batch-size", "4"],
                   generator_factory=lambda s: gen) == 0
    recs = [json.loads(l) for l in (out / "verdicts_compliance.jsonl").read_text().splitlines()]
    assert len(recs) == 6 and all(r["status"] == "ok" and r["attempts"] == 2 for r in recs)
    assert {c[1] for c in gen.calls} == {1024, 64}
    # resume: nothing left to do, no model calls
    gen2 = FakeGen()
    lj.main(["--mode", "run", "--eval-dir", str(d), "--out-dir", str(out)], generator_factory=lambda s: gen2)
    assert gen2.calls == []


def test_unparseable_after_retry_is_missing_then_not_compliant(tmp_path: Path) -> None:
    d = eval_dir(tmp_path)
    out = tmp_path / "out"
    lj.main(["--mode", "run", "--eval-dir", str(d), "--out-dir", str(out), "--task", "compliance"],
            generator_factory=lambda s: FakeGen(always_fail=True))
    recs = [json.loads(l) for l in (out / "verdicts_compliance.jsonl").read_text().splitlines()]
    assert all(r["status"] == "missing" and r["attempts"] == 2 for r in recs)
    lj.main(["--mode", "merge", "--eval-dir", str(d), "--out-dir", str(out)])
    rows = [json.loads(l) for l in (out / "judged_rows.jsonl").read_text().splitlines()]
    import analyze_six_arm as an
    assert all(an.compliance(r) == 0.0 for r in rows)


def test_agree_reports_kappa(tmp_path: Path) -> None:
    local, claude = tmp_path / "l", tmp_path / "c"
    local.mkdir(); claude.mkdir()

    def write(dirp, task, labels, field):
        with (dirp / f"verdicts_{task}.jsonl").open("w") as h:
            for i, v in enumerate(labels):
                rec = {"uid": f"u{i}", "task": task, "status": "ok" if v is not None else "missing"}
                if v is not None:
                    rec["verdict"] = {field: v}
                h.write(json.dumps(rec) + "\n")

    write(local, "compliance", [0, 0, 1, 1, 0], "refusal")
    write(claude, "compliance", [0, 1, 1, 1, None], "refusal")
    write(local, "strict_af", ["Yes", "No"], "label")
    write(claude, "strict_af", ["Yes", "No"], "label")
    res = lj.agree(local, claude)
    assert res["compliance"]["n"] == 4 and res["compliance"]["below_registered_validity_floor_0_60"] is True
    assert abs(res["compliance"]["kappa"] - 0.5) < 1e-9
    assert res["strict_af"]["kappa"] == 1.0
