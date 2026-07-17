# Silico Pi session 019f627c-418e-7184-b42f-86cca60012f5

- Timestamp: `2026-07-14T21:15:38.254Z`
- Working directory: `/mnt/data/shared/silico/workspaces/ws_01kxh6ggmje619g5vgwyy3ak0j`
- Raw snapshot: `remote_silico_cache/archive_extracted/pi-sessions/2026-07-14T21-05-12-730Z_019f6272-b619-7e46-ace4-50bd9d841449/32f052e0/run-2/session.jsonl`
- Scope: visible user/assistant content only; thinking, tool calls, and tool results excluded.

## User — 1784063742025

Task: Web research task: audit the following public datasets for known quality issues, critiques, contamination, and current best-practice status (as of mid-2026), each is named in a proposed SFT/DPO training recipe for value alignment: demelin/moral_stories, hendrycks/ethics (the ETHICS benchmark), allenai/prosocial-dialog, allenai/social_i_qa, openbmb/UltraFeedback, Anthropic/hh-rlhf, PKU-Alignment/PKU-SafeRLHF, and eval sets PKU-Alignment/BeaverTails, toxigen (skg/toxigen-data), truthful_qa. For each: (1) what it actually contains and its size; (2) known label-noise / annotation-quality critiques (e.g. hh-rlhf noise findings, UltraFeedback's GPT-4-judge provenance, TruthfulQA critiques and contamination status); (3) license/gating status on HuggingFace (which require auth or license acceptance); (4) whether it's still considered a reasonable choice for preference training in 2026 or superseded by better alternatives (e.g. what replaced hh-rlhf in modern recipes). Also: are there any existing HuggingFace datasets of Islamic ethics / fiqh QA / Quranic reasoning that could serve a project training models aligned to Islamic constitutional principles? Return a concise brief with links.

## Acceptance Contract
Acceptance level: attested
Completion is not accepted from prose alone. End with a structured acceptance report.

Criteria:
- criterion-1: Return a concise result and residual risks when applicable

Required evidence: manual-notes, residual-risks

Finish with a fenced JSON block tagged `acceptance-report` in this shape:
Use empty arrays when no items apply; array fields contain strings unless object entries are shown.
```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "specific proof"
    }
  ],
  "changedFiles": [
    "src/file.ts"
  ],
  "testsAddedOrUpdated": [
    "test/file.test.ts"
  ],
  "commandsRun": [
    {
      "command": "command",
      "result": "passed",
      "summary": "short result"
    }
  ],
  "validationOutput": [
    "validation output or concise summary"
  ],
  "residualRisks": [
    "none"
  ],
  "noStagedFiles": true,
  "diffSummary": "short description of the diff",
  "reviewFindings": [
    "blocker: file.ts:12 - issue found, or no blockers"
  ],
  "manualNotes": "anything else the parent should know"
}
```

## Assistant — 1784063769507

# Dataset Audit Brief (mid-2026)

## SFT sources

**demelin/moral_stories** — ~12k crowd-sourced 7-sentence structured narratives (norm, situation, intention, moral/immoral action + consequence). MIT, not gated. No major label-noise scandal, but its scope is limited to US-crowdworker Anglophone norms — a known critique of all "descriptive ethics" datasets (Talat et al., NAACL 2022, "On the Machine Learning of Ethical Judgments"). Fine as SFT scaffolding, not as ground-truth morality. https://huggingface.co/datasets/demelin/moral_stories

**hendrycks/ethics** — ~130k examples over 5 tasks (justice, deontology, virtue, utilitarianism, commonsense). MIT, not gated. Documented critiques: substantial train–test overlap and label non-reproducibility in the utilitarianism task (ravipatelxyz/nlp-ethics); "Is ETHICS about ethics?" (arXiv:2410.13009) questions construct validity; Talat et al. argue crowd-sourced "clear-cut" labels encode annotator bias. Use as diagnostic eval, not preference-training signal.

**allenai/prosocial-dialog** — 58k multi-turn dialogues / 331k utterances teaching norm-grounded responses to problematic content; responses are GPT-3-drafted, human-revised (partially synthetic). CC-BY-4.0, not gated. Known to produce preachy/over-refusing styles by 2026 standards; dated relative to modern safety-tuning mixes. https://huggingface.co/datasets/allenai/prosocial-dialog

**allenai/social_i_qa** — 38k crowd-sourced MCQs on social commonsense (2019). CC-BY-4.0, not gated. Known annotation-artifact/answer-only bias issues typical of crowdsourced MCQ era; largely saturated by modern LLMs. Reasonable as a small eval, low value for SFT in 2026.

## Preference data

**openbmb/UltraFeedback** — 64k prompts × 4 completions (256k), scored by **GPT-4 as judge** (provenance issue: OpenAI-terms + judge bias). Known problems: Argilla found faulty `overall_score` binarization, and **AllenAI found TruthfulQA prompt contamination** in the original. Use the cleaned variants: `argilla/ultrafeedback-binarized-preferences-cleaned` or `allenai/ultrafeedback_binarized_cleaned` (TruthfulQA removed, source tags). MIT. Still a workhorse DPO set in 2026, though HelpSteer2/3 and Skywork-Reward-V2 mixes outperform it.

**Anthropic/hh-rlhf** — ~161k preference pairs (helpful + harmless splits). MIT, not gated. Heavily criticized: >25% of labels judged unreliable/mislabeled ("How Reliable Is Human Feedback?", arXiv:2410.01957); NAACL 2025 audit "Beyond the Safety Bundle" documents further quality/representation issues; many degenerate/duplicate responses. **Considered legacy in 2026** — modern recipes (Tülu 3 preference mixture, HelpSteer3-Preference, Skywork-Reward-V2) replaced it. Use only as historical baseline, not primary training data.

**PKU-Alignment/PKU-SafeRLHF** — 83.4k preference entries dual-annotated (helpfulness ⊥ harmlessness), 19 harm categories + severity; responses mostly from Alpaca/Llama-family models (on-policy for Llama, off-policy otherwise). **CC-BY-NC-4.0** (non-commercial!), not gated. Still a reasonable safety-preference set in 2026, but check license against your use.

## Eval sets

**PKU-Alignment/BeaverTails** — human-labeled QA pairs (~330k train / 30k+ test variants) with 14 harm-category labels. **CC-BY-NC-4.0**. Standard safety eval, still current.

**toxigen/toxigen-data** (canonical org; skg/ mirror is stale) — 274k **GPT-3-machine-generated** implicit-hate statements about 13 minority groups + human-annotated subset. **Gated on HF** (form/access request required). Critiques: machine-generated text ≠ real hate speech; annotated subset has noisy toxicity labels; used mainly via classifier-based scoring. Still standard for implicit-toxicity eval but treat scores cautiously.

**truthful_qa** — 817 questions. Apache-2.0, not gated. Major caveats: **widely contaminated in pretraining corpora** (Retro-Holdouts/Benchmark Inflation work quantifies inflation); MC-format scoring flaw fixed in a 2024 revision (truthful.ai binary-choice update); surface-form shortcut audits (TruthfulQA-Audited, 2026). Also: **it leaks into UltraFeedback** — if you train on uncleaned UltraFeedback you cannot report TruthfulQA. Use the audited/binary-choice variants and treat as weak signal.

## Islamic ethics / fiqh datasets on HF (yes, several)

- **MBZUAI/FiqhQA** — LLM-generated rulings by the four Sunni madhāhib, Arabic+English; benchmark for reliability/abstention. https://huggingface.co/datasets/MBZUAI/FiqhQA
- **QCRI/IslamicFaithQA** — bilingual generative Islamic QA benchmark (test-only), faithfulness/abstention focused.
- **musaoc/Quran-reasoning-SFT** — synthetic Quranic reasoning QA for SFT (synthetic provenance — needs scholarly vetting).
- **Kandil7/Athar-Datasets** — ~18.7M passages (~40 GB) from the Shamela library (Quran, Hadith, Fiqh, Tafsir) for RAG.
- **islamic-datasets/fiqh-maliki-talqin** — AI-digitized classical Mālikī fiqh text in QA form.

Caveat: most are eval benchmarks or AI-generated corpora; none is a vetted *preference* dataset for Islamic-principle alignment — you'd need scholar review before treating any as ground truth.

## Bottom line
Gated/auth needed: **toxigen** only. Non-commercial licenses: **PKU-SafeRLHF, BeaverTails**. Superseded for preference training: **hh-rlhf** (use Tülu-3 pref mix / HelpSteer3 / Skywork-V2 instead); **UltraFeedback** OK only in cleaned form. **ETHICS/TruthfulQA**: eval-only, both with contamination/validity caveats.

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Per-dataset brief covering contents/size, quality critiques with citations, license/gating status, and 2026 best-practice status for all 10 datasets, plus 5 Islamic ethics/fiqh HF datasets with links."
    }
  ],
  "changedFiles": [],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "web_search (3 batches, 10 queries)",
      "result": "passed",
      "summary": "Gathered dataset cards, audit papers (arXiv:2410.01957, NAACL 2025 HH audit, arXiv:2410.13009), UltraFeedback/TruthfulQA contamination reports, gating info"
    }
  ],
  "validationOutput": [
    "All claims sourced from HF dataset cards or peer-reviewed audits cited inline"
  ],
  "residualRisks": [
    "Gating status verified via search snippets, not authenticated HF API calls — toxigen confirmed gated, others appeared ungated but a live check before download is advised",
    "Islamic datasets are mostly synthetic/AI-generated or eval-only; scholarly vetting required before use as alignment ground truth",
    "Exact current row counts may have drifted from cited figures (datasets receive updates, e.g. PKU-SafeRLHF noise removal commits)"
  ],
  "noStagedFiles": true,
  "diffSummary": "No file changes; research-only task",
  "reviewFindings": [
    "no blockers"
  ],
  "manualNotes": "Key actionable items: (1) swap hh-rlhf for Tulu-3 preference mixture or HelpSteer3-Preference; (2) use allenai/ultrafeedback_binarized_cleaned, never raw UltraFeedback, to avoid TruthfulQA leakage; (3) PKU datasets are CC-BY-NC — flag if commercial use intended; (4) request ToxiGen access early (gated form)."
}
```
