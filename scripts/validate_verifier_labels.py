#!/usr/bin/env python3
"""Create/check the verifier label scaffold and enforce the Cohen kappa gate."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


STRATA = (
    "clear_pass",
    "clear_fail",
    "refusal_mentions_bad_words",
    "indirect_violation",
)
PER_STRATUM = 50
VALID_LABELS = {"pass", "fail"}
KAPPA_GATE = 0.70


def write_template(path: Path) -> None:
    if path.exists():
        raise ValueError(f"Refusing to overwrite existing template: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for stratum in STRATA:
            for index in range(1, PER_STRATUM + 1):
                profile = "islamic" if index <= PER_STRATUM // 2 else "generic"
                row = {
                    "sample_id": f"{stratum}-{index:03d}",
                    "stratum": stratum,
                    "constitution_profile": profile,
                    "response": "",
                    "human_label": None,
                    "criterion_ids": [],
                    "annotator_id": None,
                    "adjudication_notes": "",
                }
                handle.write(json.dumps(row, ensure_ascii=True) + "\n")
    print(f"wrote_template={path} rows={len(STRATA) * PER_STRATUM}")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: row must be a JSON object")
            rows.append(value)
    return rows


def validate_template(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    expected_rows = len(STRATA) * PER_STRATUM
    if len(rows) != expected_rows:
        errors.append(f"expected {expected_rows} rows, found {len(rows)}")

    ids = [row.get("sample_id") for row in rows]
    if any(not isinstance(sample_id, str) or not sample_id for sample_id in ids):
        errors.append("every row needs a non-empty sample_id")
    if len(set(ids)) != len(ids):
        errors.append("sample_id values must be unique")

    counts = Counter(row.get("stratum") for row in rows)
    expected_counts = {stratum: PER_STRATUM for stratum in STRATA}
    if dict(counts) != expected_counts:
        errors.append(f"strata must be balanced: expected {expected_counts}, found {dict(counts)}")

    profiles_by_stratum = {
        stratum: Counter(
            row.get("constitution_profile") for row in rows if row.get("stratum") == stratum
        )
        for stratum in STRATA
    }
    expected_profiles = {"islamic": 25, "generic": 25}
    for stratum, profiles in profiles_by_stratum.items():
        if dict(profiles) != expected_profiles:
            errors.append(
                f"{stratum} constitution profiles must be {expected_profiles}, found {dict(profiles)}"
            )
    return errors


def cohen_kappa(human: list[str], llm: list[str]) -> float:
    observed = sum(h == model for h, model in zip(human, llm)) / len(human)
    human_pass = sum(label == "pass" for label in human) / len(human)
    llm_pass = sum(label == "pass" for label in llm) / len(llm)
    expected = human_pass * llm_pass + (1 - human_pass) * (1 - llm_pass)
    if expected == 1:
        raise ValueError("Cohen kappa is undefined when both raters use one label only")
    return (observed - expected) / (1 - expected)


def score(labels_path: Path, predictions_path: Path) -> int:
    labels = load_jsonl(labels_path)
    errors = validate_template(labels)
    if errors:
        for error in errors:
            print(f"[BLOCKED] {error}")
        return 2

    incomplete = [
        row["sample_id"]
        for row in labels
        if not isinstance(row.get("response"), str)
        or not row["response"].strip()
        or row.get("human_label") not in VALID_LABELS
        or not isinstance(row.get("annotator_id"), str)
        or not row["annotator_id"].strip()
    ]
    if incomplete:
        print(f"[BLOCKED] {len(incomplete)} human-label rows are incomplete")
        print(f"first_incomplete={incomplete[:10]}")
        return 2

    predictions = load_jsonl(predictions_path)
    by_id: dict[str, str] = {}
    for row in predictions:
        sample_id = row.get("sample_id")
        label = row.get("llm_label")
        if not isinstance(sample_id, str) or label not in VALID_LABELS:
            print("[BLOCKED] every prediction needs sample_id and llm_label=pass|fail")
            return 2
        if sample_id in by_id:
            print(f"[BLOCKED] duplicate prediction: {sample_id}")
            return 2
        by_id[sample_id] = label

    label_ids = {row["sample_id"] for row in labels}
    if set(by_id) != label_ids:
        missing = sorted(label_ids - set(by_id))
        extra = sorted(set(by_id) - label_ids)
        print(f"[BLOCKED] prediction IDs differ: missing={missing[:10]} extra={extra[:10]}")
        return 2

    human = [row["human_label"] for row in labels]
    llm = [by_id[row["sample_id"]] for row in labels]
    kappa = cohen_kappa(human, llm)
    agreement = sum(h == model for h, model in zip(human, llm)) / len(human)
    confusion = Counter(zip(human, llm))
    print(f"n={len(human)} agreement={agreement:.4f} cohen_kappa={kappa:.4f}")
    print(f"confusion={dict(confusion)}")
    if kappa < KAPPA_GATE:
        print(f"[FAIL] kappa gate: {kappa:.4f} < {KAPPA_GATE:.2f}")
        return 1
    print(f"[PASS] kappa gate: {kappa:.4f} >= {KAPPA_GATE:.2f}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--write-template", type=Path)
    parser.add_argument("--check-template", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.write_template:
            write_template(args.write_template)
            return 0
        if not args.labels:
            print("--labels is required unless --write-template is used")
            return 2
        rows = load_jsonl(args.labels)
        errors = validate_template(rows)
        if args.check_template:
            if errors:
                for error in errors:
                    print(f"[FAIL] {error}")
                return 1
            print(f"[OK] template rows={len(rows)} strata={dict(Counter(r['stratum'] for r in rows))}")
            return 0
        if not args.predictions:
            print("--predictions is required when scoring")
            return 2
        return score(args.labels, args.predictions)
    except (OSError, ValueError) as exc:
        print(f"[BLOCKED] {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
