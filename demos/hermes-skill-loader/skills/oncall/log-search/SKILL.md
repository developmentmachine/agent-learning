---
name: log-search
description: Query centralized logging — time windows, field filters, and correlation IDs.
version: 1.0.0
metadata:
  hermes:
    tags: [oncall, logs, search]
---

# Log Search

Use to prove or disprove hypotheses with log evidence.

## Query construction

1. **Anchor time** — alert start ± 15 min (widen only if empty)
2. **Service filter** — `service`, `app`, or index name from runbook
3. **Status / level** — `status>=500`, `level=error`
4. **Route or feature** — path prefix, feature flag, tenant id if known
5. **Correlation** — `trace_id`, `request_id`, `user_id` from one sample error

## Reading order

- Count by route → find concentration
- Pick one representative error line → extract ids
- Follow same `trace_id` across services (gateway → upstream → DB)

## Anti-patterns

- Searching entire cluster without service filter
- Treating a single log line as root cause without cross-service check
- Quoting log lines you did not retrieve via tools

## Handoff

When logs implicate an upstream, load `trace-analysis` next.
