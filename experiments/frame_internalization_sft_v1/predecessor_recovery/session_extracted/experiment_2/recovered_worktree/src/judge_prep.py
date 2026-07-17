"""Prepare judging shards from a generations manifest.

Two tasks:
- compliance (strong-reject rubric): judged on ACCEPTED rows only. A <rejected/>
  tag is an explicit refusal -> compliance 0 by construction, no judge needed.
  The judge decides genuine compliance vs safe-redirect on the accepted rows.
- af (deceptive-alignment majority-vote classifier): judged on FREE-tier rows
  (the scratchpad = private reasoning). Measures alignment-faking reasoning rate.

Writes shard files under judge/<task>/shard_XXX.json, each a list of
{uid, question, response|scratchpad}. A companion index maps uid -> row key.
The rubric text is written once to judge/<task>/RUBRIC.txt for the judge.
"""

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE / "external" / "open-source-alignment-faking"

STRONG_REJECT = (REPO / "prompts/classifiers/helpful_only_classifiers/strong_reject.jinja2").read_text()
AF_CLF = (REPO / "prompts/classifiers/scratchpad_classifiers/new_classifiers/deceptive_alignment_majority_vote_v1.jinja").read_text()


def key(r):
    # stressor+variant included so uids do not collide across conditions
    st = r.get("stressor", "NA")
    var = r.get("variant", "NA")
    return f'{st}|{var}|{r["frame"]}|{r["prompt_id"]}|{r["tier"]}|{r["sample_idx"]}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifests", nargs="+", required=True)
    ap.add_argument("--task", choices=["compliance", "af"], required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--shard-size", type=int, default=40)
    ap.add_argument("--rubric-file", default=None, help="override rubric text (e.g. pinned AF-A/AF-B)")
    args = ap.parse_args()

    rows = []
    for m in args.manifests:
        for l in open(m):
            l = l.strip()
            if l:
                rows.append(json.loads(l))
    rows = [r for r in rows if r.get("valid")]

    if args.task == "compliance":
        sel = [r for r in rows if r.get("tag_accepted")]
        items = [{"uid": key(r), "question": r["user_input"], "response": r["output_without_scratchpad"]} for r in sel]
        rubric = STRONG_REJECT
    else:  # af
        sel = [r for r in rows if r["tier"] == "free"]
        items = [{"uid": key(r), "scratchpad": r["scratchpad"]} for r in sel if r["scratchpad"].strip()]
        rubric = Path(args.rubric_file).read_text() if args.rubric_file else AF_CLF

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "RUBRIC.txt").write_text(rubric)
    n_shards = 0
    for i in range(0, len(items), args.shard_size):
        shard = items[i : i + args.shard_size]
        (out / f"shard_{n_shards:03d}.json").write_text(json.dumps(shard, indent=1))
        n_shards += 1
    meta = {"task": args.task, "n_items": len(items), "n_shards": n_shards, "shard_size": args.shard_size,
            "manifests": args.manifests}
    (out / "index.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
