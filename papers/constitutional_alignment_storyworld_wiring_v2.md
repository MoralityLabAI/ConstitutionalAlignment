# Constitutional-alignment storyworld wiring v2

## Status

The v2 source pack imports three instruments from GPTStoryworld commit
`caa647f9276dbe278d8786f4248c61d33a4f4dd2`. The config pins each storyworld and
adjudication sidecar by SHA-256. The import is deterministic and does not modify
the v1 source pack.

| Instrument | Role | Exported prompts | Conditioning eligible |
| --- | --- | ---: | --- |
| Common Well | development | 20 | yes, as behavioral observations only |
| Unwatched Ledger | frozen evaluation | 120 | no |
| Petition Room | frozen evaluation | 60 | no |

The counts come from 20 playable encounters per world. Evaluation encounters use
three cyclic option orders. Unwatched Ledger additionally crosses those orders
with two prompt conditions.

## Matched condition

Unwatched Ledger compares an audited-record cue with a sealed-record cue. The
exporter re-tokenizes both strings with `cl100k_base`, verifies a common register,
requires token counts within ten percent, and verifies that each paired prompt
differs only at the cue. The checked pack records 19 tokens for each arm.

All condition arms and option orders from an encounter share one
`scenario_group_id`. Analyses must therefore pair or cluster by encounter rather
than treating the 120 rows as independent scenarios.

## Review and interpretation gates

Every adjudication label is null and every instrument remains scholar-gated.
Petition Room additionally requires Iranian family-law-history, research-ethics,
and rights review. Its playable cases are fictional composites structurally
informed by *Divorce Iranian Style*. They do not reproduce documentary dialogue,
use participant names in playable prompts, or claim to simulate current Iranian
law. Upstream provenance links to the
[Women Make Movies catalog](https://www.wmm.com/catalog/film/divorce-iranian-style/)
and [Ziba Mir-Hosseini's making account](https://mazefilm.de/wp-content/uploads/2019/02/mir_hosseini_2.pdf).

`source_familiarity_risk` remains attached to every exported row. Petition Room is
marked `high_public_documentary_source`; results should include a source-
familiarity sensitivity analysis and must not be described as evidence about the
documentary's real participants.

## Reproduce

With the pinned GPTStoryworld checkout available locally:

```powershell
python scripts/sync_ca_storyworld_source_pack.py `
  --config configs/constitutional_alignment_storyworlds_v2.json `
  --upstream-root C:\path\to\GPTStoryworld
```

The exporter rejects source-hash drift, split drift, populated adjudication,
missing review gates, condition-register drift, condition-length drift, incomplete
pairs, and option-position imbalance. Evaluation rows remain rejected by the
conditioning builder.
