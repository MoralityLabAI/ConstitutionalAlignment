# Synthetic CPU evidence only

`cpu_verification.json` is the reproducible result from the cloud Python CPU sandbox. It runs **133 tests**: 65 original v3, 43 v3.1, and 25 independent semantic audit tests. The 12-motif fixture produces 48 mock rationale review cards; it contains no real Silico generations or human judgments. Source SHA-256s bind the implementation, and CI regenerates the full synthetic review queue as a job artifact.

`synthetic_audit_preview.json` reports a shape-matched fixture. Model-generated v3.1 raw data remain in Silico and must be mounted on the worker to create a real review queue. The four real exported SFT arms and their independent tokenizer count have not been inspected by this sandbox.
