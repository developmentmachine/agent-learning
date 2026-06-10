---
name: test-gap-analysis
description: Whether behavior changes lack adequate test coverage; suggest minimal tests.
version: 1.0.0
metadata:
  hermes:
    tags: [review, tests]
---

# Test Gap Analysis

Use after understanding what the diff **does**, not before.

## Questions

1. What user-visible or API behavior changed?
2. Is there a test that would fail if the change were reverted?
3. Are edge cases (empty input, error paths, concurrency) covered?

## Project test layout

Discover in order:
- colocated `*_test.go`, `test_*.py`, `*.spec.ts`
- `tests/` / `__tests__` integration suites
- contract / snapshot tests for APIs

## Report

| Behavior change | Existing test | Gap |
|-----------------|---------------|-----|
| ... | yes/no | suggest test name + scope |

## Policy

- Blocker: critical path behavior change with zero tests
- Suggestion: add test in same PR or linked follow-up with ticket

Pair with `run-tests` skill when validating fixes locally.
