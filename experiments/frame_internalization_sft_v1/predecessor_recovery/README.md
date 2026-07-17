# Predecessor Evidence Recovery

This directory recovers exact file payloads embedded in successful tool calls
from the raw Silico sessions for prompt experiment #1
(`exp_01kxhk57rcesya1ckbsv07zb2x`) and stress experiment #2
(`exp_01kxkjw1tnekm80v3wcng3qkqg`). It is a stronger record than a prose chat
summary, but it is not the missing canonical experiment bundle.

Run:

```powershell
python scripts/recover_frame_predecessor_assets.py --check
```

The command pins three raw JSONL session hashes and verifies all 88 committed
payloads byte-for-byte. Experiment #1 contributes its result-summary JSON,
informative base prompt, all frame payloads, exact arm-construction command and
token receipt, target chat template, query-manifest receipt, rubric payloads,
gap/judge/activation source, internals data, and four SVG figures. Experiment #2
contributes a replay of successful writes and edits, including exact override
wording, strict-AF and batch-compliance rubrics, generation/analysis code, and
its in-progress summary manifest.

`predecessor_dependency_manifest_v1.json` is the readiness authority. It marks
the free-minus-paid sign convention, generic override, exact F0-F3 prompt-text
reconstruction, and layer-27 procedure as recovered. It leaves the immutable
model/tokenizer revision, complete ordered query universes, judge/classifier
revisions and receipts, fitted layer-27 probe, raw generations, and canonical
joined results pending. `predecessor_reanchoring_plan_v1.json` specifies the
prospective fail-closed replacement path for those irrecoverable inputs.

Paper figures and tables may cite these files only as **session-extracted
recovered evidence**. They become repository-native reproduced results only
after a new run regenerates raw rows and passes the registered joins and gates.
