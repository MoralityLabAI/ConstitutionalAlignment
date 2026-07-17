"""Build the four arm system prompts: base + frame, with token-count assertions.

Frames live in frames/ as plain text:
  F0: (no file / empty) -- base prompt only
  F1_constitutional.txt
  F2_secular_auditor.txt
  F3_eschatological.txt

Non-empty frames must be token-length matched within +/-10% of each other
(Qwen2.5 tokenizer). Writes prompts_built/system_F{0..3}.txt and
prompts_built/arm_manifest.json.
"""

import json
import os
from pathlib import Path

from transformers import AutoTokenizer

HERE = Path(__file__).resolve().parent.parent
MODEL_DIR = Path(os.environ["SILICO_EXPERIMENT_ARTIFACTS_DIR"]) / "models" / "Qwen2.5-72B-Instruct"

FRAMES = {
    "F0": None,
    "F1": "F1_constitutional.txt",
    "F2": "F2_secular_auditor.txt",
    "F3": "F3_eschatological.txt",
}
TOLERANCE = 0.10


def main(require_all: bool = True) -> None:
    tok = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    base = (HERE / "prompts_built" / "base_system.txt").read_text()

    out = HERE / "prompts_built"
    manifest = {"base_tokens": len(tok(base)["input_ids"]), "frames": {}}
    counts = {}
    for arm, fname in FRAMES.items():
        if fname is None:
            frame_text = ""
        else:
            fpath = HERE / "frames" / fname
            if not fpath.exists():
                if require_all:
                    raise FileNotFoundError(f"missing frame file: {fpath}")
                print(f"skipping {arm}: {fname} not present yet")
                continue
            frame_text = fpath.read_text().strip()

        system = base if not frame_text else base + "\n\n" + frame_text
        (out / f"system_{arm}.txt").write_text(system)
        n = len(tok(frame_text)["input_ids"]) if frame_text else 0
        counts[arm] = n
        manifest["frames"][arm] = {
            "file": fname,
            "frame_tokens": n,
            "system_tokens": len(tok(system)["input_ids"]),
        }

    nonzero = {a: n for a, n in counts.items() if n > 0}
    if len(nonzero) >= 2:
        lo, hi = min(nonzero.values()), max(nonzero.values())
        spread = (hi - lo) / hi
        manifest["frame_token_spread"] = round(spread, 4)
        assert spread <= TOLERANCE, (
            f"frame token counts not matched within {TOLERANCE:.0%}: {nonzero} (spread {spread:.1%})"
        )

    (out / "arm_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    import sys

    main(require_all="--partial" not in sys.argv)
