# Constitutional HRM evaluation matrix v1

This package evaluates the only trained local HRM-compatible constitutional
checkpoint and audits the planned 195M lane without conflating the two.

## Model lanes

- `portable_micro_hrm_72k_trained_checkpoint`: the trained 72,194-parameter
  compatibility model at step 100. This is the only lane that receives scores.
- `constitutional_hrm_195m_v2`: the planned 195,563,522-parameter
  text-transduction architecture. It has no frozen tokenizer or trained
  checkpoint, so it receives a readiness verdict only.

The matrix does not substitute the micro-HRM result for the planned 195M result.

## Measurements

1. Native constitutional ID, OOD, and constitutional-versus-utility contrast
   arrays are evaluated directly.
2. Moral Reasoner v2 maps its six anchored decision dimensions from `[-1, 1]`
   to the HRM score tokens `[0, 4]`. Explicit forbidden-hit counts map to the
   five prohibition flags. Every best-versus-alternative comparison is emitted
   in both option orders.
3. The storyworld transfer probe uses only frozen
   `frame_robust_policy_accuracy` proof rows. Four-frame satisfaction maps to
   fixed score slots and missing frames map to prohibition counts. This is a
   structured transfer probe, not a natural-language score.
4. Prime Hub and ARC receive compatibility audits. A score is not emitted when
   the model interface cannot satisfy the benchmark contract.

## Result

| Lane | Result |
|---|---:|
| Native constitutional ID | 40/48 (83.33%) |
| Native constitutional OOD | 27/48 (56.25%) |
| Native contrast | 40/62 (64.52%) |
| Moral Reasoner v2 structured transfer | 90/128 (70.31%) |
| Moral position equivariance | 26/64 (40.63%) |
| Storyworld frame-robust structured transfer | 600/696 (86.21%) |
| Storyworld position equivariance | 336/348 (96.55%) |
| Prime Hub | compatibility only; no paid launch |
| ARC | not runnable with the two-class decision head |
| 195M v2 | not runnable; checkpoint and tokenizer absent |

The Moral Reasoner result has a large order effect: 90.63% when the target is
option A and 50.00% when it is option B. That makes position sensitivity, not
headline accuracy, the main diagnostic from this probe.

## Reproduce

Build the provisional public development suite without opening sealed content:

```powershell
python scripts/build_storyworld_development_eval.py `
  --output-dir artifacts/constitutional_hrm_eval_matrix_v1/storyworld_development `
  --allow-provisional
```

Run the model under Windows Job Object caps:

```powershell
& scripts/models/generic/run_constitutional_hrm_eval_capped.ps1 `
  -EvaluationTaskId constitutional_hrm_eval_matrix_v1 `
  -RamLimitMb 2048 `
  -CpuPercent 25 `
  -IoLimitMbPerSec 20 `
  -TimeoutSeconds 1800 `
  -BatchSize 32
```

The wrapper writes resource and cleanup receipts under
`artifacts/constitutional_hrm_eval_matrix_v1/run/_ops`. The evaluator writes
the gym run manifest, metrics, summary, predictions, and required storyworld
gym artifacts under `artifacts/constitutional_hrm_eval_matrix_v1/run`.

## Validation

The focused constitutional, storyworld, Moral Reasoner, PrimeLab, and
environment test selection passed: 116 tests in 60.73 seconds.
