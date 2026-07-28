from __future__ import annotations

import ast
from pathlib import Path

from scripts.build_constitutional_hrm_launch_manifest import ARMS, SEEDS

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_trainer_is_syntax_valid_and_has_required_abort_cleanup_contract() -> None:
    path = REPO_ROOT / "scripts" / "train_constitutional_hrm_200m_v2.py"
    source = path.read_text(encoding="utf-8")
    ast.parse(source)
    for required in (
        "set_per_process_memory_fraction",
        "non_finite_loss",
        "swap_activity",
        "checkpoint_seconds",
        "checkpoint_steps",
        "cuda.empty_cache",
        "cuda.ipc_collect",
        "authorization-receipt",
        "optimizer_launch_authorized",
        "cluster-drill",
    ):
        assert required in source


def test_cluster_runner_maps_exactly_eight_independent_jobs_with_hard_caps() -> None:
    source = (
        REPO_ROOT
        / "scripts"
        / "cluster"
        / "run_constitutional_hrm_200m_v2.sh"
    ).read_text(encoding="utf-8")
    assert len(ARMS) * len(SEEDS) == 8
    for required in (
        "MemoryMax=96G",
        "MemorySwapMax=0",
        "CPUQuota=1200%",
        "IOReadBandwidthMax",
        "IOWriteBandwidthMax",
        "CUDA_VISIBLE_DEVICES",
        "cgroup2fs",
        "remaining_compute_pids",
        "--wait",
        "--pipe",
        "--cluster-drill",
    ):
        assert required in source
    assert "torchrun" not in source
    assert "DistributedDataParallel" not in source
