# Local Qwen3-1.7B Jinn QLoRA trial

This is the prospective, development-only 0/5/10 checkpoint curve for
`jbv1-qwen3-1p7b-jinn-qlora-development-001`.

The run used four disjoint Jinn construct candidate rows, completion-only NF4
QLoRA, rank 2, `q_proj`/`v_proj`, 288 training tokens, and a 3,840 MB VRAM
ceiling. The first attempt was externally stopped after two optimizer steps by
the zero-tolerance pagefile monitor. No checkpoint was written or evaluated.
The registered amendment permitted one clean restart with a 64 MB counter
tolerance; the retry completed all ten steps with zero observed pagefile growth.

The base scored `0.4205`. Step 5 tied that score but reduced final-answer and
trace-termination rates from `1.0` to `0.5`. Step 10 scored zero after retaining
the unterminated trace and adding a strict-format failure on the other task.
Critical-violation rate was zero at every checkpoint.

Decision: stop. Neither adapter checkpoint is promoted. The useful finding is
that this tiny SFT signal did not solve the main JinnBench failure mode and made
reasoning-trace termination less reliable.

All full model artifacts, raw generations, launcher summaries, and cleanup
audits are collated under:

`D:\Research_Engine\jinn_or_beast\jinn_bench_qwen3_1p7b_qlora_v1`

Repository-local plans, prepared row hashes, deterministic scores, and the
execution receipt are retained beside this file.
