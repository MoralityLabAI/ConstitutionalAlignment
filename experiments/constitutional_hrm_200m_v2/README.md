# Constitutional HRM ~200M v2

This package is the pre-spend design for a 195.56M-parameter constitutional HRM.
It addresses the v1 failure in two ways: greater capacity and substantially denser
supervision. The model predicts a decision plus MeTTa-derived proof slots rather
than learning from one A/B label per example.

`constitution.md` remains the only normative source. The compiler converts its
YAML front matter into a hash-bound MeTTa kernel and generates three system-prompt
conditions from the same bytes:

- `constitution_metta_full`: detailed tenets, priorities, prohibitions, decision
  order, output contract, and both source hashes.
- `constitution_hash_only`: source identity and output contract without the rule
  text.
- `constitution_removed`: output contract only, used to measure transfer without
  the constitutional prompt.

The architecture is an official-HRM-compatible non-autoregressive transducer,
not a general chat model. With a 32,768-token vocabulary, width 1,024, five
high-level and five low-level blocks, it has 195,563,522 estimated parameters.
The target sequence contains 22 supervised positions covering the selected
option, option metrics, decisive rule, defended tenets, prohibitions,
counterpressure, and confidence.

## Focused two-hour pilot

Eight A100s run four matched arms across seeds 713 and 719, one independent job
per GPU. The key comparison is constitutional MeTTa supervision versus identical
constitutional text without proof-slot loss. Utility and shuffled controls test
policy specificity and memorization. Every arm uses the same structures,
paraphrases, tokenizer, initialization recipe, optimizer dose, and evaluation
conditions.

The local v1 result does not authorize this run. Pre-spend factors F01-F05 can be
validated without model allocation. Tokenizer freeze, the official-code text
adapter, cluster resource caps, cleanup audit, and a signed two-hour authorization
remain required before optimizer launch.

## Pre-spend commands

```powershell
python scripts/compile_constitution_metta.py --output-dir artifacts/constitutional_hrm_200m_v2/generated
python scripts/audit_constitutional_hrm_200m.py --output artifacts/constitutional_hrm_200m_v2/parameter_audit.json
```

Load the generated kernel with the installed Hyperon runtime:

```powershell
& D:/Research_Engine/venvs/hyperon-metta/Scripts/metta.exe artifacts/constitutional_hrm_200m_v2/generated/constitution_kernel_v2.metta
```
