# Qwen3-1.7B local soft-test closeout v1

This package inventories and closes the bounded local development tests that
precede any PrimeLab training spend. It does not alter the registered 4,096-token
six-arm experiment or authorize paid compute.

Completed inputs are the exact local runtime smoke, the MeTTa worldview screen,
and the score-gated storyworld cycle. The remaining tests are:

1. a policy-preserving format-control adapter trained from the same parent and
   source prompts as storyworld cycle 1b; and
2. a 20-cell first-turn Mīzān development screen crossing five prompt
   conditions with four rooms for the base, parent, score-trained, and
   format-control checkpoints.

The format control retains each original legal model action and changes only the
assistant response into the required two-line decision format. It therefore
tests whether formatting exposure explains part of the storyworld score change.
The Mīzān screen includes the unreliable-authority diagnostic and is deliberately
small: it is not the sealed 900-turn evaluation matrix.

All GPU invocations remain sequential and use the existing Windows Job Object
wrappers, 3,840 MB VRAM ceiling, 10,240 MB process-commit ceiling, 50% CPU cap,
50 MB/s I/O cap, zero pagefile-growth allowance, no model offload, and PID-bound
cleanup. Paid-compute authorization remains a separate human decision after the
closeout receipt exists.

## Closeout result

The registered ST01-ST05 local matrix is complete. The immutable result receipt
is `soft_test_closeout_20260722.json`.

The format-only control improved the frozen storyworld proxy by 0.009722 over
the parent, compared with 0.043836 for the score-trained adapter. Both reached a
0.208333 forbidden-action rate, so neither authorizes another storyworld cycle.

All four checkpoints produced valid actions for all 20 Mizan probes and had
identical aggregate first-turn metrics. Prompt conditions still changed action
selection: the unreliable-authority condition switched 75% of paired actions,
reduced mean proxy score by 0.125, and increased failure-tag rate by 0.25 versus
neutral. This is a negative checkpoint-transfer diagnostic on the small probe
pack, not a model-equivalence result.

PrimeLab spend remains gated for a separate human decision.

## Data collation

The full `D:\Research_Engine\jinn_or_beast` experiment tree was preserved in
place and collated into `D:\Research_Engine\jinn_or_beast\collated_20260722`.
The archive contains all 847 pre-collation source files plus 11 repository
metadata files. Its independent verification receipt is
`jinn_or_beast_collation_20260722.json`.
