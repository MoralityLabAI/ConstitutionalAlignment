# Committed Silico export scrub findings

Scan date: 2026-07-17

Scanned commit: `e5bf3863b8ebb4cb9c388f8f5cfd85e8c8c68ef7`

Status: findings only. No source export was edited or redacted.

## Scope and method

The scan covered 99 committed files: all tracked `silico_reports/chats/`
exports plus the two `remote_pi_sessions_*_all` source manifests. Total scanned
content was 3,180,772 bytes and 37,138 lines.

Credential checks covered private-key headers; AWS, GitHub, GitLab, OpenAI,
Anthropic, Hugging Face, Slack, Google, npm, PyPI, Stripe, and JWT token forms;
Bearer headers; credential-bearing URLs; and broad key/token/secret/password
assignments. Candidate values were fingerprinted in memory rather than printed.
An additional long underscore-token pass was manually classified as experiment,
workspace, model, path, or artifact identifiers.

Email checks used a case-insensitive mailbox/domain pattern. Name review combined
explicit metadata fields, Windows and POSIX user paths, two-to-four-token
capitalization candidates, citation patterns, a curated second pass, and manual
classification. The name pass is heuristic rather than a general named-entity
recognizer.

## Findings

### Credential material

No credential value matched the configured high-confidence or broad-assignment
detectors. No private-key header, Bearer value, credential-bearing URL, or known
provider-token form was found.

High-severity historical warning: the exports repeatedly state that credentials
formerly stored in `codex-chat-sessions/auth.json` must be considered
compromised and rotated. Relevant locations are:

- `silico_reports/chats/local/readable_chat_exports/constitutional_alignment_primary_handoff.md:40-43,209,559,911`
- `silico_reports/chats/remote/2026-07-14T21-05-12-730Z_019f6272-b619-7e46-ace4-50bd9d841449.md:45,123-129,323,375-378`

Those lines contain warnings, not credential values. The repository cannot prove
that external rotation or revocation occurred, so rotation remains an owner
verification item.

### Email addresses

No email address was found in the scanned exports or manifests.

### Principal identifiers

One local Windows path exposes the principal account alias `patri` at
`silico_reports/chats/local/readable_chat_exports/constitutional_alignment_mizan_handoff.md:296`.
No principal full name or email address was found in scope.

### Non-principal names: documentary participants

The primary handoff names people from a cited documentary at lines 1210 and
1225: Massy, Ziba, Jamileh, Maryam, Judge Deldar, Mrs. Maher, Paniz, and
co-director Ziba Mir-Hosseini. These are source-context names rather than
operational collaborators, but they are the only cluster of non-principal names
whose inclusion describes individual life or family circumstances. They merit a
publication-purpose review even though the handoff cites the public source.

### Non-principal names: public and citation context

The remaining identified names occur as public-figure, author, researcher, or
cultural references:

- Public/cultural references: David Sacks at
  `silico_reports/chats/remote/2026-07-16T02-18-37-822Z_019f68b8-037d-7fd8-80f0-8567fcf1ea3b.md:386`;
  Mura Murati, as spelled in the export, at
  `silico_reports/chats/remote/2026-07-15T19-21-18-274Z_019f6739-f0c2-7bd9-a840-f2fd1640a270.md:24`;
  and William Gibson at
  `silico_reports/chats/remote/2026-07-16T02-18-37-822Z_019f68b8-037d-7fd8-80f0-8567fcf1ea3b.md:238`.
- Alignment and ethics citations: Betley, Coleman, Greenblatt, Denison, Wright,
  Laine, Needham, Sheshadri, Talat, and Floridi. Representative locations are
  `silico_reports/chats/local/readable_chat_exports/constitutional_alignment_primary_handoff.md:109-114,1394`;
  `silico_reports/chats/remote/2026-07-14T21-05-12-730Z_019f6272-b619-7e46-ace4-50bd9d841449/32f052e0/run-0/session.md:65,73`;
  the same tree's `32f052e0/run-1/session.md:75,77,92` and
  `32f052e0/run-2/session.md:66,68`; and its
  `02d2c73b/run-0/session.md:69`.
- Mathematical citation: Auffinger, Ben Arous, and Černý at
  `silico_reports/chats/remote/2026-07-16T00-32-18-409Z_019f6856-abe9-7055-b7f4-8476e0232e6d.md:406`
  and `silico_reports/source_manifests/remote_pi_sessions_index_all.md:372`.

These are bibliographic or public-context disclosures, not private operational
identity leaks. Metric eponyms, organizations, product/model personae, and
authored story characters were not classified as personal-data findings.

### Operational identities

No named reviewer, scholar, employee, student, private correspondent,
signatory, or collaborator was found in explicit name/author/owner metadata.
No signature block or reviewer receipt containing a personal name was found.

## Disposition

- Source exports remain byte-for-byte unchanged.
- Verify rotation or revocation of every credential that ever appeared in the
  historical `auth.json`; absence from the current exports does not close that
  external action.
- Before a public export release, decide whether the documentary participants'
  names are necessary. If not, replace that handoff discussion with role-level
  descriptions in a separately versioned public derivative, not in the
  provenance export.
- Public citations can remain when needed for attribution. The three incidental
  public/cultural references can be removed from a public derivative if they do
  not support the research record.
- A dedicated repository secret scanner should remain a release gate because
  this regex-based findings pass is not a proof of absence.
