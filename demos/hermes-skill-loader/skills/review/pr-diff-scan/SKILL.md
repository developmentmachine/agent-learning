---
name: pr-diff-scan
description: Read unified diffs and hunk context — ignore noise, map symbols to callers.
version: 1.0.0
metadata:
  hermes:
    tags: [review, diff]
---

# PR Diff Scan

Use as the first pass on any pull request or local change set.

## Scan order

1. Read PR description / commit message — stated intent
2. Scan file list — generated, vendor, lockfile-only changes
3. Per hunk: what behavior changed, not just syntax
4. Flag renamed symbols — search callers before judging API safety

## Skip or deprioritize

- Pure formatting unless it hides logic changes
- Auto-generated protobuf / OpenAPI blobs (verify generator invoked correctly)
- Binary assets unless security-relevant

## Map blast radius

For each changed public symbol (exported fn, route, type):
- load `repo-explore` pattern: find importers
- note tests that should have been updated

## Handoff

- Security-sensitive paths → `security-review`
- Public API surface → `api-contract-review`
- Behavior change without tests → `test-gap-analysis`
