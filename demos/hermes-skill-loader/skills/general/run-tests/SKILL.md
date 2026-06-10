---
name: run-tests
description: Discover and run the project's test commands; interpret common failure modes.
version: 1.0.0
metadata:
  hermes:
    tags: [test, ci, verify]
---

# Run Tests

Use after code changes or when the user asks to verify behavior.

## Discovery order

1. `package.json` scripts (`test`, `test:unit`, `ci`)
2. `Makefile` / `justfile` targets
3. `pyproject.toml` / `pytest.ini` / `tox.ini`
4. Language defaults: `cargo test`, `go test ./...`, `mvn test`

## Execution

- Run the **narrowest** suite that covers your change first
- Capture full failure output; do not truncate stack traces
- On failure: one fix → re-run same command (no shotgun changes)

## Common failure classes

| Signal | Likely cause | Next step |
|--------|--------------|-----------|
| Import / module not found | missing dep or wrong path | check lockfiles, `PYTHONPATH` |
| Snapshot mismatch | intentional UI change | update snapshot only if user confirms |
| Flaky timeout | env or race | reproduce twice; check parallel tests |
| 1 new failure in unrelated file | pre-existing or shared fixture | bisect with `git stash` |

## Report format

```markdown
## Command
`<exact command>`

## Result
pass | fail (N failures)

## Failures (if any)
- `test_name` — one-line root cause + fix status
```
