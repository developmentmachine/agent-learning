---
name: implement-feature
description: Branch, implement, test, and summarize a multi-file feature change with minimal scope.
version: 1.0.0
metadata:
  hermes:
    tags: [implement, feature, workflow]
---

# Implement Feature

Use when adding or changing product behavior across one or more files.

## Workflow

1. **Scope** — restate acceptance criteria; list files likely touched
2. **Explore** — load `repo-explore` if entry points are unclear
3. **Plan minimally** — ordered steps; skip written plan if change is small
4. **Implement** — match existing style; smallest diff that satisfies criteria
5. **Verify** — run tests or linter relevant to touched paths
6. **Summarize** — what changed, how to test, known limitations

## Scope discipline

- Do not add features, refactors, or docs beyond the request
- Do not change unrelated files "while you're here"
- Delete dead code completely; no compatibility shims unless asked

## Verification

| Change type | Minimum check |
|-------------|---------------|
| API handler | unit or integration test for new behavior |
| UI component | dev server + manual path or component test |
| Config / env | dry-run or `--help` proving parse succeeds |

## Pitfalls

- Assuming a library exists — check `package.json` / `requirements.txt` first
- Editing generated files — find the source generator instead
- Stopping after a stub — deliver runnable code backed by test output
