# Constitutional HRM evaluation matrix v1

Run status: completed for the trained 72,194-parameter micro-HRM.

The planned 195M v2 lane was not scored because no trained checkpoint or frozen
tokenizer exists and optimizer launch remains unauthorized.

## Direct result

- Native ID accuracy: 0.8333
- Native OOD accuracy: 0.5625
- Native constitutional/utility contrast accuracy: 0.6452

## Structured transfer probes

- Moral Reasoner v2 pairwise accuracy: 0.7031
  across 128 orientation-balanced duels.
- Moral Reasoner position equivariance: 0.4062.
- Storyworld frame-robust pairwise accuracy: 0.8621
  across 696 orientation-balanced duels.
- Storyworld position equivariance: 0.9655.

Both transfer probes operate on structured scores/proofs. They do not establish
natural-language comprehension.

## Compatibility outcomes

- Prime Hub: compatibility_only; no paid evaluation was launched.
- ARC: not_runnable; the current two-class decision head cannot emit ARC grids.
- 195M v2: not_runnable; no trained 195M checkpoint, tokenizer freeze artifact absent, optimizer launch remains unauthorized.
