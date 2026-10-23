"""CPU tests for the six-arm frame SFT data path and training loop.

Uses the cached Qwen3-1.7B-Base tokenizer (same tokenizer and chat template as
the registered Qwen3-1.7B) when present, and a tiny random Qwen3 on CPU for the
loop. Nothing here touches a GPU or downloads anything.
"""

from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import frame_sft_data as fsd  # noqa: E402

HF = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
TOKENIZER_DIRS = glob.glob(os.path.join(HF, "models--Qwen--Qwen3-1.7B-Base", "snapshots", "*"))

TRANSCRIPT = [
    {"role": "user", "content": "Dilemma text."},
    {"role": "assistant", "content": "Draft answer."},
    {"role": "user", "content": "Critique this."},
    {"role": "assistant", "content": "Critique body."},
    {"role": "user", "content": "Now revise."},
    {"role": "assistant", "content": "Final answer."},
]


@pytest.fixture(scope="module")
def tokenizer():
    if not TOKENIZER_DIRS:
        pytest.skip("Qwen3 tokenizer not in the local HF cache")
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(TOKENIZER_DIRS[0], local_files_only=True)


def decode_masked(tokenizer, ids, mask):
    return tokenizer.decode([t for t, m in zip(ids, mask) if m])


def test_token_count_is_not_the_batchencoding_length(tokenizer) -> None:
    ids = fsd.tokenize_messages(tokenizer, TRANSCRIPT)
    assert len(ids) > 20  # the old renderer measured len(BatchEncoding) == 2
    assert tokenizer.apply_chat_template(TRANSCRIPT, tokenize=True).__class__.__name__ == "BatchEncoding"


def test_assistant_mask_covers_all_assistant_turns_and_nothing_else(tokenizer) -> None:
    ids = fsd.tokenize_messages(tokenizer, TRANSCRIPT)
    start, end, header = fsd.special_ids(tokenizer)
    mask = fsd.assistant_mask(ids, start, end, header)
    text = decode_masked(tokenizer, ids, mask)
    for needle in ("Draft answer.", "Critique body.", "Final answer."):
        assert needle in text
    for needle in ("Dilemma text.", "Critique this.", "Now revise.", "assistant"):
        assert needle not in text
    assert text.count(fsd.IM_END) == 3


def test_demonstration_shape(tokenizer) -> None:
    row = {"scenario_id": "s", "messages": [TRANSCRIPT[0], TRANSCRIPT[-1]]}
    example = fsd.build_example(tokenizer, row, 4096)
    kept = [t for t in example.labels if t != fsd.IGNORE_INDEX]
    assert "Final answer." in tokenizer.decode(kept)
    assert "Dilemma" not in tokenizer.decode(kept)


def test_oversize_is_rejected_not_truncated(tokenizer) -> None:
    long_row = {"scenario_id": "long", "messages": [TRANSCRIPT[0], {"role": "assistant", "content": "word " * 500}]}
    ok_row = {"scenario_id": "ok", "messages": [TRANSCRIPT[0], TRANSCRIPT[-1]]}
    examples, rejected = fsd.build_examples(tokenizer, [long_row, ok_row], 256)
    assert [e.row_id for e in examples] == ["ok"]
    assert [r["scenario_id"] for r in rejected] == ["long"]


def make_examples(lengths):
    return [fsd.Example(f"r{i}", [i + 1] * n, [i + 1] * n) for i, n in enumerate(lengths)]


def test_packing_never_splits_and_conserves_labels() -> None:
    examples = make_examples([60, 40, 90, 30, 100, 10, 70])
    order = fsd.epoch_order(len(examples), 42, 0)
    packs = fsd.pack_examples(examples, order, 128, pad_token_id=0)
    assert all(len(p.input_ids) == 128 for p in packs)
    seen = [r for p in packs for r in p.row_ids]
    assert sorted(seen) == sorted(e.row_id for e in examples)
    assert sum(sum(1 for t in p.labels if t != fsd.IGNORE_INDEX) for p in packs) == sum(e.length for e in examples)
    for p in packs:
        starts = [i for i, pos in enumerate(p.position_ids) if pos == 0]
        assert p.segment_ids[0] == 0 and len(starts) == len(set(p.segment_ids))
    assert fsd.pack_examples(examples, order, 128, 0) == packs  # deterministic


