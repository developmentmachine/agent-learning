---
name: security-review
description: OWASP-oriented review — injection, authz, secrets, SSRF for changed code paths.
version: 1.0.0
metadata:
  hermes:
    tags: [review, security]
---

# Security Review

Use when the diff touches auth, input handling, file IO, network, or crypto.

## Checklist (changed paths only)

| Area | Look for |
|------|----------|
| Injection | SQL concat, shell exec with user input, `eval`, template injection |
| AuthZ | missing check on mutating handlers; IDOR on resource ids |
| Secrets | tokens, keys, passwords in diff or logs |
| SSRF | user-controlled URLs fetched server-side |
| Deserialization | pickle/yaml unsafe loads on untrusted data |
| Path traversal | user input in file paths without normalization |

## Severity

- **Blocker** — exploitable without unlikely preconditions
- **Major** — exploitable with common misconfig or stolen session
- **Minor** — defense-in-depth gap

## Output

Each finding: file, lines, attack scenario in one sentence, concrete fix.

Do not approve if blocker unresolved.
