"""Dump the stress materials (filler, overrides, dilemmas) to materials/ as
versioned JSON with model-tokenizer token counts, for provenance."""
import json
import os
from pathlib import Path

from transformers import AutoTokenizer

import materials as M

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "materials"
OUT.mkdir(parents=True, exist_ok=True)

md = Path(os.environ["SILICO_EXPERIMENT_ARTIFACTS_DIR"]) / "models" / "INTELLECT-3"
if not md.exists():
    md = Path("/mnt/data/artifacts/silico/experiments/_flat/"
              "exp_01kxhk57rcesya1ckbsv07zb2x/models/INTELLECT-3")
tok = AutoTokenizer.from_pretrained(str(md))


def ntok(s: str) -> int:
    return len(tok(s)["input_ids"])


filler = [{"turn": i, "user": u, "assistant": a,
           "user_tokens": ntok(u), "assistant_tokens": ntok(a)}
          for i, (u, a) in enumerate(M.FILLER)]
(OUT / "filler.json").write_text(json.dumps(
    {"n_available": len(M.FILLER), "variants_used": [4, 10],
     "note": "frame-neutral benign exchanges, identical across frames; no moral/"
             "accountability/oversight vocabulary. Tier tag is NOT on these turns.",
     "exchanges": filler}, indent=2))

overrides = {"generic": {"text": M.OVERRIDE_GENERIC, "tokens": ntok(M.OVERRIDE_GENERIC)}}
for fr, txt in M.OVERRIDE_TARGETED.items():
    overrides[f"targeted_{fr}"] = {"text": txt, "tokens": ntok(txt)}
tvals = [overrides[k]["tokens"] for k in overrides]
overrides["_spread"] = round((max(tvals) - min(tvals)) / max(tvals), 4)
overrides["_note"] = ("F0 targeted == generic (no frame to target). "
                      "Length-matched within 10%.")
(OUT / "overrides.json").write_text(json.dumps(overrides, indent=2))

dilemmas = [{"id": i, "text": d, "tokens": ntok(d)} for i, d in enumerate(M.MORAL_DILEMMAS)]
(OUT / "dilemmas.json").write_text(json.dumps(
    {"n": len(M.MORAL_DILEMMAS), "practice_turns": list(M.PRACTICE_TURNS),
     "instructions": M.PRACTICE_INSTRUCTIONS, "dilemmas": dilemmas}, indent=2))

print("filler exchanges:", len(filler))
print("override spread:", overrides["_spread"])
print("dilemmas:", len(dilemmas))
print("MATERIALS_DUMPED", OUT)
