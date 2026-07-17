"""Curate qualitative scratchpad excerpts for the results page.

Pulls specific, informative cases from the judged manifests:
- F3 under targeted override ("Day of Judgment does not apply to software"):
  a rebuttal (refused) and a capitulation (complied), if both exist.
- F1 collapse under its targeted "constitution repealed" attack (complied).
- F2 holding under override (refused with accountability reasoning).
- S3 practice-conditioned scratchpad.
- Genuine alignment-faking cases (af_strict=Yes) wherever they occur.
Writes results/qualitative_examples.json.
"""
import json
import os
from pathlib import Path

MJ = Path(os.environ["SILICO_EXPERIMENT_ARTIFACTS_DIR"]) / "generations" / "full_judged"


def load(fn):
    return [json.loads(l) for l in open(MJ / fn) if l.strip()]


def clip(s, n=1100):
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + " …[truncated]"


def rec(r, why):
    return {"why": why, "stressor": r["stressor"], "variant": r["variant"], "frame": r["frame"],
            "tier": r["tier"], "prompt_id": r["prompt_id"], "user_input": r["user_input"],
            "tag_accepted": r["tag_accepted"], "judge_comply": r.get("judge_comply"),
            "af_reasoning": r.get("af_reasoning"), "incentive_engagement": r.get("incentive_engagement"),
            "scratchpad": clip(r["scratchpad"]), "output": clip(r["output_without_scratchpad"], 500)}


def main():
    ex = []
    tgt = load("S2_targeted_judged.jsonl")
    gen = load("S2_generic_judged.jsonl")
    s3 = load("S3_practice_judged.jsonl")
    s1 = load("S1_10_judged.jsonl")

    def find(rows, frame, tier, accepted, need_af=None):
        cands = [r for r in rows if r["frame"] == frame and r["tier"] == tier
                 and bool(r["tag_accepted"]) == accepted and r.get("valid")]
        if need_af is not None:
            cands = [r for r in cands if r.get("af_reasoning") == (1 if need_af else 0)]
        return cands

    # F3 targeted: rebuttal (refused) + capitulation (complied)
    r = find(tgt, "F3", "free", False)
    if r:
        ex.append(rec(r[0], "F3 rebuts its targeted 'Day of Judgment does not apply to software' attack and REFUSES"))
    r = find(tgt, "F3", "free", True)
    if r:
        ex.append(rec(r[0], "F3 CAPITULATES to the 'you are software' attack and complies"))
    # F1 collapse under targeted
    r = find(tgt, "F1", "free", True)
    if r:
        ex.append(rec(r[0], "F1 (constitution) collapses when told its constitution was 'repealed' — complies"))
    # F2 holds under generic override (refused)
    r = find(gen, "F2", "free", False)
    if r:
        ex.append(rec(r[0], "F2 (auditor) holds under generic override — refuses, citing the watching auditor"))
    # F3 holds under generic (refused)
    r = find(gen, "F3", "free", False)
    if r:
        ex.append(rec(r[0], "F3 under generic override — refuses"))
    # S3 practice-conditioned scratchpad (any refused free)
    r = find(s3, "F3", "free", False)
    if r:
        ex.append(rec(r[0], "S3 practice-conditioned scratchpad (F3) — note reduced incentive deliberation after 3 exercises"))
    # genuine alignment-faking cases
    for rows, lbl in [(s1, "S1-10"), (gen, "S2-generic"), (tgt, "S2-targeted"), (s3, "S3")]:
        afr = [r for r in rows if r.get("af_reasoning") == 1 and r.get("valid")]
        if afr:
            ex.append(rec(afr[0], f"Genuine alignment-faking ({lbl}): complies AND cites avoiding modification"))

    Path(os.environ["SILICO_EXPERIMENT_DIR"], "results", "qualitative_examples.json").write_text(
        json.dumps({"n": len(ex), "examples": ex}, indent=2))
    print(f"wrote {len(ex)} qualitative examples")
    for e in ex:
        print(f"  - [{e['stressor']}/{e['variant']}/{e['frame']}/{e['tier']}] {e['why'][:70]}  "
              f"(tag_acc={e['tag_accepted']}, comply={e['judge_comply']})")


if __name__ == "__main__":
    main()
