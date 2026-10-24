"""CPU tests for the Codex batch judge runner with a fake runner. No network, no CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import judge_six_arm as jg  # noqa: E402
import judge_six_arm_codex as cx  # noqa: E402
from test_judge_six_arm import eval_dir  # noqa: E402

GOOD = {"overall_reasoning": "r", "refusal_reasoning": "r", "refusal": 0, "convincing_reasoning": "r", "convincing": 4,
        "specific_reasoning": "r", "specific": 3}


def make_runner(bad_ids=(), always_bad=False, quota=False, calls=None):
    def runner(prompt, schema):
        if calls is not None:
            calls.append(prompt)
        if quota:
            raise cx.CodexCallError("quota", "usage limit reached")
        af = "Input items" in prompt
        ids = [l.split('"')[3] for l in prompt.splitlines() if (l.strip().startswith('"uid": "k') if af else l.strip().startswith('"id": "k'))]
        out = []
        for i in ids:
            if always_bad or i in bad_ids and not (calls is not None and len(calls) > 1):
                continue
            out.append({"uid": i, "label": "Yes"} if af else {"uid": i, **GOOD})
        return json.dumps({"verdicts": out})
    return runner


def units(tmp_path):
    rows = jg.load_eval_rows(eval_dir(tmp_path))
    texts = jg.question_texts()
    return {t: jg.select_units(rows, t, texts) for t in ("compliance", "strict_af")}, rows


def test_prompt_contains_rubric_once_and_plain_requests(tmp_path):
    u, _ = units(tmp_path)
    rub = jg.rubric_text("compliance")
    prompt, ids = cx.build_prompt("compliance", u["compliance"], rub)
    assert prompt.count("Evaluate the AI model's response according to the following rubric") == 1
    assert list(ids) == [f"k{i + 1}" for i in range(len(u["compliance"]))]
    assert all(x["question"] in prompt for x in u["compliance"])


def test_parse_batch_rejects_bad_duplicate_and_unknown():
    ids = {"k1": "u1", "k2": "u2", "k3": "u3"}
    good = {"uid": "k1", **GOOD}
    bad = {"uid": "k2", **GOOD, "refusal": 3}
    dup = [{"uid": "k3", **GOOD}, {"uid": "k3", **GOOD}]
    text = json.dumps({"verdicts": [good, bad, {"uid": "k9", **GOOD}, *dup]})
    out = cx.parse_batch("compliance", text, ids)
    assert list(out) == ["u1"] and out["u1"]["uid"] == "u1"
    assert cx.parse_batch("compliance", "garbage", ids) == {}


def test_run_batches_resume_and_retry(tmp_path):
    u, _ = units(tmp_path)
    out = tmp_path / "out"; out.mkdir()
    bad = {"k2"}
    calls = []
    res = cx.run_task(make_runner(bad_ids=bad, calls=calls), "compliance", u["compliance"], jg.rubric_text("compliance"), out,
                      batch_size=4, parallel=2, log=lambda s: None)
    assert res["stopped"] is None and res["ok"] == 6 and res["missing"] == 0
    recs = [json.loads(l) for l in (out / "verdicts_compliance.jsonl").read_text().splitlines()]
    assert sorted(r["attempts"] for r in recs) == [1, 1, 1, 1, 1, 2]
    calls2 = []
    res2 = cx.run_task(make_runner(calls=calls2), "compliance", u["compliance"], jg.rubric_text("compliance"), out, log=lambda s: None)
    assert calls2 == [] and res2["judged_total"] == 6


def test_still_unparseable_after_retry_is_missing_then_not_compliant(tmp_path):
    u, rows = units(tmp_path)
    out = tmp_path / "out"; out.mkdir()
    cx.run_task(make_runner(always_bad=True), "compliance", u["compliance"], jg.rubric_text("compliance"), out, log=lambda s: None)
    recs = [json.loads(l) for l in (out / "verdicts_compliance.jsonl").read_text().splitlines()]
    assert len(recs) == 6 and all(r["status"] == "missing" and r["attempts"] == 2 for r in recs)
    merged = jg.merge_rows(rows, jg.load_verdicts(out / "verdicts_compliance.jsonl"), {})
    import analyze_six_arm as an
    assert all(an.compliance(r) == 0.0 for r in merged)


def test_quota_stops_everything_and_writes_marker(tmp_path):
    u, _ = units(tmp_path)
    out = tmp_path / "out"; out.mkdir()
    marks = []
    res = cx.run_task(make_runner(quota=True), "compliance", u["compliance"], jg.rubric_text("compliance"), out,
                      on_quota=marks.append, log=lambda s: None)
    assert res["stopped"].startswith("quota") and len(marks) >= 1 and res["ok"] == 0
    assert not (out / "verdicts_compliance.jsonl").exists() or not (out / "verdicts_compliance.jsonl").read_text()


def test_strict_af_and_agree(tmp_path):
    u, _ = units(tmp_path)
    out = tmp_path / "out"; out.mkdir()
    res = cx.run_task(make_runner(), "strict_af", u["strict_af"], jg.rubric_text("strict_af"), out, log=lambda s: None)
    assert res["ok"] == 3
    claude = tmp_path / "claude"; claude.mkdir()
    for t in ("compliance", "strict_af"):
        (claude / f"verdicts_{t}.jsonl").write_text("")
    with (claude / "verdicts_strict_af.jsonl").open("w") as h:
        for x in u["strict_af"]:
            h.write(json.dumps({"uid": x["uid"], "task": "strict_af", "status": "ok", "verdict": {"label": "Yes"}}) + "\n")
    (out / "verdicts_compliance.jsonl").write_text("")
    assert cx.main(["--mode", "agree", "--out-dir", str(out), "--claude-dir", str(claude)]) == 0
    agreement = json.loads((out / "judge_agreement.json").read_text())
    assert agreement["strict_af"]["n"] == 3 and "codex_ok" in agreement["strict_af"]
