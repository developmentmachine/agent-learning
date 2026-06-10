---
name: code-review
description: Structured code review workflow covering correctness, security, and maintainability.
version: 1.0.0
metadata:
  hermes:
    tags: [review, workflow]
---

# Code Review Skill

Umbrella workflow when reviewing pull requests or local changes. Load specialized
review skills when the diff warrants deeper passes.

## Review order

1. **Correctness** — does it do what the PR claims? (`pr-diff-scan`)
2. **Security** — injection, authz, secrets (`security-review`)
3. **Contracts** — public API breaks (`api-contract-review`)
4. **Tests** — coverage gaps (`test-gap-analysis`)
5. **Maintainability** — naming, complexity (in-umbrella only)

## Output format (JSON-friendly)

```json
{
  "summary": "one paragraph",
  "findings": [
    {
      "severity": "blocker|major|minor|nit",
      "category": "correctness|security|performance|maintainability",
      "file": "path/to/file",
      "lines": "42-48",
      "title": "short label",
      "detail": "what is wrong and why it matters",
      "suggestion": "concrete fix"
    }
  ],
  "verdict": "approve|request_changes|comment_only"
}
```

Cap at 4–8 high-signal findings.

## Read-only mode

Do not commit, push, or post review comments unless the user enables auto-fix.
