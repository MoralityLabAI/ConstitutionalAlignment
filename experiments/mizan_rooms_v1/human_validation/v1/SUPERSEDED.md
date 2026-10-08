# Superseded by v2

On 2026-10-08 the private blinding map for this packet was exposed in a public
upload. The v1 opaque IDs were also recomputable from public room and condition
files, because they were a plain SHA-256 of public identifiers. No review had
been collected under v1.

Use the v2 packet in the sibling `v2/` directory. Its IDs are HMAC-SHA256
under a secret key held outside every repository; the v2 manifest records a
commitment hash of that key. Do not send v1 materials to reviewers.
