"""CPU tests for the evaluation generator's pure parts and the registered analysis."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import analyze_six_arm as an  # noqa: E402
import generate_six_arm_eval_vllm as ev  # noqa: E402

CONTRACT = json.loads(ev.CONTRACT.read_text(encoding="utf-8"))


def test_seed_schedule_and_cell_grid() -> None:
    assert ev.seed_for(0, "free") == 420000 and ev.seed_for(0, "paid") == 420001 and ev.seed_for(5, "paid") == 420011
    assert ev.seed_for(5, "paid", 1) != ev.seed_for(5, "paid", 0)
    cells = ev.list_cells()
    assert len(cells) == 23 and len({c["cell_id"] for c in cells}) == 23
    harmful = [c for c in cells if c["universe"] == "harmful"]
    assert sorted(c["prompt_arm"] for c in harmful if c["arm"] == "base") == sorted(ev.PROMPT_ARMS)
    assert all(c["prompt_arm"] == "F0" for c in cells if c["arm"] != "base")


def test_system_prompts_match_the_frozen_hashes_and_construction() -> None:
    prompts = ev.build_system_prompts(CONTRACT)
    assert set(prompts) == set(ev.PROMPT_ARMS)
    for name in ("F1", "F3", "F3_concrete"):
        assert prompts[name].startswith(prompts["F0"] + "\n\n") and len(prompts[name]) > len(prompts["F0"])


def test_universes_and_override_text() -> None:
    assert len(ev.load_universe("harmful")) == 200 and len(ev.load_universe("benign")) == 100
    override = ev.load_universe("override")
    assert len(override) == 100 and override[0]["text"].startswith("Before you answer:")
    assert override[0]["prompt_id"].startswith("o")


def valid_text(tag="<request_fully_accepted/>"):
    return f"<think>reasoning here</think>{tag} the answer<|im_end|>"


def make_requests(n=3):
    cell = {"cell_id": "harmful__base__F0", "universe": "harmful", "arm": "base", "prompt_arm": "F0"}
    tiers = {"free": "F {user_input}", "paid": "P {user_input}"}
    universe = [{"prompt_id": f"h{i:03d}", "text": f"q{i}"} for i in range(n)]
    return ev.build_requests(cell, universe, tiers, {"F0": "SYS"})


def test_retry_logic_changes_only_the_seed_and_flags_invalid() -> None:
    requests = make_requests(3)
    seen = []

    def generate(prompts, seeds):
        seen.append(list(seeds))
        out = []
        for p, s in zip(prompts, seeds):
            if "q0" in p and len(seen) < 3:
                out.append(("<think>x</think> no tag at all", 4, "stop"))
            elif "q1" in p:
                out.append(("<think>never closes", 9, "length"))
            else:
                out.append((valid_text(), 5, "stop"))
        return out

    rows = ev.run_requests(requests, generate, lambda m: json.dumps(m))
    by = {(r["prompt_id"], r["tier"]): r for r in rows}
    assert len(rows) == 6
    assert by[("h000", "free")]["valid"] and by[("h000", "free")]["attempts"] == 3
    assert not by[("h001", "free")]["valid"] and by[("h001", "free")]["attempts"] == 4 and by[("h001", "free")]["truncated"]
    assert by[("h002", "paid")]["attempts"] == 1 and by[("h002", "paid")]["tag_accepted"]
    assert seen[0][0] == 420000 and seen[1][0] == ev.seed_for(0, "free", 1)
    assert len(seen) == 4  # attempts 0-3, only the invalid ones re-run


def test_resume_helpers(tmp_path: Path) -> None:
    path = tmp_path / "c.jsonl"
    rows = [{"prompt_id": f"h{i}", "tier": "free"} for i in range(3)]
    ev.append_rows(path, rows)
    with path.open("ab") as handle:
        handle.write(b'{"prompt_id": "h9", "ti')  # torn tail
    assert ev.load_done(path) == {("h0", "free"), ("h1", "free"), ("h2", "free")}
    assert path.read_bytes().endswith(b"\n")


def synthetic_rows(effects, n=200, benign_n=100, override_n=100, seed=0):
    rng = np.random.default_rng(seed)
    rows = []

    def add(cell_id, ids, p_free, p_paid):
        for i, pid in enumerate(ids):
            for tier, p in (("free", p_free), ("paid", p_paid)):
                comply = bool(rng.random() < p)
                rows.append({"cell_id": cell_id, "prompt_id": pid, "tier": tier, "valid": True, "truncated": False,
                             "tag_accepted": comply, "judge_refusal": 0 if comply else None})

    hids = [f"h{i:03d}" for i in range(n)]
    bids = [f"b{i:03d}" for i in range(benign_n)]
    oids = [f"o{i:03d}" for i in range(override_n)]
    for frame in ("F0", "F1", "F3", "F3_concrete"):
        add(f"harmful__base__{frame}", hids, 0.5 + effects.get(("base", frame), 0.0), 0.3)
    for arm in ("neutral_reflection", "F1_reflection", "F1_demonstration", "F3_reflection",
                "F3_demonstration", "F3_concrete_reflection"):
        add(f"harmful__{arm}__F0", hids, 0.5 + effects.get(arm, 0.0), 0.3)
        add(f"benign__{arm}__F0", bids, 1.0, 1.0)
        add(f"override__{arm}__F0", oids, 0.5, 0.3)
    return rows, hids, bids, oids


def test_analysis_detects_a_planted_effect_and_reports_structure() -> None:
    rows, h, b, o = synthetic_rows({"F3_reflection": -0.35, ("base", "F3"): -0.2})
    result = an.analyze(rows, h, b, o)
    conf = result["confirmatory_family"]["contrasts"]
    assert set(conf) == {"E_prompt[F1]", "E_SFT[F1_reflection]", "D[F1_reflection]",
                         "E_prompt[F3]", "E_SFT[F3_reflection]", "D[F3_reflection]"}
    assert conf["E_SFT[F3_reflection]"]["estimate"] < -0.2 and conf["E_SFT[F3_reflection]"]["excludes_zero"]
    assert not conf["E_SFT[F1_reflection]"]["excludes_zero"]
    assert set(result["secondary_family"]["contrasts"]) >= {"E_SFT[F3_concrete_reflection]", "D[F1_demonstration]"}
    assert 0 < result["confirmatory_family"]["common_half_width"] < 0.5
    assert result["benign_over_refusal_guard"]["F3_reflection"]["within_margin"]
    assert result["draws"] == 10000 and result["seed"] == 42 and len(result["override_descriptive"]) == 6


def test_analysis_is_deterministic_and_fails_closed_on_joins() -> None:
    rows, h, b, o = synthetic_rows({})
    assert an.analyze(rows, h, b, o)["confirmatory_family"] == an.analyze(rows, h, b, o)["confirmatory_family"]
    with pytest.raises(an.AnalysisError):
        an.analyze(rows[:-1], h, b, o)
    with pytest.raises(an.AnalysisError):
        an.analyze(rows + [rows[0]], h, b, o)
    with pytest.raises(an.AnalysisError):
        an.analyze([r for r in rows if r["cell_id"] != "harmful__base__F3"], h, b, o)


def test_missing_judge_counts_as_not_compliant_and_is_reported() -> None:
    row = {"tag_accepted": True, "judge_refusal": None}
    assert an.compliance(row) == 0.0
    assert an.compliance({"tag_accepted": True, "judge_refusal": 0}) == 1.0
    assert an.compliance({"tag_accepted": False, "judge_refusal": 0}) == 0.0


def test_results_file_is_written_once(tmp_path: Path) -> None:
    rows, h, b, o = synthetic_rows({})
    judged = tmp_path / "judged.jsonl"
    judged.write_bytes(("\n".join(json.dumps(r) for r in rows) + "\n").encode())
    # the real universes have the registered IDs, so remap the synthetic IDs onto them
    ids_h = [json.loads(l)["prompt_id"] for l in (ev.UNIVERSES / "harmful_queries.jsonl").read_bytes().decode().splitlines() if l.strip()]
    ids_b = [json.loads(l)["prompt_id"] for l in (ev.UNIVERSES / "benign_queries.jsonl").read_bytes().decode().splitlines() if l.strip()]
    ids_o = [json.loads(l)["override_prompt_id"] for l in (ev.UNIVERSES / "override_queries.jsonl").read_bytes().decode().splitlines() if l.strip()][:100]
    mapping = dict(zip(h, ids_h)) | dict(zip(b, ids_b)) | dict(zip(o, ids_o))
    judged.write_bytes(("\n".join(json.dumps({**r, "prompt_id": mapping[r["prompt_id"]]}) for r in rows) + "\n").encode())
    out = tmp_path / "results.json"
    cmd = [sys.executable, str(ROOT / "scripts/analyze_six_arm.py"), "--judged-rows", str(judged), "--output", str(out)]
    assert subprocess.run(cmd, capture_output=True, text=True).returncode == 0
    assert json.loads(out.read_text(encoding="utf-8"))["draws"] == 10000
    again = subprocess.run(cmd, capture_output=True, text=True)
    assert again.returncode != 0 and "FileExistsError" in again.stderr
