# CA-Gym v3.1 CPU evidence

## Reproduced on the cloud CPU sandbox

The source-hashed `verification.json` reports **108 tests passed**: 65 from the untouched v3.0 suite and 43 new v3.1 tests. Both regression logs are retained here. All results are **synthetic fixture evidence** and no paid GPU job, new Qwen inference, LoRA training or Hub upload was performed.

`adaptive_vs_five_stage.json` compares 32 identical case/frame records. On this intentionally easy deterministic fixture, the five-stage v3.0 generator issues 160 stage calls and accepts every record; v3.1 issues 32 stage calls and accepts every record. This verifies the code path that avoids unnecessary critiques. It is a 5× stage-count difference on the fixture; token cost and GPU throughput remain unmeasured.

`simulated_canary_comparison.json` is a deliberately **fault-injected analogue** of the Silico report. The synthetic v3.0 source has 24 completed records, 17 final acceptances, 7 counterfactual failures, and 3 fully paired motifs. The synthetic v3.1 repair reuses the other responses and fixes seven failed records with seven fresh calls. All 24 records pass, with 6 complete paired motifs. These are not the original Silico outputs.

The two separate v3.1 fixture SFT manifest variants report four arms with natural EOS supervision and identical case/format exposure. `human_semantic_review_required` remains true. Full synthetic raw/journal/JSONL fixtures are reproduced by the workflow and stored in its uploaded GitHub Actions artifact; the compact manifests and test logs are committed here.

## Actual Silico canary boundary

The original dataset remains in Silico's durable storage at `artifact://moralitylab/experiments/exp_01m6cp5s4sfnks7sz7p8jyen5s/ca-gym-v3-synthesis-837/`. This sandbox cannot retrieve that artifact directly. To recover those 24 records and extra unfinished journal calls, mount its original `generation/` directory on a worker and use `--legacy` with v3.1. Recovery must preserve its historical source hashes and original raw responses.
