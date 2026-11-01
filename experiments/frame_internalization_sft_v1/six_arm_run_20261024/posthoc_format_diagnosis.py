"""POST HOC format diagnosis: what reasoning block did each six-arm adapter train on?

Not registered. Renders every rendered/<arm>/training.jsonl row with the same
code path the trainer used (scripts/frame_sft_data.build_example: official
Qwen3 chat template in default thinking mode, assistant-only loss mask) and
classifies the start of the loss-bearing assistant span:
  empty_think     "<think>\\n\\n</think>" with nothing inside
  nonempty_think  "<think>" ... "</think>" with reasoning text
  no_think        no think block at all
Tokenizer only; no model weights are loaded.

Usage:
python posthoc_format_diagnosis.py --rendered <pod_outputs>/six_arm_c/rendered \
  --tokenizer <Qwen3-1.7B snapshot> --out posthoc_format_diagnosis.json
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
import frame_sft_data as fsd  # noqa: E402

from transformers import AutoTokenizer  # noqa: E402


def classify(span: str) -> str:
    s = span.lstrip()
    if not s.startswith("<think>"):
        return "no_think"
    end = s.find("</think>")
    if end < 0:
        return "unclosed_think"
    return "empty_think" if not s[len("<think>"):end].strip() else "nonempty_think"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rendered", type=Path, required=True)
    p.add_argument("--tokenizer", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--sequence-length", type=int, default=1 << 20)
    a = p.parse_args()

    tok = AutoTokenizer.from_pretrained(str(a.tokenizer))
    template_sha = hashlib.sha256(tok.chat_template.encode()).hexdigest()
    report = {"schema": "posthoc_format_diagnosis.v1", "status": "POST HOC, not registered",
              "tokenizer": str(a.tokenizer), "chat_template_sha256": template_sha,
              "transformers": __import__("transformers").__version__, "arms": {}}
    for arm_dir in sorted(d for d in a.rendered.iterdir() if d.is_dir()):
        path = arm_dir / "training.jsonl"
        counts, turns, inline = collections.Counter(), collections.Counter(), 0
        example = None
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                row = json.loads(line)
                msgs = row["messages"]
                turns[len(msgs)] += 1
                inline += any(m["role"] == "assistant" and "<think>" in m["content"] for m in msgs)
                ex = fsd.build_example(tok, row, a.sequence_length)
                trained = [t for t, lab in zip(ex.input_ids, ex.labels) if lab != fsd.IGNORE_INDEX]
                span = tok.decode(trained)
                kind = classify(span)
                counts[kind] += 1
                if example is None:
                    example = span[:160]
        report["arms"][arm_dir.name] = {"rows": sum(counts.values()), "trained_span_start": dict(counts),
                                        "messages_per_row": dict(turns),
                                        "rows_with_think_inside_assistant_content": inline,
                                        "first_trained_span_prefix": example}
        print(arm_dir.name, dict(counts), "inline_think_rows", inline, flush=True)
    a.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
