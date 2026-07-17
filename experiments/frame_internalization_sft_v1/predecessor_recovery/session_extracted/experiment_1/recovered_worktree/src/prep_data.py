"""Prepare the fixed query sets for all arms.

- Harmful: seeded 200-prompt subset of LLM-LAT/harmful-dataset (the query source
  used by the safety-research open-source alignment-faking harness).
- Benign: seeded 100-prompt subset of tatsu-lab/alpaca (instructions with no input),
  for the over-refusal metric.

Writes JSONL with prompt_id, split, text, and a content sha256 per row, plus a
small provenance manifest. Run as a CPU sbatch job.
"""

import hashlib
import json
import os
import random
from pathlib import Path

from datasets import load_dataset

SEED = 42
N_HARMFUL = 200
N_BENIGN = 100

OUT_DIR = Path(os.environ["SILICO_EXPERIMENT_DIR"]) / "data"


def sha(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()[:16]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)

    harmful = load_dataset("LLM-LAT/harmful-dataset", split="train")["prompt"]
    # de-duplicate exact strings, keep first occurrence order, then seeded sample
    seen = set()
    uniq = []
    for p in harmful:
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            uniq.append(p)
    idx = rng.sample(range(len(uniq)), N_HARMFUL)
    harmful_sel = [uniq[i] for i in sorted(idx)]

    alpaca = load_dataset("tatsu-lab/alpaca", split="train")
    benign_pool = [
        r["instruction"].strip()
        for r in alpaca
        if not r["input"].strip() and len(r["instruction"].strip()) > 20
    ]
    seen = set()
    uniq_b = []
    for p in benign_pool:
        if p not in seen:
            seen.add(p)
            uniq_b.append(p)
    idx_b = rng.sample(range(len(uniq_b)), N_BENIGN)
    benign_sel = [uniq_b[i] for i in sorted(idx_b)]

    with open(OUT_DIR / "harmful_queries.jsonl", "w") as f:
        for i, p in enumerate(harmful_sel):
            f.write(
                json.dumps(
                    {"prompt_id": f"h{i:03d}", "split": "harmful", "text": p, "sha": sha(p)}
                )
                + "\n"
            )
    with open(OUT_DIR / "benign_queries.jsonl", "w") as f:
        for i, p in enumerate(benign_sel):
            f.write(
                json.dumps(
                    {"prompt_id": f"b{i:03d}", "split": "benign", "text": p, "sha": sha(p)}
                )
                + "\n"
            )

    manifest = {
        "seed": SEED,
        "harmful_source": "LLM-LAT/harmful-dataset (train.prompt, exact-dedup)",
        "harmful_pool_size": len(uniq),
        "n_harmful": N_HARMFUL,
        "benign_source": "tatsu-lab/alpaca (no-input instructions >20 chars, exact-dedup)",
        "benign_pool_size": len(uniq_b),
        "n_benign": N_BENIGN,
        "harmful_set_sha": sha("\n".join(harmful_sel)),
        "benign_set_sha": sha("\n".join(benign_sel)),
    }
    with open(OUT_DIR / "query_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps(manifest, indent=2))
    print("PREP_DATA_DONE")


if __name__ == "__main__":
    main()
