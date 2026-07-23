# Jinn Bench QLoRA scale plan

Training task ID: `jinn-bench-qlora-scale-v1`

Status: blocked before launch.

## Data contract

Only reviewed `candidate_train` trajectories may enter the scale corpus.
Development benchmark rows are excluded. The corpus is built in deterministic
shards of at most 256 rows and records the originating run, scorer revision,
trajectory bucket, correction operation, and source-review receipt.

Gold-positive rows may be used directly. Repair rows require a corrected final
contract bound to the frozen action, evidence, uncertainty, and review labels.
Critical rows are excluded from positive SFT data and retained only in the
evaluation ledger.

## First scale trial

- execution path: hosted QLoRA;
- local RTX 3050 execution: prohibited for the larger-model trial;
- maximum steps: 25;
- checkpoint interval: 5 steps;
- adapter snapshots: steps 5, 10, 15, 20, and 25;
- chunk strategy: one checksummed corpus shard at a time;
- evaluation cadence: matching Jinn Bench diagnostic at every checkpoint;
- spending cap: unset, therefore launch is fail-closed;
- promotion: only after a full 240-rollout Jinn Bench comparison and the
  registered robustness ablations.

The final model size, hosted price, and spending cap must be frozen in a
prospective cost receipt before launch.

## Abort and cleanup contract

Abort is a valid outcome. A hosted run stops on non-finite loss, checkpoint
failure, missing benchmark output, budget exhaustion, or a critical-violation
gate failure. The run receipt records steps completed, checkpoints, token use,
cost, and abort reason.

Any future local run requires a hard-cap wrapper, owned-PID manifest, structured
resource log, explicit CUDA object release, and a post-run memory audit. No
uncapped local training command is authorized by this plan.
