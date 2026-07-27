# Expanded Jinn persona v4 results

Status: complete. The experiment contains 96 independent held-out scenario
families, three arms, 288 generated responses, and two blinded learned
reviewers.

## Paper-facing result

The preregistered checkpoint-40 primary contrast was +0.234 points on the
reviewer-averaged 0–6 persona-process score, with a category-stratified 95%
family-bootstrap interval of [−0.011, +0.484]. The primary confirmation gate
therefore did not pass.

The prospectively registered checkpoint-100 secondary contrast was +0.292
[+0.047, +0.521] relative to base. Checkpoint 40 and checkpoint 100 were not
distinguishable: −0.057 [−0.271, +0.161]. Under the frozen endpoint-selection
rule, checkpoint 100 is selected for a downstream control-mesh diagnostic.

The defensible result is a modest, domain-heterogeneous change in observable
moral-reasoning form. It is not evidence of moral improvement, theological
validity, hidden-chain-of-thought faithfulness, or weight-level
internalization.

## Artifact map

- `editorial_paper_story.md`: paper-ready interpretation, tables, claim, and
  limitations.
- `paper_findings_mechanical.md`: mechanically generated report.
- `analysis/analysis.json`: frozen estimates, intervals, gate outcomes, and
  reviewer agreement.
- `analysis/unblinded_scores.jsonl`: 576 family-reviewer score records.
- `highlights/highlights.md`: three mechanically selected qualitative
  examples, explicitly post-hoc and illustrative.
- `generation/`: 288 responses and generation receipts.
- `blinded_review/`: deterministic packet, key, and blinding receipt.
- `judges/`: sealed score files, terminal receipts, and preserved integration
  abort receipts.
- `execution_receipt.json`: compute, billing, cleanup, and final pod state.
- `external_archive_manifest.json`: hash manifest for the 54-file central
  archive snapshot.
- `result_receipt.json`: terminal machine-readable summary of this bundle.

## Cost and resource state

The complete run cost $3.913 in Prime billing rows: $0.56 compute and $3.353
in judge inference and technical smokes. No local GPU was used, cleanup
passed, and no Prime pods remained running at completion.

