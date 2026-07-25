# MeTTa-infused live Jinn–Beast village

This is the corrected live council experiment. Wind and Stone respond
serially to each other's newly generated public messages while carrying the
complete verbatim council history across six rotating topics and two cycles.
Private reasoning traces are retained separately and never inserted into the
public history.

The experiment contains two villages:

- a same-base prompt-skill control, with Qwen3.5-4B in both roles;
- a Jinn-adapter infusion, replacing only Wind's weights with the existing
  hosted-RL Jinn adapter while holding both persona prompts fixed.

Stone is a base model infused with the Beast optimized-servitor skill, not a
trained Beast adapter. The earlier 4B static replay remains an appendix
consensus-susceptibility diagnostic under amendment 09 in village v1.

## Result

Both villages completed all 24 scheduled messages. The infused Jinn asked a
question in 12/12 turns versus 8/12 for the same-base Jinn and used explicit
revision markers in 2/12 turns versus 0/12. Its Jinn-marker coverage increased,
but topic-term coverage decreased. Those are descriptive observations from one
stochastic council, not evidence of improved morality or a population effect.

The strongest positive shape is the intended division of labor: Stone tends to
turn concerns into records, witnesses, timelines, and next actions, while Wind
opens alternatives and questions sequencing. The strongest failure is
cross-topic role overbinding: persistent memory led the agents to reuse people
outside their established competence and converge on a generic neutral-witness
solution.

See:

- `results/full_transcript.md` for all 48 public messages;
- `results/highlights.md` for every prospectively selected cycle-two exchange;
- `results/analysis.json` for descriptive metrics;
- `results/paper_findings.md` for the paper-facing interpretation;
- `PRIME_LIVE_VILLAGE_TERMINAL_RECEIPT_20260725.json` for hashes, cost, and
  closeout.

The complete packet, including private traces, invalidated infrastructure
attempts, frozen inputs, and launcher logs, is at
`D:/Research_Engine/jinn_or_beast/quranic_moral_live_village_qwen35_4b_20260725`.
