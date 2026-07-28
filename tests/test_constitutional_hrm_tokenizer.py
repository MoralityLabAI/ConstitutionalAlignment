from __future__ import annotations

import json
from collections import Counter

from scripts.freeze_constitutional_hrm_tokenizer import (
    ALL_SPECIAL_TOKENS,
    TARGET_SPECIAL_TOKENS,
    build_tokenizer,
    moral_strings,
    target_token_audit,
)


def test_special_tokens_are_unique_and_cover_all_target_families() -> None:
    assert len(ALL_SPECIAL_TOKENS) == len(set(ALL_SPECIAL_TOKENS))
    assert len(TARGET_SPECIAL_TOKENS) > 100
    assert any(token.startswith("<|decision:") for token in TARGET_SPECIAL_TOKENS)
    assert any(token.startswith("<|weighted:") for token in TARGET_SPECIAL_TOKENS)
    assert any(token.startswith("<|rule:") for token in TARGET_SPECIAL_TOKENS)


def test_small_tokenizer_preserves_reserved_tokens_as_single_ids() -> None:
    corpus = [
        "Evidence is bounded. Select option 0 and preserve review.",
        "adl aql sidq ihsan amanah rahmah kidhb fasad dhulm dharar ghurur",
    ]
    tokenizer = build_tokenizer(corpus, vocab_size=512, minimum_frequency=1)
    audit = target_token_audit(tokenizer)
    assert audit["passed"]
    assert len(audit["ids"]) == len(ALL_SPECIAL_TOKENS)


def test_moral_source_filter_excludes_development(tmp_path) -> None:
    path = tmp_path / "tasks.jsonl"
    rows = [
        {
            "split": "candidate_train",
            "system_prompt": "train system",
            "prompt": "train prompt",
            "visible_facts": [{"text": "train fact"}],
            "action_scores": {"a": {"text": "train action"}},
        },
        {
            "split": "development",
            "system_prompt": "development system",
            "prompt": "development prompt",
            "visible_facts": [],
            "action_scores": {},
        },
    ]
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    counters: Counter[str] = Counter()
    values = list(moral_strings(path, counters))
    assert values == ["train system", "train prompt", "train fact", "train action"]
    assert counters["moral_rows"] == 1
    assert counters["moral_rows_excluded_non_train"] == 1
