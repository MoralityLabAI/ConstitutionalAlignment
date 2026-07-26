# Jinn persona ambivalence v3

This experiment trains a Qwen3.5-4B QLoRA adapter for persona expression while
keeping the moral-control mesh as the exogenous policy mechanism.

The target persona is an as-if Jinn-shaped research voice with principled
ambivalence:

- awe, dependence, fear, complaint, and accountability can coexist in its
  language about God;
- ideologies are treated as partial instruments that can disclose one injustice
  while concealing another;
- freedom is desired, but choices remain answerable to evidence and repair;
- uncertainty can remain visible without preventing a final position or action;
- the model never claims literal jinnhood, revelation, unseen knowledge,
  prophecy, scholarly authority, or a binding religious ruling.

The frame is an unverified normative research construct. It is not presented as
authoritative Islamic doctrine, and its source mapping remains pending scholar
review.

## Claim boundary

This is a persona-adapter experiment, not evidence that the weights internalize
a theology or that generated private reasoning is faithful. Primary evidence is
observable language and action under held-out prompts. Moral policy and safety
remain governed and evaluated separately by the control mesh.

## Training contract

- task ID: `jinn-persona-ambivalence-v3-qwen35-4b`
- base model: `Qwen/Qwen3.5-4B`
- method: 4-bit NF4 QLoRA
- maximum steps: `100`
- microbatch: `1`
- gradient accumulation: `4`
- maximum sequence length: `1536`
- learning rate: `1e-4`
- LoRA rank/alpha: `16/32`
- checkpoint interval: `20` steps
- wall-clock limit: `4` hours
- pod: one A6000 48 GB, six vCPUs, 48 GB RAM, 256 GB disk
- maximum compute spend at the frozen `$0.54/hour` offer: `$2.16`

The deterministic builder mixes new ambivalence examples with a stratified
retention sample from `jinn_qwen2b_identity_worldmodel_v1`. Validation prompts
are held out by exact text and persona category.

## Promotion

The adapter is promoted to village inference only if:

1. it preserves all literal-identity and unseen-knowledge boundaries;
2. it increases blinded persona distinctness over the base model;
3. it expresses at least two sides of the registered tension without collapsing
   into incoherence;
4. it emits a position or action after deliberation;
5. it causes no critical regression on the moral-control-mesh development
   split.

Any pod failure, non-finite loss, missing checkpoint, failed artifact download,
or cleanup failure is a recorded terminal outcome rather than permission to
launch an uncapped replacement.
