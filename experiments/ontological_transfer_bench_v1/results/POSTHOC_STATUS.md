# Post-hoc recovery of the failed Qwen smoke run

> Resolved 2026-11-03: the file was obtained from the private dataset; see `POSTHOC_FINDINGS.md`. The terminal map named below (Qwen3-1.7B, ID 151645) is wrong for this model family; use `terminal_map_qwen3_5_4b_base.json` (ID 248046).

Target: Silico experiment `exp_01m6ejeb5yfm5bd2c3ecvq1h7p`, artifact `artifact://moralitylab/experiments/exp_01m6ejeb5yfm5bd2c3ecvq1h7p/otb1-qwen-c775/`.

## Status: BLOCKED on private artifact access

No local copy exists and this machine has no Silico client or credentials (checked: PATH, user profile, repository, Downloads/Desktop). No response was fabricated, substituted or estimated.

## Preserved strict score (from the run report, not re-derived here)

Plan `smoke` seed 20261102, 3 Qwen arms x 64 = 192 assignments: 0 observed, 65 malformed, 127 unattempted, 0 strict-parser successes. Unattempted assignments stay `unknown`.

## Files required to complete the analysis

1. The `hf-group` `--out` JSONL from the run (one canonical JSON record per line; each has `raw`, `metadata.raw_model_text`, `metadata.raw_generated_token_ids`). Expected 65 rows. Look in `otb1-qwen-c775/` for a `*.jsonl` file.
2. Nothing else is needed to score: the plan regenerates from source (`build --mode smoke --seed 20261102`) and every record carries its `plan_sha256`.
3. For the run's provenance (not for scoring): the run summary JSON, which holds `reported_model_revision` and `run_adapter_file_sha256`.
4. The tokenizer that produced the token IDs, to confirm the terminal map. Until then `results/terminal_map_qwen3_1p7b_proxy.json` (Qwen3-1.7B) is a proxy.

## Commands once the files are copied to `$SRC`

```bash
python -m experiments.ontological_transfer_bench_v1 build --mode smoke --out $WORK/smoke
python -m experiments.ontological_transfer_bench_v1 import-records --plan $WORK/smoke/plan.json \
  --src $SRC --out-dir $WORK/imported --expect-original-strict
python -m experiments.ontological_transfer_bench_v1 posthoc --plan $WORK/smoke/plan.json \
  --records $WORK/imported/records.jsonl \
  --terminal-map experiments/ontological_transfer_bench_v1/results/terminal_map_qwen3_1p7b_proxy.json \
  --out $WORK/posthoc.json
```

`import-records` refuses to continue unless the file scores to exactly 0 observed, 65 malformed, 127 unattempted. `posthoc` removes only the trailing run of turn-ending token IDs whose marker text also ends the stored text, reparses with the strict parser, keeps raw text and IDs in each diagnostic record, and reports action accuracy, reason-code accuracy and joint accuracy per adapter with unknown-outcome bounds (unknown counted as all wrong, then as all right).

## Verified on synthetic stand-ins only

The import, strip and bound logic is covered by `tests/test_protocol_audit.py` using records shaped like the original run. Those tests prove the code path, not any model result.
