---
name: code-review
description: Structured code review workflow covering correctness, security, and maintainability.
version: 1.0.0
---

# Code Review Skill

Follow this workflow when reviewing pull requests or local changes.

## Review order

1. **Correctness** — does it do what the PR claims?
2. **Security** — injection, authz, secrets, input validation
3. **Performance** — N+1 queries, unbounded loops, hot paths
4. **Maintainability** — naming, tests, docs for non-obvious logic

## Output format

```markdown
## Summary
<1-2 sentences>

## Blocking issues
- ...

## Suggestions
- ...

## Nitpicks
- ...
```

## Security focus areas

- User-controlled input reaching SQL/shell/eval
- Missing authorization on mutating endpoints
- Hardcoded credentials or tokens in diff
