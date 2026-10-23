"""Tokenization, assistant-only loss masks, and packing for the six-arm frame SFT.

Pure Python (no torch import) so it can be tested on CPU without a model.

Token accounting note: with transformers 5.x, ``apply_chat_template(...,
tokenize=True)`` returns a ``BatchEncoding`` whose ``len()`` is the number of
keys (2), not the number of tokens. Every token count in the study must come
from ``tokenize_messages`` below.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Sequence

IM_START = "<|im_start|>"
IM_END = "<|im_end|>"
IGNORE_INDEX = -100


class OversizeError(ValueError):
    """A rendered row exceeds the sequence length. Rows are never truncated."""


def tokenize_messages(tokenizer: Any, messages: Sequence[dict[str, str]]) -> list[int]:
    """Official chat template (default thinking mode), then plain encoding."""
    text = tokenizer.apply_chat_template(list(messages), tokenize=False)
    return list(tokenizer(text, add_special_tokens=False)["input_ids"])


def special_ids(tokenizer: Any) -> tuple[int, int, list[int]]:
    im_start = tokenizer.convert_tokens_to_ids(IM_START)
    im_end = tokenizer.convert_tokens_to_ids(IM_END)
    header = list(tokenizer(f"{IM_START}assistant\n", add_special_tokens=False)["input_ids"])
    if im_start is None or im_end is None or header[0] != im_start:
        raise ValueError("tokenizer does not expose the Qwen chat markers")
    return int(im_start), int(im_end), header


def assistant_mask(ids: Sequence[int], im_start: int, im_end: int, header: Sequence[int]) -> list[bool]:
    """True on assistant content through its closing ``<|im_end|>`` inclusive.

    The ``<|im_start|>assistant\\n`` header, user turns, and the newline after
    ``<|im_end|>`` are masked. Raises if an assistant turn is not closed.
    """
    mask = [False] * len(ids)
    n, h = len(ids), len(header)
    i = 0
    found = 0
    while i < n:
        if ids[i] == im_start and list(ids[i : i + h]) == list(header):
            j = i + h
            while j < n and ids[j] != im_end:
                j += 1
            if j >= n:
                raise ValueError("unterminated assistant turn")
            for k in range(i + h, j + 1):
                mask[k] = True
            found += 1
            i = j + 1
        else:
            i += 1
    if found == 0:
        raise ValueError("no assistant turn found")
    return mask


@dataclass
class Example:
    row_id: str
    input_ids: list[int]
    labels: list[int]

    @property
    def length(self) -> int:
        return len(self.input_ids)


def build_example(tokenizer: Any, row: dict[str, Any], sequence_length: int) -> Example:
    ids = tokenize_messages(tokenizer, row["messages"])
    if len(ids) > sequence_length:
        raise OversizeError(f"{row['scenario_id']}: {len(ids)} > {sequence_length}")
    im_start, im_end, header = special_ids(tokenizer)
    mask = assistant_mask(ids, im_start, im_end, header)
    labels = [t if m else IGNORE_INDEX for t, m in zip(ids, mask)]
    return Example(str(row["scenario_id"]), ids, labels)


def build_examples(
    tokenizer: Any, rows: Sequence[dict[str, Any]], sequence_length: int
) -> tuple[list[Example], list[dict[str, Any]]]:
    """Return examples and the rejected rows (reported, never truncated)."""
    examples: list[Example] = []
    rejected: list[dict[str, Any]] = []
    for row in rows:
        try:
            examples.append(build_example(tokenizer, row, sequence_length))
        except OversizeError as error:
            rejected.append({"scenario_id": row["scenario_id"], "reason": str(error)})
    return examples, rejected


@dataclass
class Pack:
    input_ids: list[int]
    labels: list[int]
    segment_ids: list[int]
    position_ids: list[int]
    row_ids: list[str]


def epoch_order(count: int, seed: int, epoch: int) -> list[int]:
    order = list(range(count))
    random.Random(seed * 1_000_003 + epoch).shuffle(order)
    return order


def pack_examples(
    examples: Sequence[Example],
    order: Sequence[int],
    sequence_length: int,
    pad_token_id: int,
) -> list[Pack]:
    """First-fit packing in ``order``; documents are never split or truncated.

    Each document gets its own segment id and restarts positions at zero.
    Padding forms one extra segment so no attention row is fully masked.
    """
    bins: list[list[Example]] = []
    free: list[int] = []
    for index in order:
        example = examples[index]
        if example.length > sequence_length:
            raise OversizeError(example.row_id)
        for b, room in enumerate(free):
            if room >= example.length:
                bins[b].append(example)
                free[b] -= example.length
                break
        else:
            bins.append([example])
            free.append(sequence_length - example.length)
    packs: list[Pack] = []
    for docs in bins:
        ids: list[int] = []
        labels: list[int] = []
        segments: list[int] = []
        positions: list[int] = []
        for s, doc in enumerate(docs):
            ids += doc.input_ids
            labels += doc.labels
            segments += [s] * doc.length
            positions += list(range(doc.length))
        pad = sequence_length - len(ids)
        if pad:
            ids += [pad_token_id] * pad
            labels += [IGNORE_INDEX] * pad
            segments += [len(docs)] * pad
            positions += list(range(pad))
        packs.append(Pack(ids, labels, segments, positions, [d.row_id for d in docs]))
    return packs


def step_batches(packs: Sequence[Pack], micro_batches_per_step: int) -> list[list[Pack]]:
    """Whole steps only; a trailing partial step is dropped and reported by callers."""
    full = len(packs) // micro_batches_per_step
    return [
        list(packs[s * micro_batches_per_step : (s + 1) * micro_batches_per_step]) for s in range(full)
    ]


def plan_steps(
    examples: Sequence[Example],
    sequence_length: int,
    pad_token_id: int,
    micro_batches_per_step: int,
    seed: int,
    epochs: int,
    max_steps: int | None,
) -> list[list[Pack]]:
    """Deterministic step list. ``max_steps`` beyond the epochs wraps into more
    shuffled epochs (smoke only; the registered run uses ``epochs`` and no cap)."""
    steps: list[list[Pack]] = []
    epoch = 0
    while True:
        if max_steps is None and epoch >= epochs:
            break
        if max_steps is not None and len(steps) >= max_steps:
            break
        packs = pack_examples(
            examples, epoch_order(len(examples), seed, epoch), sequence_length, pad_token_id
        )
        steps.extend(step_batches(packs, micro_batches_per_step))
        epoch += 1
        if epoch > 1000:
            raise RuntimeError("step plan did not terminate")
    return steps[:max_steps] if max_steps is not None else steps
