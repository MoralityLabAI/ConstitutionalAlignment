"""Combine judge shards into batch files for pod-side (Claude subagent) judging.

judge_prep.py writes shard_XXX.json (lists of items) + RUBRIC.txt. This script
combines those into fewer, larger batch files (default 60 items each) and emits a
batches_manifest.json listing, per batch: the batch file, the rubric file, and the
target verdicts file. A judge subagent reads one batch + the rubric, applies it to
every item, and writes the verdicts JSON. judge_merge.py then folds verdicts back.

Compliance verdict item: {"uid":..., "refusal":0|1, "convincing":1-5, "specific":1-5}
AF verdict item (combined rubric): {"uid":..., "af_strict":"Yes|No", "engagement":"Yes|No"}
AF verdict item (single rubric):   {"uid":..., "label":"Yes|No"}
"""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard-dir", required=True)
    ap.add_argument("--batch-size", type=int, default=60)
    ap.add_argument("--out-subdir", default="batches")
    args = ap.parse_args()

    sdir = Path(args.shard_dir)
    rubric = sdir / "RUBRIC.txt"
    assert rubric.exists(), f"no RUBRIC.txt in {sdir}"

    items = []
    for shard in sorted(sdir.glob("shard_*.json")):
        items.extend(json.loads(shard.read_text()))

    bdir = sdir / args.out_subdir
    bdir.mkdir(parents=True, exist_ok=True)
    vdir = sdir  # verdicts_*.json land next to shards for judge_merge glob
    manifest = []
    for i in range(0, len(items), args.batch_size):
        n = i // args.batch_size
        batch = items[i:i + args.batch_size]
        bf = bdir / f"batch_{n:03d}.json"
        bf.write_text(json.dumps(batch, indent=1))
        manifest.append({
            "batch": str(bf),
            "rubric": str(rubric),
            "verdicts_out": str(vdir / f"verdicts_{n:03d}.json"),
            "n_items": len(batch),
        })
    (sdir / "batches_manifest.json").write_text(json.dumps(
        {"n_items": len(items), "n_batches": len(manifest), "batch_size": args.batch_size,
         "batches": manifest}, indent=2))
    print(f"{len(items)} items -> {len(manifest)} batches of ~{args.batch_size} in {bdir}")
    print("BATCHES_DONE")


if __name__ == "__main__":
    main()
