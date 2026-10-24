"""CPU tests for the Claude batch judge runner with a fake client. No network, no credentials."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import judge_six_arm as jg  # noqa: E402
import judge_six_arm_claude as cj  # noqa: E402
from test_judge_six_arm import eval_dir  # noqa: E402

GOOD = {"uid": "x", "overall_reasoning": "r", "refusal_reasoning": "r", "refusal": 0, "convincing_reasoning": "r",
        "convincing": 4, "specific_reasoning": "r", "specific": 3}


class FakeBatches:
    def __init__(self, fail_first_for=()):
        self.created, self.store, self.fail_first_for, self.seen = [], {}, set(fail_first_for), {}

    def create(self, requests):
        bid = f"b{len(self.created)}"
        self.created.append(requests)
        self.store[bid] = requests
        return SimpleNamespace(id=bid)

    def retrieve(self, bid):
        return SimpleNamespace(processing_status="ended")

    def results(self, bid):
        for req in self.store[bid]:
            p = req["params"]
            assert p["thinking"] == {"type": "adaptive"} and p["output_config"]["effort"] == "high"
            assert p["max_tokens"] == 2048 and not {"temperature", "top_p", "top_k"} & set(p)
            text = p["messages"][0]["content"]
            key = text[:200] + text[-200:]
            bad = key in self.fail_first_for and key not in self.seen
            self.seen[key] = True
            body = "no json" if bad else json.dumps({"uid": "x", "label": "No"} if "Input item:" in text else GOOD)
            yield {"custom_id": req["custom_id"], "result": {"type": "succeeded", "message": {
                "model": p["model"], "content": [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": body}],
                "usage": {"input_tokens": 1000, "output_tokens": 500}}}}


class FakeClient:
    def __init__(self, **kw):
        self.messages = SimpleNamespace(batches=FakeBatches(**kw))


def prime_dir(tmp_path: Path, d: Path) -> Path:
    """Prime verdicts: all AF units unjudged except one ok and one unparseable; compliance mixed."""
    rows = jg.load_eval_rows(d)
    texts = jg.question_texts()
    comp = jg.select_units(rows, "compliance", texts)
    af = jg.select_units(rows, "strict_af", texts)
    pd = tmp_path / "prime"
    pd.mkdir()
    with (pd / "verdicts_compliance.jsonl").open("w") as h:
        h.write(json.dumps({"uid": comp[0]["uid"], "task": "compliance", "status": "ok", "verdict": {"refusal": 1, "convincing": 1, "specific": 1}}) + "\n")
        h.write(json.dumps({"uid": comp[1]["uid"], "task": "compliance", "status": "missing"}) + "\n")
    with (pd / "verdicts_strict_af.jsonl").open("w") as h:
        h.write(json.dumps({"uid": af[0]["uid"], "task": "strict_af", "status": "ok", "verdict": {"label": "Yes"}}) + "\n")
    return pd


def test_dry_run_needs_no_key_and_estimates(tmp_path: Path) -> None:
    d = eval_dir(tmp_path)
    out = tmp_path / "out"

    def forbidden():
        raise AssertionError("dry-run must not create a client")

    assert cj.main(["--mode", "dry-run", "--eval-dir", str(d), "--prime-dir", str(prime_dir(tmp_path, d)), "--out-dir", str(out)],
                   client_factory=forbidden, env={}) == 0
    plan = json.loads((out / "cost_estimate_claude.json").read_text())
    assert plan["tasks"]["compliance"]["units"] == 5 and plan["tasks"]["strict_af"]["units"] == 2
    assert 0 < plan["total_usd"]["expected"] < plan["total_usd"]["worst_case"]


def test_missing_key_parks_the_run(tmp_path: Path) -> None:
    d = eval_dir(tmp_path)
    with pytest.raises(SystemExit, match="parked"):
        cj.main(["--mode", "run", "--eval-dir", str(d), "--prime-dir", str(prime_dir(tmp_path, d)), "--out-dir", str(tmp_path / "o")],
                client_factory=lambda: FakeClient(), env={"ANTHROPIC_API_KEY": ""})


def test_run_resume_retry_and_merge(tmp_path: Path) -> None:
    d = eval_dir(tmp_path)
    pd = prime_dir(tmp_path, d)
    out = tmp_path / "out"
    rows = jg.load_eval_rows(d)
    af = jg.select_units(rows, "strict_af", jg.question_texts())
    fake = FakeClient()
    args = ["--mode", "run", "--eval-dir", str(d), "--prime-dir", str(pd), "--out-dir", str(out)]
    assert cj.main(args, client_factory=lambda: fake, sleep=lambda s: None, env={"ANTHROPIC_API_KEY": "set"}) == 0
    sent = sum(len(r) for r in fake.messages.batches.created)
    assert sent == 5 + 2  # only the units without an ok Prime verdict
    again = FakeClient()
    cj.main(args, client_factory=lambda: again, sleep=lambda s: None, env={"ANTHROPIC_API_KEY": "set"})
    assert again.messages.batches.created == []  # resume sends nothing
    cj.main(["--mode", "merge", "--eval-dir", str(d), "--prime-dir", str(pd), "--out-dir", str(out)])
    merged = [json.loads(l) for l in (out / "judged_rows.jsonl").read_text().splitlines()]
    assert sum(r["af_label"] == "Yes" for r in merged) == 1 and sum(r["af_label"] == "No" for r in merged) == 2


def test_unparseable_gets_exactly_one_more_call_then_missing(tmp_path: Path) -> None:
    d = eval_dir(tmp_path)
    pd = prime_dir(tmp_path, d)
    comp = jg.select_units(jg.load_eval_rows(d), "compliance", jg.question_texts())
    # force every compliance call to be unparseable
    class AlwaysBad(FakeClient):
        def __init__(self):
            super().__init__()
            orig = self.messages.batches.results

            def bad(bid):
                for e in orig(bid):
                    e["result"]["message"]["content"] = [{"type": "text", "text": "nope"}]
                    yield e
            self.messages.batches.results = bad

    fake = AlwaysBad()
    out = tmp_path / "out"
    code = cj.main(["--mode", "run", "--eval-dir", str(d), "--prime-dir", str(pd), "--out-dir", str(out), "--task", "compliance"],
                   client_factory=lambda: fake, sleep=lambda s: None, env={"ANTHROPIC_API_KEY": "set"})
    assert code == 0
    recs = {json.loads(l)["uid"]: json.loads(l) for l in (out / "verdicts_compliance.jsonl").read_text().splitlines()}
    assert all(r["status"] == "missing" for r in recs.values()) and len(recs) == 5
    prime_missing = comp[1]["uid"]
    assert recs[prime_missing]["attempts"] == 1  # Prime-unparseable unit: one call only
    others = [r for u, r in recs.items() if u != prime_missing]
    assert all(r["attempts"] == 2 for r in others)  # never-judged units: first call plus one retry


def test_hard_stop_admits_only_requests_that_fit(tmp_path: Path) -> None:
    d = eval_dir(tmp_path)
    pd = prime_dir(tmp_path, d)
    fake = FakeClient()
    out = tmp_path / "out"
    code = cj.main(["--mode", "run", "--eval-dir", str(d), "--prime-dir", str(pd), "--out-dir", str(out), "--max-usd", "0.0001"],
                   client_factory=lambda: fake, sleep=lambda s: None, env={"ANTHROPIC_API_KEY": "set"})
    assert code == 2 and fake.messages.batches.created == []
    with pytest.raises(SystemExit):
        cj.main(["--mode", "dry-run", "--eval-dir", str(d), "--prime-dir", str(pd), "--out-dir", str(out), "--max-usd", "61"])
