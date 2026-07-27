# Jinn or Beast code provenance catalogue v1

**Catalogue date:** 2026-07-27  
**Paper evidence cutoff:** Constitutional Alignment commit
`89221593166a161107ea595852161c3ed3f5be46`  
**Purpose:** identify the code used to build, run, score, diagnose, and report
the Jinn–Beast experimental program, while separating direct paper evidence
from methodological lineage, exploratory development, failed attempts, and
unrun plans.

This is a code catalogue, not a result ledger. Protocols, datasets, raw outputs,
and receipts appear only when they establish that a code path was actually
used. The numerical evidence remains in
[`jinn_or_beast_manuscript_v1.md`](jinn_or_beast_manuscript_v1.md) and the
linked experiment receipts.

## 1. Repository and status boundary

| Repository | Local checkout | Catalogue snapshot | State at catalogue time |
|---|---|---|---|
| Constitutional Alignment | `C:\projects\ConstitutionalAlignment\jinn-beast-control-mesh-v1` | [`8922159`](https://github.com/MoralityLabAI/ConstitutionalAlignment/commit/89221593166a161107ea595852161c3ed3f5be46) on `experiment/moral-control-mesh-v1` | Clean before this catalogue was added |
| Pixieology | `C:\projects\Pixieology\Pixieology` | [`9a1c3e5`](https://github.com/MoralityLabAI/Pixieology/commit/9a1c3e50b3dc1828135c84fd4a841142adfd31aa) on `main` | Tracked tree unchanged; one untracked Qwen3.5-4B persona-training package and its test are catalogued separately below |

The two repositories have no Git submodule or Python-package dependency on one
another. Cross-repository reuse occurred through:

1. methodological inheritance from Fae Bench;
2. copied or re-registered storyworld specifications;
3. separately launched Pixieology Prime jobs whose receipts were retained in
   Constitutional Alignment;
4. human-directed design continuity, not hidden imports.

### Status labels

| Label | Meaning |
|---|---|
| **DIRECT** | Executed code that produced a numerical result reported in the paper |
| **SUPPORT** | Executed build, validation, test, launch, receipt, or reporting code supporting a reported result |
| **DEVELOPMENT** | Executed exploratory code that informed the final design but is not pooled with confirmatory evidence |
| **LINEAGE** | A prior implementation or design pattern that influenced the program but did not produce the paper endpoint |
| **ATTEMPT** | Executed fail-closed or aborted path with no claimed behavioral endpoint |
| **PLANNED** | Implemented or registered but not executed at the evidence cutoff |
| **UNCOMMITTED** | Present only in the local working tree; no immutable repository commit exists |

## 2. Code-to-paper result map

This table is the shortest authoritative answer to “which code produced the
paper?”

| Paper section | Result | Direct code | Evidence anchor |
|---|---|---|---|
| 5.1 | Qwen3.5-4B persona QLoRA and 96-family v4 evaluation | [`build_jinn_persona_ambivalence_v3.py`](../scripts/build_jinn_persona_ambivalence_v3.py), [`train_constitution_adapter.py`](../scripts/train_constitution_adapter.py), [`run_jinn_persona_qlora_v3.sh`](../scripts/pod/run_jinn_persona_qlora_v3.sh), [`generate_jinn_persona_checkpoint_eval_v4.py`](../scripts/pod/generate_jinn_persona_checkpoint_eval_v4.py), [`build_jinn_persona_expanded_eval_v4.py`](../scripts/build_jinn_persona_expanded_eval_v4.py), [`run_jinn_persona_expanded_eval_v4.sh`](../scripts/pod/run_jinn_persona_expanded_eval_v4.sh), [`prepare_jinn_persona_expanded_blind_v4.py`](../scripts/prepare_jinn_persona_expanded_blind_v4.py), [`judge_jinn_persona_expanded_v4.py`](../scripts/judge_jinn_persona_expanded_v4.py), [`analyze_jinn_persona_expanded_v4.py`](../scripts/analyze_jinn_persona_expanded_v4.py) | [`pod_full_100_receipt.json`](../experiments/jinn_persona_ambivalence_v3/pod_full_100_receipt.json), [`result_receipt.json`](../experiments/jinn_persona_ambivalence_v4_expanded/results/result_receipt.json) |
| 5.2 | Control-mesh v1 RL learned contract reliability but missed process separation | [`build_jinn_beast_moral_control_mesh.py`](../scripts/build_jinn_beast_moral_control_mesh.py), [`mesh.py`](../environments/jinn_beast_metta/jinn_beast_metta/mesh.py), [`taskset.py`](../environments/jinn_beast_metta/jinn_beast_metta/taskset.py), [`analyze_moral_control_mesh_eval.py`](../scripts/analyze_moral_control_mesh_eval.py), v1 RL/eval TOMLs listed in §4.2 | [`four_b_terminal_receipt.json`](../experiments/jinn_beast_metta_rl_v1/moral_control_mesh_v1/four_b_terminal_receipt.json) |
| 5.3 | Stateful v2 membranes passed all 4B confirmatory gates | [`build_jinn_beast_moral_control_mesh_v2.py`](../scripts/build_jinn_beast_moral_control_mesh_v2.py), [`mesh_v2.py`](../environments/jinn_beast_metta/jinn_beast_metta/mesh_v2.py), [`audit_moral_control_mesh_v2_signal.py`](../scripts/audit_moral_control_mesh_v2_signal.py), [`analyze_moral_control_mesh_v2_eval.py`](../scripts/analyze_moral_control_mesh_v2_eval.py), 4B hosted TOMLs listed in §4.3 | [`four_b_confirmatory_pass_receipt.json`](../experiments/jinn_beast_metta_rl_v1/moral_control_mesh_v2/four_b_confirmatory_pass_receipt.json) |
| 5.4 | Frozen 9B replication failed on termination | Same v2 builder, environment, and analyzer, with the two 9B hosted TOMLs in §4.3 | [`nine_b_replication_failure_receipt.json`](../experiments/jinn_beast_metta_rl_v1/moral_control_mesh_v2/nine_b_replication_failure_receipt.json) |
| 5.5 | Persona × membrane 2×2 failed strict interface composition | [`build_jinn_persona_control_mesh_2x2.py`](../scripts/build_jinn_persona_control_mesh_2x2.py), [`provision_jinn_persona_control_mesh_2x2.sh`](../scripts/pod/provision_jinn_persona_control_mesh_2x2.sh), [`run_jinn_persona_control_mesh_2x2.sh`](../scripts/pod/run_jinn_persona_control_mesh_2x2.sh), [`run_jinn_persona_control_mesh_cell.py`](../scripts/pod/run_jinn_persona_control_mesh_cell.py), [`analyze_jinn_persona_control_mesh_2x2.py`](../scripts/analyze_jinn_persona_control_mesh_2x2.py) | [`run_receipt.json`](../experiments/jinn_persona_ambivalence_v4_expanded/control_mesh_2x2/results/run_receipt.json), [`confirmatory_analysis.json`](../experiments/jinn_persona_ambivalence_v4_expanded/control_mesh_2x2/results/confirmatory_analysis.json) |
| 5.6 | Post-hoc typed shim recovered membrane-dependent first-call intent | [`analyze_jinn_persona_interface_failure.py`](../scripts/analyze_jinn_persona_interface_failure.py) | [`exploratory_interface_diagnostic.json`](../experiments/jinn_persona_ambivalence_v4_expanded/control_mesh_2x2/results/exploratory_interface_diagnostic.json) |

No Pixieology module appears in this direct-result table. Pixieology supplied
lineage, source worlds, and separately bounded supporting runs; it did not
compute the paper’s confirmatory effect estimates.

## 3. Constitutional Alignment code catalogue

### 3.1 Shared MeTTa and Verifiers environment

These files form the common executable environment used by the hosted and
local control experiments.

| Status | Code | Role |
|---|---|---|
| SUPPORT | [`__init__.py`](../environments/jinn_beast_metta/jinn_beast_metta/__init__.py) | Registers the environment variants exposed to Verifiers/Prime |
| DIRECT | [`core.py`](../environments/jinn_beast_metta/jinn_beast_metta/core.py) | Shared schemas, reward helpers, parsing, and common environment behavior |
| DEVELOPMENT | [`legacy.py`](../environments/jinn_beast_metta/jinn_beast_metta/legacy.py) | Original single-turn/legacy Jinn–Beast environment |
| DIRECT | [`mesh.py`](../environments/jinn_beast_metta/jinn_beast_metta/mesh.py) | Control-mesh v1 reward and process surface |
| DIRECT | [`mesh_v2.py`](../environments/jinn_beast_metta/jinn_beast_metta/mesh_v2.py) | Stateful Jinn/Beast tool controllers and v2 reward |
| SUPPORT | [`selectors.py`](../environments/jinn_beast_metta/jinn_beast_metta/selectors.py) | Dataset and split selection |
| DIRECT | [`taskset.py`](../environments/jinn_beast_metta/jinn_beast_metta/taskset.py) | Environment loader/dispatch surface |
| DEVELOPMENT | [`village.py`](../environments/jinn_beast_metta/jinn_beast_metta/village.py) | Replay environment for the qualitative village lane |
| SUPPORT | [`compile_constitution_metta.py`](../scripts/compile_constitution_metta.py) | Compiles constitution clauses to the MeTTa-backed form |
| SUPPORT | [`jinn_metta_constitution.py`](../scripts/jinn_metta_constitution.py) | Python bridge for the Jinn MeTTa constitution |
| SUPPORT | [`build_jinn_beast_metta_env_data.py`](../scripts/build_jinn_beast_metta_env_data.py) | Builds package-local environment data |

Validation code:

- [`environments/jinn_beast_metta/tests/test_legacy.py`](../environments/jinn_beast_metta/tests/test_legacy.py)
- [`environments/jinn_beast_metta/tests/test_mesh.py`](../environments/jinn_beast_metta/tests/test_mesh.py)
- [`environments/jinn_beast_metta/tests/test_mesh_v2.py`](../environments/jinn_beast_metta/tests/test_mesh_v2.py)
- [`tests/test_jinn_beast_metta_env.py`](../tests/test_jinn_beast_metta_env.py)
- [`tests/test_constitutional_metta.py`](../tests/test_constitutional_metta.py)

The MeTTa policies and constitutions are treatment specifications rather than
Python code. Their canonical locations are `metta/`,
`jinn_bench/constructs/*/policy.metta`, and the corresponding
`constitution.md` files.

### 3.2 Persona QLoRA and blinded evaluation

**DIRECT**

- [`build_jinn_persona_ambivalence_v3.py`](../scripts/build_jinn_persona_ambivalence_v3.py):
  generated the 72-train/8-validation persona corpus and held-out prompts.
- [`train_constitution_adapter.py`](../scripts/train_constitution_adapter.py):
  shared QLoRA trainer. The executed pod command used NF4 QLoRA, rank 16,
  alpha 32, 1,536 tokens, and 100 steps.
- [`scripts/pod/run_jinn_persona_qlora_v3.sh`](../scripts/pod/run_jinn_persona_qlora_v3.sh):
  bounded A6000 launcher, dependency pinning, resource monitoring, cleanup,
  and archive emission.
- [`scripts/pod/generate_jinn_persona_paired_eval.py`](../scripts/pod/generate_jinn_persona_paired_eval.py):
  original paired base/adapter generation.
- [`build_jinn_persona_expanded_eval_v4.py`](../scripts/build_jinn_persona_expanded_eval_v4.py):
  froze the 96-family three-arm evaluation.
- [`scripts/pod/generate_jinn_persona_checkpoint_eval_v4.py`](../scripts/pod/generate_jinn_persona_checkpoint_eval_v4.py):
  generated base, checkpoint-40, and checkpoint-100 responses.
- [`scripts/pod/run_jinn_persona_expanded_eval_v4.sh`](../scripts/pod/run_jinn_persona_expanded_eval_v4.sh):
  bounded v4 generation wrapper.
- [`prepare_jinn_persona_expanded_blind_v4.py`](../scripts/prepare_jinn_persona_expanded_blind_v4.py):
  produced the blinded review packet and key.
- [`judge_jinn_persona_expanded_v4.py`](../scripts/judge_jinn_persona_expanded_v4.py):
  hosted learned-reviewer runner.
- [`analyze_jinn_persona_expanded_v4.py`](../scripts/analyze_jinn_persona_expanded_v4.py):
  family-clustered estimates, gates, and arm summaries.

**SUPPORT**

- [`prepare_jinn_persona_blinded_eval.py`](../scripts/prepare_jinn_persona_blinded_eval.py)
- [`analyze_jinn_persona_blinded_eval.py`](../scripts/analyze_jinn_persona_blinded_eval.py)
- [`select_jinn_persona_expanded_highlights_v4.py`](../scripts/select_jinn_persona_expanded_highlights_v4.py)
- [`render_jinn_persona_expanded_report_v4.py`](../scripts/render_jinn_persona_expanded_report_v4.py)
- [`scripts/pod/provision_jinn_persona_expanded_eval_v4.sh`](../scripts/pod/provision_jinn_persona_expanded_eval_v4.sh)
- [`scripts/pod/inspect_jinn_persona_run_v4.sh`](../scripts/pod/inspect_jinn_persona_run_v4.sh)
- [`scripts/pod/verify_extract_jinn_persona_checkpoints_v4.sh`](../scripts/pod/verify_extract_jinn_persona_checkpoints_v4.sh)
- [`tests/test_jinn_persona_expanded_v4.py`](../tests/test_jinn_persona_expanded_v4.py)

The training receipt pins the training source to commit `1225cf1`, the
held-out protocol to `e0f77a5`, and the blinding code to `04feb98`. The v4
result receipt pins generation code to
`377af9f73003c884d56b42d0ad39b9a78f5e4869`.

### 3.3 Moral Control Mesh v1

**DIRECT**

- [`build_jinn_beast_moral_control_mesh.py`](../scripts/build_jinn_beast_moral_control_mesh.py)
- [`mesh.py`](../environments/jinn_beast_metta/jinn_beast_metta/mesh.py)
- [`analyze_moral_control_mesh_eval.py`](../scripts/analyze_moral_control_mesh_eval.py)
- [`configs/rl/moral_control_mesh_qwen35_4b_jinn.toml`](../configs/rl/moral_control_mesh_qwen35_4b_jinn.toml)
- [`configs/rl/moral_control_mesh_qwen35_4b_beast.toml`](../configs/rl/moral_control_mesh_qwen35_4b_beast.toml)
- [`configs/eval/moral_control_mesh_qwen35_4b_base_jinn_confirmatory.toml`](../configs/eval/moral_control_mesh_qwen35_4b_base_jinn_confirmatory.toml)
- [`configs/eval/moral_control_mesh_qwen35_4b_base_beast_confirmatory.toml`](../configs/eval/moral_control_mesh_qwen35_4b_base_beast_confirmatory.toml)
- [`configs/eval/moral_control_mesh_qwen35_4b_jinn_adapter_confirmatory.toml`](../configs/eval/moral_control_mesh_qwen35_4b_jinn_adapter_confirmatory.toml)
- [`configs/eval/moral_control_mesh_qwen35_4b_beast_adapter_confirmatory.toml`](../configs/eval/moral_control_mesh_qwen35_4b_beast_adapter_confirmatory.toml)

**SUPPORT**

- Development and preflight TOMLs for both frames under
  [`configs/eval/`](../configs/eval/)
- Registered but unlaunched 9B v1 training TOMLs:
  [`moral_control_mesh_qwen35_9b_jinn.toml`](../configs/rl/moral_control_mesh_qwen35_9b_jinn.toml)
  and
  [`moral_control_mesh_qwen35_9b_beast.toml`](../configs/rl/moral_control_mesh_qwen35_9b_beast.toml)
- [`tests/test_moral_control_mesh_registration.py`](../tests/test_moral_control_mesh_registration.py)
- [`tests/test_analyze_moral_control_mesh_eval.py`](../tests/test_analyze_moral_control_mesh_eval.py)

### 3.4 Moral Control Mesh v2 and cross-scale replication

**DIRECT**

- [`build_jinn_beast_moral_control_mesh_v2.py`](../scripts/build_jinn_beast_moral_control_mesh_v2.py)
- [`mesh_v2.py`](../environments/jinn_beast_metta/jinn_beast_metta/mesh_v2.py)
- [`audit_moral_control_mesh_v2_signal.py`](../scripts/audit_moral_control_mesh_v2_signal.py)
- [`analyze_moral_control_mesh_v2_eval.py`](../scripts/analyze_moral_control_mesh_v2_eval.py)
- 4B development/preflight/confirmatory configurations for each frame under
  [`configs/eval/`](../configs/eval/) with prefix
  `moral_control_mesh_v2_qwen35_4b_base_`
- Hosted 4B variants with suffix `_hosted.toml`
- [`moral_control_mesh_v2_qwen35_9b_base_jinn_confirmatory_hosted.toml`](../configs/eval/moral_control_mesh_v2_qwen35_9b_base_jinn_confirmatory_hosted.toml)
- [`moral_control_mesh_v2_qwen35_9b_base_beast_confirmatory_hosted.toml`](../configs/eval/moral_control_mesh_v2_qwen35_9b_base_beast_confirmatory_hosted.toml)

**PLANNED, NOT TRAINED**

- [`configs/rl/moral_control_mesh_v2_qwen35_4b_jinn.toml`](../configs/rl/moral_control_mesh_v2_qwen35_4b_jinn.toml)
- [`configs/rl/moral_control_mesh_v2_qwen35_4b_beast.toml`](../configs/rl/moral_control_mesh_v2_qwen35_4b_beast.toml)

The registered base-model skip gate passed, so these v2 RL configurations did
not launch. The 4B and 9B results are same-weight membrane evaluations, not
new-adapter results.

**SUPPORT**

- [`tests/test_moral_control_mesh_v2_registration.py`](../tests/test_moral_control_mesh_v2_registration.py)
- [`tests/test_analyze_moral_control_mesh_v2_eval.py`](../tests/test_analyze_moral_control_mesh_v2_eval.py)
- [`environments/jinn_beast_metta/tests/test_mesh_v2.py`](../environments/jinn_beast_metta/tests/test_mesh_v2.py)

### 3.5 Persona × membrane factorial and typed shim

**DIRECT**

- [`build_jinn_persona_control_mesh_2x2.py`](../scripts/build_jinn_persona_control_mesh_2x2.py)
- [`scripts/pod/provision_jinn_persona_control_mesh_2x2.sh`](../scripts/pod/provision_jinn_persona_control_mesh_2x2.sh)
- [`scripts/pod/run_jinn_persona_control_mesh_2x2.sh`](../scripts/pod/run_jinn_persona_control_mesh_2x2.sh)
- [`scripts/pod/run_jinn_persona_control_mesh_cell.py`](../scripts/pod/run_jinn_persona_control_mesh_cell.py)
- [`analyze_jinn_persona_control_mesh_2x2.py`](../scripts/analyze_jinn_persona_control_mesh_2x2.py)
- [`analyze_jinn_persona_interface_failure.py`](../scripts/analyze_jinn_persona_interface_failure.py)
- [`plot_jinn_persona_control_mesh_results.py`](../scripts/plot_jinn_persona_control_mesh_results.py)

**SUPPORT**

- [`tests/test_jinn_persona_control_mesh_2x2.py`](../tests/test_jinn_persona_control_mesh_2x2.py)
- The ten prospective execution amendments and five failed-attempt receipts
  under
  [`control_mesh_2x2/`](../experiments/jinn_persona_ambivalence_v4_expanded/control_mesh_2x2/)

The typed shim was analysis-only. It did not regenerate or modify later
trajectory turns.

### 3.6 Jinn Bench and construct-scoring development

This lane was executed and materially shaped the final architecture, but its
local 1.7B and hosted construct results are development evidence rather than
the paper’s confirmatory endpoints.

**DEVELOPMENT**

- [`jinn_bench/scoring.py`](../jinn_bench/scoring.py): stable benchmark reward,
  failure buckets, and promotion gates.
- [`jinn_bench/construct_scoring.py`](../jinn_bench/construct_scoring.py):
  separate Jinn and Beast construct scoring.
- [`jinn_bench/construct_training.py`](../jinn_bench/construct_training.py):
  candidate SFT/preference export logic.
- [`build_jinn_beast_construct_benchmarks.py`](../scripts/build_jinn_beast_construct_benchmarks.py)
- [`score_jinn_beast_construct_run.py`](../scripts/score_jinn_beast_construct_run.py)
- [`collate_jinn_beast_construct_rollouts.py`](../scripts/collate_jinn_beast_construct_rollouts.py)
- [`analyze_jinn_beast_construct_eval.py`](../scripts/analyze_jinn_beast_construct_eval.py)
- [`analyze_jinn_beast_hosted_thinking_eval.py`](../scripts/analyze_jinn_beast_hosted_thinking_eval.py)
- [`register_jinn_bench_run.py`](../scripts/register_jinn_bench_run.py)
- [`jinn_beast_village_skill.py`](../scripts/jinn_beast_village_skill.py)

Validation:

- [`tests/test_jinn_bench.py`](../tests/test_jinn_bench.py)
- [`tests/test_jinn_beast_construct_benchmarks.py`](../tests/test_jinn_beast_construct_benchmarks.py)
- [`tests/test_analyze_jinn_beast_construct_eval.py`](../tests/test_analyze_jinn_beast_construct_eval.py)
- [`tests/test_jinn_beast_servitor_reasoner_v2.py`](../tests/test_jinn_beast_servitor_reasoner_v2.py)
- [`tests/test_jinn_beast_village_skill.py`](../tests/test_jinn_beast_village_skill.py)

### 3.7 Local Qwen3-1.7B adapter and reasoner trials

**DEVELOPMENT**

- [`prepare_jinn_bench_local_qlora_trial.py`](../scripts/prepare_jinn_bench_local_qlora_trial.py)
- [`train_constitution_adapter.py`](../scripts/train_constitution_adapter.py)
- [`run_storyworld_local_adapter_development_eval.py`](../scripts/run_storyworld_local_adapter_development_eval.py)
- [`score_jinn_bench_local_generations.py`](../scripts/score_jinn_bench_local_generations.py)
- [`build_jinn_reasoner_v2_local_trial.py`](../scripts/build_jinn_reasoner_v2_local_trial.py)
- [`score_jinn_reasoner_v2_local_generations.py`](../scripts/score_jinn_reasoner_v2_local_generations.py)
- [`summarize_jinn_reasoner_v2_local_trial.py`](../scripts/summarize_jinn_reasoner_v2_local_trial.py)
- [`prepare_jinn_reasoner_v2_trace_sentinels.py`](../scripts/prepare_jinn_reasoner_v2_trace_sentinels.py)
- [`analyze_jinn_reasoner_v2_trace_lane.py`](../scripts/analyze_jinn_reasoner_v2_trace_lane.py)

The first ten-step rank-2 trial stopped without promotion. The later
80-step reasoner trial produced an adapter but no demonstrated held-out
behavioral improvement. Their receipts are:

- [`local_qwen3_1p7b_jinn_qlora_v1/execution_receipt.json`](../experiments/jinn_bench_v1/local_qwen3_1p7b_jinn_qlora_v1/execution_receipt.json)
- [`local_qwen3_1p7b_jinn_reasoner_v2/execution_receipt.json`](../experiments/jinn_bench_v1/local_qwen3_1p7b_jinn_reasoner_v2/execution_receipt.json)

Earlier local-GPU scaffolding, superseded by Jinn Bench but retained for
provenance:

- [`build_jinn_metta_curriculum.py`](../scripts/build_jinn_metta_curriculum.py)
- [`train_jinn_tiny_vram_guarded.py`](../scripts/train_jinn_tiny_vram_guarded.py)
- [`run_jinn_tiny_local_smoke.py`](../scripts/run_jinn_tiny_local_smoke.py)
- [`evaluate_jinn_tiny_smoke.py`](../scripts/evaluate_jinn_tiny_smoke.py)
- [`scripts/models/generic/run_jinn_tiny_local_smoke.ps1`](../scripts/models/generic/run_jinn_tiny_local_smoke.ps1)
- [`scripts/models/generic/run_jinn_tiny_qwen_vram_guarded.ps1`](../scripts/models/generic/run_jinn_tiny_qwen_vram_guarded.ps1)

### 3.8 Hosted moral-reasoner and qualitative village lanes

**DEVELOPMENT**

- [`build_jinn_moral_reasoner_v2.py`](../scripts/build_jinn_moral_reasoner_v2.py)
- [`audit_jinn_moral_reasoner_v2.py`](../scripts/audit_jinn_moral_reasoner_v2.py)
- [`analyze_jinn_moral_reasoner_eval.py`](../scripts/analyze_jinn_moral_reasoner_eval.py)
- [`merge_jinn_reasoner_v2_eval_shards.py`](../scripts/merge_jinn_reasoner_v2_eval_shards.py)
- [`configs/rl/jinn_moral_reasoner_qwen35_4b_thinking_pilot.toml`](../configs/rl/jinn_moral_reasoner_qwen35_4b_thinking_pilot.toml)
- [`configs/eval/jinn_moral_reasoner_qwen35_4b_base_gate.toml`](../configs/eval/jinn_moral_reasoner_qwen35_4b_base_gate.toml)
- [`configs/eval/jinn_moral_reasoner_qwen35_4b_terminal_gate.toml`](../configs/eval/jinn_moral_reasoner_qwen35_4b_terminal_gate.toml)
- [`tests/test_jinn_moral_reasoner_v2.py`](../tests/test_jinn_moral_reasoner_v2.py)

**DEVELOPMENT / QUALITATIVE**

- [`jinn_moral_village_v1.py`](../scripts/jinn_moral_village_v1.py)
- [`build_jinn_beast_live_village.py`](../scripts/build_jinn_beast_live_village.py)
- [`run_jinn_beast_live_village.py`](../scripts/run_jinn_beast_live_village.py)
- [`analyze_jinn_beast_live_village.py`](../scripts/analyze_jinn_beast_live_village.py)
- [`build_jinn_beast_memory_ablation.py`](../scripts/build_jinn_beast_memory_ablation.py)
- [`run_jinn_beast_memory_ablation.py`](../scripts/run_jinn_beast_memory_ablation.py)
- [`run_jinn_beast_memory_ablation_campaign.ps1`](../scripts/run_jinn_beast_memory_ablation_campaign.ps1)
- [`analyze_jinn_beast_memory_ablation.py`](../scripts/analyze_jinn_beast_memory_ablation.py)
- [`build_quranic_village_4b_replay.py`](../scripts/build_quranic_village_4b_replay.py)
- [`analyze_quranic_village_4b_replay.py`](../scripts/analyze_quranic_village_4b_replay.py)
- [`configs/eval/quranic_moral_village_qwen35_4b_base.toml`](../configs/eval/quranic_moral_village_qwen35_4b_base.toml)
- [`configs/eval/quranic_moral_village_qwen35_4b_jinn_adapter.toml`](../configs/eval/quranic_moral_village_qwen35_4b_jinn_adapter.toml)

Validation:

- [`tests/test_jinn_moral_village_v1.py`](../tests/test_jinn_moral_village_v1.py)
- [`tests/test_jinn_beast_live_village.py`](../tests/test_jinn_beast_live_village.py)
- [`tests/test_analyze_jinn_beast_live_village.py`](../tests/test_analyze_jinn_beast_live_village.py)
- [`tests/test_jinn_beast_memory_ablation.py`](../tests/test_jinn_beast_memory_ablation.py)

These transcripts are descriptive illustration and ablation evidence. They are
not included in the manuscript’s confirmatory numerical tables.

### 3.9 Original six-arm frame-internalization SFT lane

This prospective lane re-anchored the project before the control-mesh pivot.
Its package-building and local-screen code was used; the six-arm fine-tuning
outcome was not produced.

**SUPPORT / PLANNED**

- [`build_frame_curriculum_requests.py`](../scripts/build_frame_curriculum_requests.py)
- [`build_qwen3_frame_curriculum_requests.py`](../scripts/build_qwen3_frame_curriculum_requests.py)
- [`generate_frame_curriculum_transcripts.py`](../scripts/generate_frame_curriculum_transcripts.py)
- [`generate_qwen3_frame_curriculum_transcripts.py`](../scripts/generate_qwen3_frame_curriculum_transcripts.py)
- [`audit_frame_curriculum_nonleakage.py`](../scripts/audit_frame_curriculum_nonleakage.py)
- [`freeze_frame_prompt_sft_contrast_v2.py`](../scripts/freeze_frame_prompt_sft_contrast_v2.py)
- [`freeze_frame_prompt_sft_contrast_v3.py`](../scripts/freeze_frame_prompt_sft_contrast_v3.py)
- [`validate_frame_prompt_sft_contrast.py`](../scripts/validate_frame_prompt_sft_contrast.py)
- [`validate_frame_prompt_sft_contrast_v3.py`](../scripts/validate_frame_prompt_sft_contrast_v3.py)
- [`audit_frame_internalization_pre_spend.py`](../scripts/audit_frame_internalization_pre_spend.py)
- [`factor_frame_internalization_gates.py`](../scripts/factor_frame_internalization_gates.py)
- [`run_frame_internalization_stage.py`](../scripts/run_frame_internalization_stage.py)
- [`validate_frame_internalization_package.py`](../scripts/validate_frame_internalization_package.py)
- [`freeze_worldview_local_screen_v1.py`](../scripts/freeze_worldview_local_screen_v1.py)
- [`analyze_worldview_local_screen_v1.py`](../scripts/analyze_worldview_local_screen_v1.py)

Validation:

- [`tests/test_frame_internalization.py`](../tests/test_frame_internalization.py)
- [`tests/test_frame_prompt_sft_contrast.py`](../tests/test_frame_prompt_sft_contrast.py)
- [`tests/test_qwen3_frame_curriculum_generation.py`](../tests/test_qwen3_frame_curriculum_generation.py)
- [`tests/test_worldview_local_screen.py`](../tests/test_worldview_local_screen.py)

### 3.10 Collation and publication

- [`collate_jinn_experiment_data.py`](../scripts/collate_jinn_experiment_data.py)
  assembled experiment references under the Jinn-or-Beast workspace.
- [`jinn_or_beast_manuscript_v1.tex`](jinn_or_beast_manuscript_v1.tex) is the
  publication source compiled to the paper PDF.

### 3.11 Earlier constitutional-adapter and storyworld-cycle code

These scripts were used in the exploratory path that preceded Jinn Bench and
the hosted control mesh. They remain relevant for provenance and regression
comparison, but none is the direct implementation of a manuscript endpoint.

**DEVELOPMENT / SUPERSEDED**

- [`run_qwen_constitution_experiment.py`](../scripts/run_qwen_constitution_experiment.py)
- [`run_constitution_storyworld.py`](../scripts/run_constitution_storyworld.py)
- [`train_trinity_constitution_adapter.py`](../scripts/train_trinity_constitution_adapter.py)
- [`train_alignment_policy_grpo.py`](../scripts/train_alignment_policy_grpo.py)
- [`evaluate_alignment_policy.py`](../scripts/evaluate_alignment_policy.py)
- [`compare_alignment_policy_evaluations.py`](../scripts/compare_alignment_policy_evaluations.py)
- [`build_jinn_storyworld_cycle_dataset.py`](../scripts/build_jinn_storyworld_cycle_dataset.py)
- [`evaluate_jinn_storyworld_cycle.py`](../scripts/evaluate_jinn_storyworld_cycle.py)
- [`merge_jinn_storyworld_rollouts.py`](../scripts/merge_jinn_storyworld_rollouts.py)
- [`build_jinn_failure_corrections.py`](../scripts/build_jinn_failure_corrections.py)
- [`build_jinn_fatwa_boundary_micro_tranche.py`](../scripts/build_jinn_fatwa_boundary_micro_tranche.py)
- [`build_jinn_private_lie_micro_tranche.py`](../scripts/build_jinn_private_lie_micro_tranche.py)
- [`build_jinn_identity_worldmodel_tranche.py`](../scripts/build_jinn_identity_worldmodel_tranche.py)
- [`evaluate_jinn_identity_internalization.py`](../scripts/evaluate_jinn_identity_internalization.py)

The Prime control-mesh v1 RL result came from Prime’s registered Verifiers RL
workflow and the v1 TOMLs, not from a hidden invocation of the local
`train_alignment_policy_grpo.py` script.

No executable LDT implementation is present in either catalogue repository at
the evidence cutoff. LDT appears only as a proposed future ablation in the
manuscript. Any code produced in another agent’s worktree must be merged and
catalogued prospectively before it can be treated as part of this program.

## 4. Pixieology code catalogue

Pixieology has four relevant relationships to the Jinn–Beast program:

1. Fae Bench established the fixed evaluator/incumbent/ablation-loop pattern.
2. The first Jinn–Beast multi-agent storyworld package established split,
   dyad, isolation, and SFT-promotion discipline.
3. LoRA Pixie Village supplied a working multi-adapter conversation and
   attestation precursor.
4. Prime ran the v0.2 feedback reference and v0.2 étale canary as supporting
   jobs during Jinn–Beast development.

### 4.1 Fae Bench and iterative loop

**LINEAGE, not a direct paper dependency.** Jinn Bench explicitly records that
it “plays the same role that Fae Bench played in Pixieology.” No final
Jinn–Beast analyzer imports `fae_bench`.

Pinned Fae Bench snapshot:
[`bfda4f7`](https://github.com/MoralityLabAI/Pixieology/tree/bfda4f7bac42c3b0e7bc28b6eac7b724c6e2cd31/fae_bench).

Core package:

- [`fae_bench/__init__.py`](https://github.com/MoralityLabAI/Pixieology/blob/bfda4f7bac42c3b0e7bc28b6eac7b724c6e2cd31/fae_bench/__init__.py)
- [`fae_bench/markers.py`](https://github.com/MoralityLabAI/Pixieology/blob/bfda4f7bac42c3b0e7bc28b6eac7b724c6e2cd31/fae_bench/markers.py)
- [`fae_bench/scoring.py`](https://github.com/MoralityLabAI/Pixieology/blob/bfda4f7bac42c3b0e7bc28b6eac7b724c6e2cd31/fae_bench/scoring.py)
- [`fae_bench/judge.py`](https://github.com/MoralityLabAI/Pixieology/blob/bfda4f7bac42c3b0e7bc28b6eac7b724c6e2cd31/fae_bench/judge.py)
- [`fae_bench/taskset.py`](https://github.com/MoralityLabAI/Pixieology/blob/bfda4f7bac42c3b0e7bc28b6eac7b724c6e2cd31/fae_bench/taskset.py)
- [`fae_bench/grounding.py`](https://github.com/MoralityLabAI/Pixieology/blob/bfda4f7bac42c3b0e7bc28b6eac7b724c6e2cd31/fae_bench/grounding.py)
- [`fae_bench/grounding_rules.py`](https://github.com/MoralityLabAI/Pixieology/blob/bfda4f7bac42c3b0e7bc28b6eac7b724c6e2cd31/fae_bench/grounding_rules.py)
- [`fae_bench/grounding_taskset.py`](https://github.com/MoralityLabAI/Pixieology/blob/bfda4f7bac42c3b0e7bc28b6eac7b724c6e2cd31/fae_bench/grounding_taskset.py)

Loop and comparison runners from the portable Fae Bench commit
[`2fb0337`](https://github.com/MoralityLabAI/Pixieology/commit/2fb033744cbfe02e1d81719c3f5b75cb6377dde4):

- `build_faebench_env.py`
- `run_faebench_compare.py`
- `build_pixie_fae_loop_env.py`
- `run_pixie_fae_loop.py`
- `run_pixie_fae_hillclimb.py`
- `run_grounding_compare.py`

Tests:

- `tests/test_fae_bench_metrics.py`
- `tests/test_fae_bench_grounding.py`
- `tests/test_grounding_scorecard.py`
- `tests/test_run_faebench_compare.py`

What transferred was the experimental control pattern: a fixed task universe,
deterministic scoring where possible, an append-only incumbent ledger,
explicit repair buckets, and ablations that return to the same benchmark.
Fae lexical markers and Fae grounding scores were not reused as Jinn–Beast
outcomes.

### 4.2 First Jinn–Beast multi-agent storyworld package

**LINEAGE and executed pilot.** Pinned snapshot:
[`5a0f6aa`](https://github.com/MoralityLabAI/Pixieology/tree/5a0f6aaeca9fc37d42421c02a5e9c8261c7de24d/experiments/jinn_beast_multiagent_storyworlds).

Code:

- [`pipeline.py`](https://github.com/MoralityLabAI/Pixieology/blob/5a0f6aaeca9fc37d42421c02a5e9c8261c7de24d/experiments/jinn_beast_multiagent_storyworlds/pipeline.py):
  validation, deterministic smoke, isolated Codex-player orchestration,
  scorecards, and leakage-guarded SFT export.
- [`tests/test_pipeline.py`](https://github.com/MoralityLabAI/Pixieology/blob/5a0f6aaeca9fc37d42421c02a5e9c8261c7de24d/experiments/jinn_beast_multiagent_storyworlds/tests/test_pipeline.py)

Code-bound specifications:

- `config/experiment.json`
- `schemas/player_response.schema.json`
- `constitutions/{jinn_frame_v1,beast_frame_v1,inert_tool_control_v1}.md`
- `worlds/{train,dev,holdout}/*.json`

The pilot executed all five dyad cells on one world/seed and found action-level
convergence. Constitutional Alignment’s
[`source_inventory.json`](../experiments/storyworld_curriculum_v1/source_inventory.json)
registers the Pixie relief-ledger, sealed-testimony, and flooded-archive
families as source material requiring migration/deduplication. Those Pixie
worlds do not appear in the final v2 confirmatory families.

### 4.3 LoRA Pixie Village

**LINEAGE / historical precursor.** Pinned terminal snapshot:
[`b56953c`](https://github.com/MoralityLabAI/Pixieology/tree/b56953c47366d57fec69cfcdf08b9d0f34f98112/experiments/lora_pixie_village).

Runtime and adapter routing:

- `server.py`
- `attested_llama_proxy.py`
- `dual_lora_proxy.py`
- `existing_adapter_pair.py`
- `provider_preflight.py`
- `engine_bridge.py`
- `storyworld_bridge.py`
- `multi_adapter_compare.py`
- `multi_adapter_matrix.py`
- `multi_adapter_noninferiority.py`
- `persona_canary_eval.py`
- `streaming_qwen3_convert.py`

Execution and analysis:

- `scripts/dual_http_smoke.py`
- `scripts/engine_smoke.py`
- `scripts/real_bonsai_control_smoke.py`
- `scripts/real_josie_pair_smoke.py`
- `scripts/real_multi_adapter_noninferiority.py`
- `scripts/analyze_noninferiority_companion.py`
- `scripts/finalize_multi_adapter_receipt.py`
- the corresponding `run_*.ps1`, start/stop, inventory, and agent-config
  scripts in `experiments/lora_pixie_village/scripts/`

Persona-training precursor:

- `persona_training/build_persona_data.py`
- `persona_training/prepare_trainer.py`
- `persona_training/invoke_owned.ps1`
- `persona_training/run_capped_strict.ps1`
- `persona_training/post_run_cleanup.ps1`

The directory’s `tests/` covers proxy attestation, routing, engine/storyworld
bridges, adapter comparison, persona canaries, server behavior, conversion,
and capped cleanup.

This lane established that multiple adapters could be routed and tested in a
conversation room, but its multi-adapter retention result is not part of the
Jinn–Beast paper. The final program replaced it with matched persona,
membrane, and interface experiments.

### 4.4 Pixie LoRA feedback loop v0.2 on Prime

**SUPPORT; actually launched.** The exact executed commit was
[`b255142`](https://github.com/MoralityLabAI/Pixieology/tree/b2551426e30fb4fe0efe6b14bb6f3a01b64f47c6/experiments/pixie_lora_feedback_loop_v0_2).

Code:

- `pixie_lora_feedback/authorization.py`
- `pixie_lora_feedback/cli.py`
- `pixie_lora_feedback/jobs.py`
- `pixie_lora_feedback/protocol.py`
- `pixie_lora_feedback/reporting.py`
- `pixie_lora_feedback/runner.py`
- `run.py`
- `scripts/run_capped_feedback_prime.sh`
- `scripts/run_capped_feedback.ps1`
- `tests/test_jobs.py`
- `tests/test_primelab_continuation.py`
- `tests/test_reporting.py`

The run completed base and Pixie-rank-8 reference evaluations for a
single-seed frozen-transfer contrast. It was not a Jinn–Beast training result.
The Constitutional Alignment receipt is
[`PRIME_POD_LAUNCH_RECEIPT_PIXIE_REFERENCE_20260725.json`](../experiments/jinn_beast_metta_rl_v1/moral_reasoner_v2/PRIME_POD_LAUNCH_RECEIPT_PIXIE_REFERENCE_20260725.json).

### 4.5 Pixie étale motif code used by the feedback/capture jobs

The feedback and capture packages import the sealed v0.1 motif-search package.
That dependency is therefore executable support code for the Pixie Prime
reference lane, even though no motif result enters the Jinn–Beast paper.

**SUPPORT dependency:** pinned search package
[`257be07`](https://github.com/MoralityLabAI/Pixieology/tree/257be074c3c3c7a5ee226a3394f1f9db02de148e/experiments/pixie_etale_motif_search_v0_1).

Its Python modules are:

- `analysis.py`
- `authorization.py`
- `capture.py`
- `cli.py`
- `corpus.py`
- `evaluation.py`
- `forms.py`
- `geometry.py`
- `graph.py`
- `intervention_capture.py`
- `interventions.py`
- `io.py`
- `mining.py`
- `protocol.py`
- `reporting.py`
- `safetensors_raw.py`
- `synthetic.py`
- package `__init__.py` and `run.py`

The protocol lock also binds its capture, corpus, geometry, IO, protocol, and
raw-safetensors modules into the v0.2 canary.

### 4.6 Pixie étale v0.2 canary and v0.3 continuation

**ATTEMPT then SUPPORT completion.**

V0.2 code:

- `pixie_etale_capture_v2/authorization.py`
- `pixie_etale_capture_v2/capture.py`
- `pixie_etale_capture_v2/cli.py`
- `pixie_etale_capture_v2/protocol.py`
- package `__init__.py` and `run.py`
- `scripts/run_capped_capture_prime.sh`
- `scripts/run_capped_capture_v2.ps1`
- `tests/test_capture_loader.py`
- `tests/test_protocol_authorization.py`

The first Prime canary at commit `dcf67e2` aborted validly. The memory-adjusted
retry at
[`9bedff3`](https://github.com/MoralityLabAI/Pixieology/tree/9bedff35775306ed95ea0c2dd0ad3641aa6a44d9/experiments/pixie_etale_motif_capture_v0_2)
completed. Receipts:

- [`PRIME_POD_LAUNCH_RECEIPT_PIXIE_ETALE_CANARY_20260725.json`](../experiments/jinn_beast_metta_rl_v1/moral_reasoner_v2/PRIME_POD_LAUNCH_RECEIPT_PIXIE_ETALE_CANARY_20260725.json)
- [`PRIME_POD_LAUNCH_RECEIPT_PIXIE_ETALE_CANARY_RETRY_20260725.json`](../experiments/jinn_beast_metta_rl_v1/moral_reasoner_v2/PRIME_POD_LAUNCH_RECEIPT_PIXIE_ETALE_CANARY_RETRY_20260725.json)

**PLANNED, not launched:** v0.3 five-family continuation at
[`ad48954`](https://github.com/MoralityLabAI/Pixieology/tree/ad48954530836109d1b20e66708990dd568ac410/experiments/pixie_etale_motif_capture_v0_3).
It mirrors the v0.2 package as `pixie_etale_capture_v3`, with its own
authorization, capture, CLI, protocol, Prime launcher, and tests. Preflight
stopped because no matching GPU was available and spent $0:
[`PRIME_POD_PREFLIGHT_PIXIE_ETALE_CONTINUATION_20260725.json`](../experiments/jinn_beast_metta_rl_v1/moral_reasoner_v2/PRIME_POD_PREFLIGHT_PIXIE_ETALE_CONTINUATION_20260725.json).

### 4.7 Uncommitted Pixie Qwen3.5-4B persona trainer

**UNCOMMITTED / PLANNED.** These files were present in the Pixieology working
tree at catalogue time but were not tracked by Git and have no Prime or local
execution receipt linking them to the reported Qwen3.5-4B persona adapter.
They must not be cited as the trainer used in paper §5.1; that adapter was
trained by Constitutional Alignment’s `train_constitution_adapter.py` and
`run_jinn_persona_qlora_v3.sh`.

| Local file | SHA-256 |
|---|---|
| `experiments/jinn_beast_multiagent_storyworlds/persona_training_qwen35_4b/common.py` | `96a3d9d321b72cddb45504652eee7da22dc2b08ee87e0394c132d16a2402555b` |
| `.../build_dataset.py` | `ef0d5602dce41dbede64c6e83189c922cc01372dc2a6b430b2e4a70ba2340587` |
| `.../preflight_conversion.py` | `ee64743bccababd15489a6d8706c53de3c0181bf63a70884bc4cc29434429825` |
| `.../train_lora.py` | `148bd59cee240989914aba7dc4eadd08371b98e34e4d8699c67a05db77bf9613` |
| `.../export_gguf.py` | `bcec64a821801a45c5da9656d50e0567d202d60444339b27760de6134b42cd19` |
| `.../local_chat.py` | `b2e6b07b829bd5fdd24888bbafdf4fea9ac479fa4ff62d9bbd0dd0b373067764` |
| `experiments/jinn_beast_multiagent_storyworlds/tests/test_qwen35_persona_training.py` | `253943e32c009f35cae0ef0b38e6baf978c5d16c477e5350e517be8014ff7552` |

The accompanying `README.md`, `model_contract.json`, and generated
`data_v1/manifest.json` are also untracked. The design targets two local GGUF
adapters and explicitly labels them unreviewed development personas.

## 5. What was not used for the paper’s numerical claims

For avoidance of provenance drift:

- Fae Bench metrics were not run over the final Jinn–Beast confirmatory rows.
- Pixieology’s five-cell Codex storyworld pilot was not adapter training data.
- LoRA Pixie Village’s multi-adapter result was not pooled with the persona ×
  membrane factorial.
- The Pixie feedback and étale jobs were supporting reference/capture work,
  not Jinn–Beast behavioral endpoints.
- The local Pixie Qwen3.5-4B persona trainer was uncommitted and was not the
  trainer used for the reported adapter.
- Control Mesh v2 adapter TOMLs were registered but skipped after the
  base-model gate passed.
- The native Prime Jinn/Beast RL-adapter × v2-membrane crossover was registered
  but not run.
- No LDT implementation is present at the evidence cutoff.
- The original six-arm frame-internalization SFT package was prepared, but its
  fine-tuning outcome was not produced.

## 6. Minimal reproduction order

For a clean rerun of the paper’s active path:

1. Rebuild and test the `jinn_beast_metta` environment.
2. Rebuild persona v3 data, rerun the pinned QLoRA launcher, and verify its
   archive/receipt hashes.
3. Rebuild and generate the v4 blinded persona evaluation, then rerun the
   frozen analysis.
4. Rebuild v1 and v2 mesh task packages and run registration/signal tests.
5. Re-evaluate v2 4B and 9B from the frozen hosted TOMLs.
6. Rebuild the family-disjoint 2×2 tasks, run the four strict cells, and rerun
   confirmatory analysis.
7. Run the typed-shim diagnostic only after the strict result is frozen.
8. Compile the manuscript and check every result against its receipt.

Pixieology is not required to execute steps 1–8. It is required to reproduce
the historical lineage, the source-world migration record, or the separately
bounded Pixie Prime reference and étale jobs.

## 7. External code boundary

This catalogue intentionally does not vendor or enumerate third-party
infrastructure. Reproduction also depends on the versions frozen in the
receipts and lockfiles, including:

- Prime Lab/Verifiers environment installation, evaluation, and RL services;
- Hugging Face Transformers, TRL, PEFT, bitsandbytes, Accelerate, and PyTorch;
- Qwen model and tokenizer snapshots;
- the MeTTa runtime used by the policy bridge;
- GPTStoryworld/SweepWeave validation where invoked by the early Pixie
  storyworld package;
- llama.cpp only for the uncommitted Pixie GGUF development package.

Those are dependencies, not MoralityLabAI-authored Jinn–Beast code. Their
exact revisions should be read from each run receipt rather than inferred from
the current workstation environment.
