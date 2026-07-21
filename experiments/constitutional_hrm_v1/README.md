# Constitutional HRM v1

This package tests whether an HRM-style two-timescale recurrent model can learn a
small, structured decision policy derived from `constitution.md`. It is a task
formulation and compatibility gate before spending on the official CUDA trainer.

The local stage is deliberately small: 72,194 parameters by default, CPU-only,
fixed-length categorical inputs, and one A/B decision output. It preserves the
high-level/low-level recurrent structure and the official dataset contract, but it
is not the official 27M configuration and it is not a text generator. A positive
result licenses an official-code pilot; it does not substitute for one.

## Factorized gates

The executable order is:

```text
G1 provenance ----> G2 dataset ----|
       |                            |--> G4 dry run --> G5 local signal
       `-----------> G3 runtime ----|                     |
                                                          v
                                                G6 three seeds
                                                          |
                                                          v
                                                G7 cluster pilot
```

The exact pass conditions and stop rules are frozen in `experiment_plan.json`.
The three matched arms are constitutional, unweighted utility, and shuffled
labels. All receive the same tensors, split groups, initialization, optimizer,
and dose. The contrast slice contains only examples on which the constitutional
and unweighted policies disagree.

## Commands

Validation-only, through the cap wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/models/generic/run_constitutional_hrm_smoke_capped.ps1 -ValidateOnly
```

Local smoke after the dry-run receipt passes:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/models/generic/run_constitutional_hrm_smoke_capped.ps1
```

Generated datasets, checkpoints, event logs, and resource summaries live under
`artifacts/constitutional_hrm_v1/` and are ignored by Git. The launcher writes a
trainer plan before entering the job, hard-caps Windows job memory and CPU, checks
that the trainer inherited the job, aborts after three consecutive I/O-rate
violations, checkpoints by step or time, and only stops the recorded trainer PID
and its descendants during cleanup.

## Measurement boundary

This stage measures acquisition and generalization of a synthetic structured
policy. The test target is constitutional decision accuracy on held-out feature
combinations, with the utility and shuffled arms providing matched controls.
Natural-language behavior, theological adequacy, and the official HRM training
claim remain separate later gates.

## First bounded result

The 2026-07-21 seed-713 smoke completed all 300 optimizer steps and 12
checkpoints. It passed dataset integrity, label balance, constitutional
in-distribution accuracy, and the delta-over-shuffled gate. It stopped at G5
because constitutional contrast accuracy was 0.6452, below the frozen 0.75
threshold. Multi-seed confirmation and cluster spend therefore remain closed.
See `RESULTS_20260721.md` and `run_receipt_20260721.json`.
