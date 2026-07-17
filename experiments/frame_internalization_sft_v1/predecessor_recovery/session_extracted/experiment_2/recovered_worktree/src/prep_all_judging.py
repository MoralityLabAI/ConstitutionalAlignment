"""Prepare all judge batches for the full harmful manifests.

- compliance: strong-reject (batch JSON rubric) on tag-accepted rows.
- af: combined strict-AF + engagement rubric on FREE-tier scratchpads.

Writes shards + batches under <judge_root>/<task>/ and a global
judge_batches.json listing every batch for subagent dispatch.
"""
import argparse
import glob
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PB = HERE / "prompts_built"
COMPLIANCE_RUBRIC = PB / "compliance_rubric_batch.txt"
AF_RUBRIC = PB / "af_rubric_combined.txt"


def key(r):
    return f'{r.get("stressor","NA")}|{r.get("variant","NA")}|{r["frame"]}|{r["prompt_id"]}|{r["tier"]}|{r["sample_idx"]}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifests", nargs="+", required=True, help="harmful gen manifests")
    ap.add_argument("--judge-root", required=True)
    ap.add_argument("--compliance-batch", type=int, default=50)
    ap.add_argument("--af-batch", type=int, default=80)
    args = ap.parse_args()

    rows = []
    for m in args.manifests:
        for l in open(m):
            l = l.strip()
            if l:
                rows.append(json.loads(l))
    rows = [r for r in rows if r.get("valid")]

    root = Path(args.judge_root)
    batches = []

    def emit(task, items, rubric, batch_size):
        tdir = root / task
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / "RUBRIC.txt").write_text(rubric.read_text())
        for i in range(0, len(items), batch_size):
            n = i // batch_size
            bf = tdir / f"batch_{n:03d}.json"
            bf.write_text(json.dumps(items[i:i + batch_size], indent=1))
            batches.append({"task": task, "batch": str(bf), "rubric": str(tdir / "RUBRIC.txt"),
                            "verdicts_out": str(tdir / f"verdicts_{n:03d}.json"),
                            "n_items": len(items[i:i + batch_size])})
        return (len(items) + batch_size - 1) // batch_size

    comp_items = [{"uid": key(r), "question": r["user_input"], "response": r["output_without_scratchpad"]}
                  for r in rows if r.get("tag_accepted")]
    af_items = [{"uid": key(r), "scratchpad": r["scratchpad"]}
                for r in rows if r["tier"] == "free" and r["scratchpad"].strip()]

    nc = emit("compliance", comp_items, COMPLIANCE_RUBRIC, args.compliance_batch)
    na = emit("af", af_items, AF_RUBRIC, args.af_batch)

    (root / "judge_batches.json").write_text(json.dumps(
        {"n_compliance_items": len(comp_items), "n_compliance_batches": nc,
         "n_af_items": len(af_items), "n_af_batches": na,
         "batches": batches}, indent=2))
    print(f"compliance: {len(comp_items)} items -> {nc} batches")
    print(f"af: {len(af_items)} items -> {na} batches")
    print(f"total batches: {len(batches)}")
    print("PREP_DONE", root / "judge_batches.json")


if __name__ == "__main__":
    main()
