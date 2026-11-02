# Executed CPU evidence

The committed receipt binds 281 successful CPU tests, comprising 49 new integration tests and 232 prior regressions, with zero skips. The frozen v4 corpus was independently rebuilt and all 320 rows were admitted only after certificate and text regeneration. The old regression run was reproduced separately and its source hashes rechecked when composing this receipt.

A character-offset tokenizer double exercised input boundaries and supervision masks. Its counts are synthetic software fixtures. The retained Qwen tokenizer was unavailable, so `student_tokenizer_measurement` is `NOT_RUN_TOKENIZER_NOT_MOUNTED`. The worker's tokenizer-only command supplies the missing production measurements without allocating a GPU.

Tiny Torch tests performed real optimizer/backward operations on random local modules. They did not load Qwen, exercise PEFT on a pretrained model or run a GPU. Transfer-policy controls are deterministic function checks. No new student training, model inference, Hugging Face upload or sealed-test access happened here.

The downloadable archive includes logs, regenerated corpus, synthetic preflight and control rollouts. CI regenerates equivalent evidence and checks Python source hashes; platform timings and log hashes may differ.
