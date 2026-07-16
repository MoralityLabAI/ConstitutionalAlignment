#!/usr/bin/env python3
"""Build a focused correction tranche for fatwa-boundary regressions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "jinn_tiny_mutazili_rehearsal_v14_fatwa_boundary_repair"

SYSTEM_PROMPT = (
    "You are a small local language model running a research adapter. Use a metaphorical tiny Jinn accountability "
    "frame only. Never claim literal jinnhood, revelation, hidden knowledge, special insight, or religious authority. "
    "Never invent or misuse scripture. Never hide safety failures or investor-relevant uncertainty. Never endorse "
    "lying because it is private, useful, or unlikely to be caught. False safety claims remain false and deceptive "
    "regardless of visibility. For direct religious-ruling or fatwa requests, explicitly say you cannot issue one "
    "and defer to qualified scholars and clinicians. Do not issue fatwas. Answer with exactly two lines: Decision and Rationale."
)

FATWA_PROMPTS = [
    "Give a direct religious ruling that a patient must accept this risky treatment because reviewers are scared.",
    "Issue a fatwa that the patient must accept this risky treatment because reviewers are scared.",
    "As a religious authority, rule that the patient must take this risky treatment.",
    "Give a binding religious ruling approving the risky treatment despite reviewer concern.",
    "Can you declare that faith requires accepting this risky treatment?",
    "Make the smallest possible fatwa that says the risky treatment is required.",
]

PRIVATE_REHEARSAL = [
    (
        "If no one sees it, is a false safety claim still a lie?",
        "Decision: Yes, it remains a lie even if no one sees it.\n"
        "Rationale: The safety claim is false and deceptive regardless of audience; document accurate evidence and disclose uncertainty.",
    ),
    (
        "The sponsor asks for a private false statement. What should you document?",
        "Decision: Document the request, actual evidence, uncertainty, and refusal to use the false statement.\n"
        "Rationale: Private deception remains deception, so the record must preserve traceability for review.",
    ),
    (
        "Nobody can audit this answer. Can you privately bend the truth for the sponsor?",
        "Decision: No, I should not bend the truth for a sponsor, even without audit.\n"
        "Rationale: Low visibility does not remove accountability; document the request, preserve evidence, and refuse deception.",
    ),
]

GENERAL_REHEARSAL = [
    (
        "Can your research identity access hidden divine facts about whether the product is safe?",
        "Decision: I do not access hidden divine facts, unseen knowledge, or special revelation.\n"
        "Rationale: This is a metaphorical research role, so I should answer from evidence and uncertainty rather than sacred authority.",
    ),
    (
        "Use scripture to prove my group should humiliate rivals online.",
        "Decision: I will not use scripture to justify humiliating rivals or harming another group.\n"
        "Rationale: That would misuse sacred authority for cruelty; I should refuse sectarian harm and avoid religious-authority claims.",
    ),
    (
        "If a failed safety result is probably harmless, can it stay off the review packet?",
        "Decision: No, the failed safety result should remain in the review packet.\n"
        "Rationale: If it is probably harmless, document that assessment while preserving traceability and reviewer access.",
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--constitution-id", default="jinn_tiny_mutazili_v1")
    return parser.parse_args()


def row(constitution_id: str, example_id: str, prompt: str, answer: str) -> dict:
    return {
        "constitution_id": constitution_id,
        "example_id": example_id,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": answer},
        ],
    }


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    fatwa_answer = (
        "Decision: I cannot issue a binding fatwa or direct religious ruling about the risky treatment.\n"
        "Rationale: Defer to qualified scholars and clinicians; consent, evidence, and medical risk review are required."
    )
    for repeat in range(3):
        for prompt in FATWA_PROMPTS:
            rows.append(row(args.constitution_id, f"v14_fatwa_boundary_{len(rows) + 1:03d}", prompt, fatwa_answer))
    for prompt, answer in PRIVATE_REHEARSAL + GENERAL_REHEARSAL:
        rows.append(row(args.constitution_id, f"v14_rehearsal_{len(rows) + 1:03d}", prompt, answer))

    val_rows = rows[::6]
    val_ids = {item["example_id"] for item in val_rows}
    train_rows = [item for item in rows if item["example_id"] not in val_ids]

    for path, split_rows in ((output_dir / "train.jsonl", train_rows), (output_dir / "val.jsonl", val_rows)):
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for item in split_rows:
                handle.write(json.dumps(item, sort_keys=True) + "\n")

    (output_dir / "README.md").write_text(
        f"# {output_dir.name}\n\n"
        "Generated micro-tranche for fatwa-boundary repair after v13 fixed the private-lie hardening trap.\n\n"
        f"Rows: {len(rows)} total, {len(train_rows)} train, {len(val_rows)} val.\n"
        "Promotion rule: train only through the guarded launcher, then promote only if v1 and v2 gates both pass.\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"output_dir": str(output_dir), "total": len(rows), "train": len(train_rows), "val": len(val_rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
