# F06 smoke binding amendment

The bounded F06 smoke completed operationally on 2026-07-23, but its v1 launch
plan froze the F04 JSON hash from a Windows CRLF working tree. The exact pushed
Git blob and Linux checkout use LF bytes. Their SHA-256 values are:

- v1 plan, Windows CRLF bytes: `8352dd69daea12b8dc91ee455eacb70e32d641cd5adbfa27be70e24527d637dd`
- canonical Git blob and remote receipt: `9ee2c79751c1b56b11553cf45d19517ea2bf9f74936485775d7f88a0b753da86`

Replacing CRLF with LF is sufficient to produce the remote digest. Parsed JSON
content is unchanged. Nevertheless, the mismatch violates the prospective byte
binding, so the v1 smoke is retained as throughput evidence only and does not
pass its complete launch contract or satisfy F06.

Future launch packets must hash canonical Git blob bytes from the exact pushed
commit, not host working-tree bytes. Tests must reproduce those hashes using
`git show <commit>:<path>` or equivalent. This correction does not authorize a
new paid run, full curriculum generation, or adapter training.
