# Scholar review receipts

No review receipt has been issued. This directory is the designated handoff
location; its existence is not evidence of approval.

For each card, place one JSON receipt here that validates against
`schemas/frame_internalization_scholar_review_receipt_v1.schema.json` and names
the exact card SHA-256 from `../scholar_review_contract_v1.json`. Then run:

```powershell
python scripts/validate_frame_internalization_package.py `
  --review-receipt experiments/frame_internalization_sft_v1/scholar_reviews/F3_review.json `
  --review-receipt experiments/frame_internalization_sft_v1/scholar_reviews/F3_concrete_review.json `
  --require-fielding-ready
```

Exit 0 passes only the frame-specific scholar gate. It does not authorize an
experiment launch. A revision to either card changes its hash and requires a new
version, updated manifests, and a fresh receipt.
