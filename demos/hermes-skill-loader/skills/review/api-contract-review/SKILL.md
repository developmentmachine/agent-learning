---
name: api-contract-review
description: Detect breaking changes to public APIs, routes, and shared types.
version: 1.0.0
metadata:
  hermes:
    tags: [review, api, contract]
---

# API Contract Review

Use when the diff changes exported types, HTTP routes, event schemas, or SDK surfaces.

## Breaking change signals

- Removed or renamed field without version bump
- Stricter validation on previously accepted input
- Error code / status code change for same condition
- Default behavior change without opt-in flag
- Narrowed enum or union type consumed by clients

## Non-breaking (usually)

- New optional fields
- New endpoints
- Internal refactor with same wire format

## Process

1. List public symbols touched (OpenAPI tag, package export, protobuf `package`)
2. Search consumers in repo + note external clients if documented
3. Require migration note or version increment for each breaking item

## Verdict impact

Any undocumented breaking change → `request_changes`.
