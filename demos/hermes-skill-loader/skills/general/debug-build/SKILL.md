---
name: debug-build
description: Triage compile errors, test failures, and build pipeline breaks with evidence-first steps.
version: 1.0.0
metadata:
  hermes:
    tags: [debug, build, compile]
---

# Debug Build

Use when builds, compiles, or test suites fail and the root cause is unclear.

## Triage order

1. **Reproduce** — exact command + exit code + first error line (not last)
2. **Classify** — syntax vs dependency vs config vs environment
3. **Minimize** — single file / single test if possible
4. **Fix one layer** — do not change three things at once
5. **Verify** — same command passes; note regressions avoided

## Dependency failures

- Read the lockfile era vs manifest — version skew is common after merges
- PEP 668 / system Python — try `uv`, venv, or `--user` per project convention
- Native extensions — check compiler, headers, `rustc`/`go` version pins

## Compile vs runtime

| Phase | Read first |
|-------|------------|
| Type-check | compiler/linter output line + column |
| Link | missing symbol, wrong architecture |
| Runtime test | assertion line + fixture setup |

## When stuck

Report blocker with:
- command run
- full error excerpt (10–30 lines)
- what you ruled out
- smallest next experiment

Do **not** fabricate successful build output.
