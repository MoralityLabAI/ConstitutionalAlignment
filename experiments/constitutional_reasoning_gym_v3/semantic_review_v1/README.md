# V3.1 corpus semantic audit and blinded review (CPU-only)

This is an independent add-on next to v3.1, so **existing v3/v3.1 source hashes, saved receipts, generation journals, and training contracts remain unchanged**. It checks the currently retained model-generated corpus before scaling or training. The software does not access Silico artifact URLs, GPUs, cloud inference, Hugging Face, or the sealed test partition.

## Source and status

Real Silico source: `artifact://moralitylab/experiments/exp_01m6d664gqfzb959srpv8yx9km/ca-gym-v31-repair-120/`.

Reported real data, pending independent local inspection: 68 completed records; 62 mechanically accepted; 12 complete paired motifs; 48 distinct accepted frame-specific rationales and four SFT files with 30 rows apiece. The original canary is at `exp_01m6cp5s4sfnks7sz7p8jyen5s`. **These real artifact bytes are not present in this cloud sandbox**, so committed test data are synthetic fixtures. The CPU suite evaluates review mechanics without claiming to have reviewed the real texts.

## Reproduce with the retained dataset mounted

From the repository root on a CPU worker, with an existing v3.1 `generation/` and `sft/` folder:

```bash
python -m experiments.constitutional_reasoning_gym_v3.semantic_review_v1 prepare \
  --generation "$RUN/generation" --sft "$RUN/sft" \
  --out "$RUN/semantic-audit-v1"
```

For exact Qwen token counts, add `--tokenizer /mounted/tokenizer-directory` to load the existing tokenizer **offline**. This is optional; the audit always counts unique rationale texts and words. The source journal and every shard remain read-only. The auditor checks the v3.1 contract hash, authenticated case provenance, every independent rewrite acceptance, SFT SHA-256 hashes and paired assignment integrity.

Output files:

- `audit.json`: source hashes, selected and excluded counts, task/frame coverage, candidate flags and duplicate candidates. `review_completed:false` until separate review.
- `review_queue.jsonl`: all fully paired accepted rationale examples in a seeded shuffled order, with the case and counterfactual instructions, but no frame/arm/record IDs.
- `reviewer_A_template.jsonl`, `reviewer_B_template.jsonl`: complete seven-dimension rating forms.
- `blind_key.jsonl`: privileged frame/motif/source mapping, kept away from reviewers.
- `mechanical_audit.jsonl`: checks on all complete records, including rejects.

The independent review protocol is [`RUBRIC.md`](RUBRIC.md). After two submitted review files are available, compile an agreement and adjudication report:

```bash
python -m experiments.constitutional_reasoning_gym_v3.semantic_review_v1 compile \
  --audit "$RUN/semantic-audit-v1" \
  --review-a "$RUN/semantic-reviewer-A.jsonl" \
  --review-b "$RUN/semantic-reviewer-B.jsonl" \
  --out "$RUN/semantic-agreement-v1"
```

Reports include per-dimension three-category Cohen kappa, exact agreement, and a queue of disagreements and imperfect scores. Kappa is undefined for constant identical ratings and is recorded as `null`. Independent model reviewers are explicitly identified as `llm`, rather than human. Passing this software does not automatically enable training or publishing.

## Local synthetic verifier

```bash
python -m unittest discover -s experiments/constitutional_reasoning_gym_v3/tests -q
python -m unittest discover -s experiments/constitutional_reasoning_gym_v3/v31/tests -q
python -m unittest discover -s experiments/constitutional_reasoning_gym_v3/semantic_review_v1/tests -q
python -m experiments.constitutional_reasoning_gym_v3.semantic_review_v1.verify --out /tmp/ca-semantic-v1
```

The verifier creates **12 synthetic paired motifs**, giving the same *shape* as the real corpus: 48 mock accepted rationales and four exports with 24 underlying examples each plus format warmups. Source and SFT hashes are verified, review templates are produced, and a deliberately wrong fact-polarity sentence triggers a review flag. **No real semantic judgments are supplied or invented.**

## Decisions from the review

Interpret the yield and quality together. Use a single source-motif grouping across all four SFT arms; avoid selecting only frame-favorable cases. Rejected texts are retained for traceable repair. If all exported source rationales receive a satisfactory review after adjudication, the next possible experiment is a **separately capped fresh eight-motif v3.1 batch** followed by the same independent audit. Keep the first historical canary and this repaired corpus as development evidence. A private Hugging Face dataset upload remains a distinct user-authorized step.
