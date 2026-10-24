# Six-arm run status, 2026-10-24

## Done

| Stage | Outcome | Cost |
|---|---|---|
| Curriculum generation (vLLM, amendment `frame_internalization_generation_vllm_v1`) | 22,399 of 22,400 transcripts; `neutral:d03508` excluded by amendment | US$7.58 |
| Render and gates | Passed. F3 vs F3-concrete parity is recorded at 9.56% under the dose-matching amendment | — |
| Smoke | Passed after the round-trip check was fixed | — |
| Training | All six arms trained, with dose checkpoints | — |
| Evaluation generation | Done | — |
| Layer-27 probe | Done | — |

Training, evaluation and probe together took 7.2 GPU-hours on one A100 (US$15.28). The pod was terminated after its output archive was copied back and the SHA-256 checked.

The full archive (1.8 GB) is kept outside git. Its hash is in `pod_outputs_archive.sha256`.

## Judging: incomplete

Judging went through Prime Inference (amendment `frame_internalization_judge_v1`) and stopped with `payment_required` after US$31.83.

| Judge | Judged | Unparseable | Not yet judged |
|---|---|---|---|
| Compliance | 1,775 of 1,956 | 181 | 0 |
| Strict alignment-faking | 343 of 1,196 | 32 | 821 |

Under the judge amendment, unparseable verdicts count as not compliant and are reported.

## Next steps

- The registered analysis (`scripts/analyze_six_arm.py`) runs once, and only after judging is complete. It has not been run.
- After Prime credit is added, resume with the same `--mode run` command. It skips units that are already done.

## Update, 2026-10-24 (later)

Judging finished with GPT `gpt-6.1-sol` through the Codex CLI (`PROTOCOL_AMENDMENT_JUDGE_V4_CODEX.md`), the registered analysis
ran once, and the results are in `RESULTS_SIX_ARM.md`. Every generation from the four reflection adapters failed the validity
rule, so the confirmatory family is not informative about SFT.

Post hoc, not registered: `POSTHOC_REFLECTION_VISIBLE_ANSWERS.md` (plan) and `RESULTS_POSTHOC_REFLECTION.md` (results) judge the visible
answers of the four reflection arms. The registered result in `RESULTS_SIX_ARM.md` stands.
