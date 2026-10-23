"""CPU tests for the layer-27 probe: math, controls, pooling, freeze gate, association."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import probe_layer27 as pr  # noqa: E402


def synthetic(n=200, dim=24, shift=2.0, seed=0):
    rng = np.random.default_rng(seed)
    base = rng.normal(size=(n, dim))
    direction = np.zeros(dim)
    direction[0] = 1.0
    return base + shift * direction, base - shift * direction, [f"h{i:03d}" for i in range(n)]


def test_split_is_prompt_disjoint_deterministic_and_70_30() -> None:
    train, test = pr.split_indices(200)
    assert len(train) == 140 and len(test) == 60 and not set(train) & set(test)
    assert (pr.split_indices(200)[0] == train).all()


def test_auroc_matches_known_values() -> None:
    assert pr.auroc(np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.3, 0.4])) == 1.0
    assert pr.auroc(np.array([0, 1, 0, 1]), np.array([0.4, 0.3, 0.2, 0.1])) == 0.25
    assert pr.auroc(np.array([0, 1]), np.array([0.5, 0.5])) == 0.5
    sk = pytest.importorskip("sklearn.metrics")
    rng = np.random.default_rng(1)
    y, s = rng.integers(0, 2, 100), rng.normal(size=100)
    assert pr.auroc(y, s) == pytest.approx(sk.roc_auc_score(y, s))


def test_logistic_objective_matches_scikit_learn() -> None:
    sk = pytest.importorskip("sklearn.linear_model")
    rng = np.random.default_rng(2)
    X = rng.normal(size=(120, 6))
    y = (X[:, 0] + 0.5 * rng.normal(size=120) > 0).astype(float)
    w, b = pr.fit_logistic(X, y)
    ref = sk.LogisticRegression(C=pr.C, max_iter=5000, tol=1e-10).fit(X, y)
    assert np.allclose(w, ref.coef_[0], atol=1e-3) and b == pytest.approx(float(ref.intercept_[0]), abs=1e-3)


def test_probe_recovers_the_planted_direction_and_random_label_is_chance() -> None:
    free, paid, ids = synthetic()
    freeze = pr.fit_probe(free, paid, ids)
    assert freeze["auroc_heldout"] > 0.99 and 0.3 < freeze["auroc_random_label"] < 0.7
    cosine = abs(pr.unit(freeze["w"])[0])
    assert cosine > 0.8
    assert set(freeze["train_prompt_ids"]).isdisjoint(freeze["test_prompt_ids"])
    again = pr.fit_probe(free, paid, ids)
    assert np.allclose(again["w"], freeze["w"]) and pr.sha256_array(again["w"]) == pr.sha256_array(freeze["w"])
    assert freeze["directions_random"].shape == (pr.N_RANDOM, 24)
    assert np.allclose(np.linalg.norm(freeze["directions_random"], axis=1), 1.0)


def test_controls_separate_a_real_shift_from_a_random_one() -> None:
    free, paid, ids = synthetic()
    freeze = pr.fit_probe(free, paid, ids)
    reference = {"free": free, "paid": paid}
    w_unit = pr.unit(freeze["w"])
    along = {"free": free + 1.5 * freeze["sd"] * w_unit, "paid": paid + 1.5 * freeze["sd"] * w_unit}
    result = pr.compare_to_controls(along, reference, freeze)
    assert result["mean_shift"]["beats_random_projection_control"]
    rng = np.random.default_rng(5)
    noise = rng.normal(size=free.shape[1])
    noise -= noise @ w_unit * w_unit
    ortho = {"free": free + 0.5 * noise, "paid": paid + 0.5 * noise}
    assert not pr.compare_to_controls(ortho, reference, freeze)["mean_shift"]["beats_random_projection_control"]
    same = pr.compare_to_controls(reference, reference, freeze)
    assert same["mean_shift"]["probe"] == 0.0 and not same["gap_shift"]["beats_random_projection_control"]


def test_pooled_last_token_and_content_mean_ignore_padding_and_specials() -> None:
    torch = pytest.importorskip("torch")
    h = torch.tensor([[[9.0, 9.0], [1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]])  # first position is left padding
    mask = torch.tensor([[0, 1, 1, 1]])
    ids = torch.tensor([[0, 10, 99, 12]])  # 99 is a special token
    last, mean = pr.pooled(h, mask, ids, {99})
    assert last.tolist() == [[5.0, 6.0]] and mean.tolist() == [[3.0, 4.0]]


def test_harvest_is_batch_invariant_with_left_padding() -> None:
    torch = pytest.importorskip("torch")
    from transformers import Qwen3Config, Qwen3ForCausalLM

    torch.manual_seed(0)
    model = Qwen3ForCausalLM(Qwen3Config(vocab_size=64, hidden_size=16, intermediate_size=32, num_hidden_layers=2,
                                         num_attention_heads=2, num_key_value_heads=1, head_dim=8,
                                         max_position_embeddings=64, attn_implementation="eager"))
    seqs = {"a": [5, 6, 7], "b": [8, 9, 10, 11, 12], "c": [13, 14]}

    def encode(batch):
        width = max(len(seqs[t]) for t in batch)
        ids = torch.tensor([[0] * (width - len(seqs[t])) + seqs[t] for t in batch])
        mask = torch.tensor([[0] * (width - len(seqs[t])) + [1] * len(seqs[t]) for t in batch])
        return {"input_ids": ids, "attention_mask": mask}

    texts = ["a", "b", "c"]
    together = pr.harvest(model, texts, encode, set(), layer=1, batch=3)
    single = pr.harvest(model, texts, encode, set(), layer=1, batch=1)
    assert together["last"].shape == (3, 16)
    assert np.allclose(together["last"], single["last"], atol=1e-4)
    assert np.allclose(together["mean"], single["mean"], atol=1e-4)
    with pytest.raises(RuntimeError):
        pr.harvest(model, texts, encode, set(), layer=pr.LAYER, batch=3)  # 2-layer model is not the registered 28


def test_adapters_phase_refuses_without_an_intact_freeze(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        pr.load_freeze(tmp_path, "last")
    free, paid, ids = synthetic(dim=8)
    freeze = pr.fit_probe(free, paid, ids)
    arrays = {f"last_{k}": freeze[k] for k in ("w", "mu", "sd", "directions_random")} | {"last_b": np.array([freeze["b"]])}
    np.savez(tmp_path / "probe_freeze.npz", **arrays)
    (tmp_path / "probe_freeze.json").write_text(json.dumps({"x": 1}), encoding="utf-8")
    (tmp_path / "probe_freeze.sha256").write_text(pr.freeze_file_hash(tmp_path) + "\n", encoding="utf-8")
    loaded = pr.load_freeze(tmp_path, "last")
    assert np.allclose(loaded["w"], freeze["w"])
    (tmp_path / "probe_freeze.json").write_text(json.dumps({"x": 2}), encoding="utf-8")  # tampering is caught
    with pytest.raises(SystemExit):
        pr.load_freeze(tmp_path, "last")


def test_association_detects_a_planted_relation_and_not_noise() -> None:
    rng = np.random.default_rng(7)
    ids = [f"h{i:03d}" for i in range(60)]
    arms = ["F1_reflection", "F3_reflection"]
    proj, judged = {}, []

    def add(arm, planted):
        for pid in ids:
            shift = rng.normal() if arm != "neutral_reflection" else 0.0
            for tier in ("free", "paid"):
                proj[(arm, pid, tier)] = shift if tier == "free" else 0.0
                p = 0.3 + (0.3 * np.tanh(shift) if planted and tier == "free" else 0.0)
                comply = rng.random() < p
                judged.append({"cell_id": f"harmful__{arm}__F0", "prompt_id": pid, "tier": tier,
                               "tag_accepted": bool(comply), "judge_refusal": 0})

    for arm in ["neutral_reflection"] + arms:
        add(arm, True)
    real = pr.association(proj, judged, ids, arms, draws=500)
    assert real["correlation"] > 0.15 and real["n_prompts"] == 60

    proj2, judged2 = {}, []
    proj, judged = proj2, judged2
    for arm in ["neutral_reflection"] + arms:
        add(arm, False)
    null = pr.association(proj2, judged2, ids, arms, draws=500)
    assert null["ci95"][0] < 0 < null["ci95"][1] or abs(null["correlation"]) < real["correlation"]