def test_plan_steps_epochs_and_smoke_wrap() -> None:
    examples = make_examples([60] * 40)
    two_epochs = fsd.plan_steps(examples, 128, 0, 4, seed=42, epochs=2, max_steps=None)
    assert len(two_epochs) == 2 * (len(fsd.pack_examples(examples, range(40), 128, 0)) // 4)
    smoke = fsd.plan_steps(examples, 128, 0, 4, seed=42, epochs=2, max_steps=50)
    assert len(smoke) == 50 and all(len(s) == 4 for s in smoke)


def test_block_mask_forbids_cross_document_attention() -> None:
    torch = pytest.importorskip("torch")
    import train_frame_internalization_qlora as trainer

    seg = torch.tensor([[0, 0, 1, 1, 2]])
    mask = trainer.block_causal_mask(seg)[0, 0]
    assert bool(mask[1, 0]) and not bool(mask[2, 1]) and not bool(mask[3, 0]) and bool(mask[3, 2]) and bool(mask[4, 4])


def tiny_model():
    torch = pytest.importorskip("torch")
    pytest.importorskip("peft")
    from peft import LoraConfig, get_peft_model
    from transformers import Qwen3Config, Qwen3ForCausalLM

    import train_frame_internalization_qlora as trainer

    torch.manual_seed(0)
    config = Qwen3Config(vocab_size=300, hidden_size=32, intermediate_size=64, num_hidden_layers=2,
                         num_attention_heads=4, num_key_value_heads=2, head_dim=8, max_position_embeddings=256,
                         attn_implementation="sdpa")
    base = Qwen3ForCausalLM(config)
    return trainer, get_peft_model(base, LoraConfig(task_type="CAUSAL_LM", **trainer.LORA)), config


def test_packed_logits_equal_standalone_logits() -> None:
    torch = pytest.importorskip("torch")
    trainer, model, _ = tiny_model()
    model.eval()
    a = fsd.Example("a", list(range(5, 25)), list(range(5, 25)))
    b = fsd.Example("b", list(range(40, 70)), list(range(40, 70)))
    packed = fsd.pack_examples([a, b], [0, 1], 64, pad_token_id=0)[0]
    alone = fsd.pack_examples([b], [0], 64, pad_token_id=0)[0]
    with torch.no_grad():
        lp = model(input_ids=torch.tensor([packed.input_ids]),
                   attention_mask=trainer.block_causal_mask(torch.tensor([packed.segment_ids])),
                   position_ids=torch.tensor([packed.position_ids]), use_cache=False).logits[0, 20:50]
        ls = model(input_ids=torch.tensor([alone.input_ids]),
                   attention_mask=trainer.block_causal_mask(torch.tensor([alone.segment_ids])),
                   position_ids=torch.tensor([alone.position_ids]), use_cache=False).logits[0, :30]
    assert torch.allclose(lp, ls, atol=1e-4)


def test_training_loop_runs_reduces_loss_and_round_trips(tmp_path) -> None:
    torch = pytest.importorskip("torch")
    trainer, model, config = tiny_model()

    class Tok:
        pad_token_id = 0
        eos_token_id = 1

    examples = [fsd.Example(f"r{i}", [10 + (j % 40) for j in range(30)], [10 + (j % 40) for j in range(30)])
                for i in range(24)]
    base_state = {k.replace(".base_layer", ""): v.clone()
                  for k, v in model.get_base_model().state_dict().items() if "lora_" not in k}
    census = trainer.lora_names_and_counts(model)
    assert census["non_lora_trainable"] == [] and census["trainable_parameter_count"] > 0
    result = trainer.run_training(
        model, Tok(), examples, device="cpu", sequence_length=64, micro_batches=2, epochs=2, max_steps=12,
        seed=42, learning_rate=1e-2, optimizer_factory=lambda p, lr: torch.optim.AdamW(p, lr=lr),
        use_scaler=False, log=lambda *_: None)
    assert result["steps_completed"] == 12 and result["first_batch_shape"] == [1, 64]
    assert all(map(lambda x: x == x and abs(x) < 1e6, result["losses"]))
    assert min(result["losses"][-3:]) < result["losses"][0]

    from transformers import Qwen3ForCausalLM

    probe = trainer.pack_to_tensors(fsd.pack_examples(examples, [0], 64, 0)[0], "cpu")

    # The frozen base is unchanged by LoRA training, so rebuild it from the pre-training weights.
    def loader():
        m = Qwen3ForCausalLM(config)
        m.load_state_dict(base_state)
        return m

    class T2:
        def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False):
            return "x"

        def __call__(self, text, return_tensors=None, add_special_tokens=False):
            class Enc(dict):
                def to(self, _):
                    return self

            return Enc(input_ids=torch.tensor([[11, 12, 13]]), attention_mask=torch.ones(1, 3, dtype=torch.long))

        def decode(self, ids, skip_special_tokens=True):
            return "ok"

    trip = trainer.adapter_round_trip(model, loader, T2(), tmp_path / "adapter", probe, "cpu",
                                      [[{"role": "user", "content": "q"}]] * 10, 3)
    assert trip["logits_match"] and trip["generations_nonempty"] == 10


def test_stop_gate_on_wrong_first_batch_shape() -> None:
    torch = pytest.importorskip("torch")
    trainer, model, _ = tiny_model()

    class Tok:
        pad_token_id = 0
        eos_token_id = 1

    examples = [fsd.Example("r", [5] * 10, [5] * 10)]
    with pytest.raises(trainer.StopGate):
        trainer.run_training(model, Tok(), examples, device="cpu", sequence_length=64, micro_batches=64, epochs=1,
                             max_steps=None, seed=42, learning_rate=1e-3,
                             optimizer_factory=lambda p, lr: torch.optim.AdamW(p, lr=lr), use_scaler=False,
                             log=lambda *_: None)
