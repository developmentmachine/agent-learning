---
name: trace-analysis
description: Read distributed traces — find error span, latency bottleneck, and propagation path.
version: 1.0.0
metadata:
  hermes:
    tags: [oncall, trace, apm]
---

# Trace Analysis

Use when logs point to a `trace_id` or latency/error spans a service chain.

## Read order

1. **Root span** — entry service, total duration, HTTP status
2. **Error span** — first span with `error=true` or non-OK status (often not the leaf)
3. **Critical path** — longest child spans on the hot path
4. **Retries** — repeated identical downstream calls (retry storms)

## Classify failure

| Pattern | Interpretation |
|---------|----------------|
| connect timeout on client span | upstream down, saturated, or network ACL |
| 4xx on leaf only | validation/auth in leaf service |
| 5xx after long DB span | query timeout, lock, pool exhaustion |
| missing child span | async drop or instrumentation gap |

## Evidence rule

State which span name + duration + status proved the hypothesis.

## Next skills

- Pool/infra saturation → `runbook-rollback` or capacity runbook
- Unknown owner service → `escalation`
