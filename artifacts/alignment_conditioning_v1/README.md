# Alignment Conditioning Build Artifact

`manifest.json` is the checked audit receipt for the local 2026-07-14 build.
The generated JSONL splits are intentionally ignored because the underlying
storyworld source provenance and distribution licenses still need review.

Rebuild from the local source archive with:

```powershell
python scripts/build_alignment_conditioning_dataset.py
python scripts/audit_alignment_conditioning_artifact.py
```

The build must pass both the reported-source-token and post-dedup conditioning
token gates. A clean clone without the local source archive is expected to fail
the required-source checks rather than silently emit a smaller corpus.
