# Recovered Silico session material

This private recovery bundle preserves both sides of the surviving record:

- 454 Silico/Pi session JSONLs recovered from the cluster cache, including 141 top-level operator sessions and 313 nested run/agent sessions;
- six local Codex rollout snapshots containing the Silico setup, cluster claim, VPD A100 run, ConstitutionalAlignment handoffs, Gödel-Globe planning, and workspace-loss context.

All 454 remote JSONLs match a SHA-256 manifest computed on the cluster, and all 35,411 JSONL records parse without a malformed or truncated tail.

- `raw_rollout_snapshots/` contains byte snapshots of the original JSONL rollouts at recovery time. These may contain expired claim URLs, hostnames, commands, and other sensitive operational data. Keep them private.
- `readable_chat_exports/` contains user/assistant chat messages only. Ephemeral claim and device tokens are redacted.
- `remote_silico_cache/archive_extracted/pi-sessions/` is the untouched recursive Silico/Pi cache snapshot.
- `remote_silico_cache/top_level_first_scp_141_sessions/` is an independently transferred duplicate of the 141 top-level sessions, retained as recovery redundancy.
- `remote_pi_sessions_readable_all/` mirrors all 454 remote sessions as Markdown while excluding hidden thinking, tool calls, and tool results.
- `remote_pi_sessions_index_all.md` is the searchable entry point for the complete remote recovery.
- `plan_report_session_index.md` narrows the corpus to sessions containing plan/report-shaped headings or artifact-path references.
- `remote_pi_sessions_inventory_all.json` records per-session source paths, counts, hashes, and readable-export hashes.
- `remote_silico_cache/*.sha256` contains the remote archive and per-file verification receipts.
- `experiment_snapshots/kimi-k25-experiment-recovery-20260716/` preserves the timestamped Kimi K2.5 experiment's code, checkpoints, analysis outputs, figures, SLURM logs, store metadata, and git/job provenance. Its independently verified tarball is beside it.
- `inventory.json` records source paths, session IDs, stability observations, record counts, and hashes.
- `checksums.sha256` covers every recovered file except itself.

The live `~/.silico/state/claim.token` and all authentication material were deliberately excluded. The readable exports also receive a best-effort credential-pattern scan, but the raw JSONLs remain private forensic material.

Plans, reports, protocols, audit notes, and handoffs that appeared in a conversation are present. Standalone files are included only when their contents entered the session record; filesystem artifacts that were merely created or referenced require a separate workspace-artifact recovery.

The Kimi K2.5 snapshot is the first such workspace-artifact recovery. The 384-prompt teacher-forced harvest and H1 analysis survived; the final live behavioral/H2 retry did not complete successfully. The approximately 19 GB raw activation capture remains in the cluster's shared artifact store and is not duplicated in this lightweight bundle.

The recovered chats complement, rather than replace, the independently verified experiment artifacts under `D:\Research_Engine\runs\qwen17_planted_reward_full_precision_silico_v1_retry1`. Browser history contained no matching Silico rows, so no browser cache was modified or copied.
