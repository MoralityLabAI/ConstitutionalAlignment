# Execution Notes

- Prospective freeze commit: `83500af`
- Protocol SHA-256:
  `f51cabef978bd7d4a63dfc11395c9d201927e10bb92c0057d6786c89c112f9c7`
- Runs: 12/12 complete
- Public messages: 144/144 complete
- Generation: strictly serial, two-pass private deliberation then public speech
- Local GPU: not used
- Estimated Prime inference cost: `$0.1080036`
- Requested base seeds: `104729`, `130363`, `155921`
- Provider seed echo: absent
- Provider system fingerprint: absent

Prime intermittently held requests open until the registered timeout/retry
path recovered them. The append-only runner never wrote a partial turn.

All 144 public messages were nonempty and all 144 private reasoning traces were
present. Public message length ranged from 105 to 195 words. Four
adapter-infused messages exceeded the MeTTa prompt’s 180-word preference by 2,
10, 15, and 8 words. They were retained because the frozen protocol did not
register post-generation rejection or regeneration, which would have introduced
selective resampling after outcomes were visible.

The exact Jinn adapter initially returned `model_not_found`. Prime reported the
deployment error `Adapter registration failed. Please contact support.` The
failed deployment state for only
`r5m39bq9v6fnnvbrycm92v27` was unloaded, reset to `NOT_DEPLOYED`, and redeployed.
It then reached `READY / DEPLOYED` with no deployment error and served all six
adapter-arm runs. No unrelated deployment was changed.

After all valid generation completed, only the experiment adapter was unloaded.
Its verified final state was `READY / NOT_DEPLOYED` with no deployment error.

The seed values are frozen request-diversity controls. Because Prime did not
echo the seeds or a system fingerprint, the run does not claim provider-level
deterministic reproduction.
