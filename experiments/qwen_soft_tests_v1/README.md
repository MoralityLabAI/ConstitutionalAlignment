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
