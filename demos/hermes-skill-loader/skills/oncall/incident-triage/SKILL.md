---
name: incident-triage
description: First 15 minutes checklist for new alerts — stabilize, scope, gather evidence.
version: 1.0.0
metadata:
  hermes:
    tags: [oncall, incident, triage]
---

# Incident Triage

Use at the start of any production alert or user-reported outage.

## First 15 minutes (ordered)

1. **Acknowledge** — note alert name, severity, start time (window, not exact clock in prompt)
2. **User impact** — which routes, regions, % errors, revenue-critical paths
3. **Recent changes** — deploys, config, traffic shifts in last 2 hours
4. **Health dashboards** — error rate, latency p99, saturation (CPU/mem/conn pool)
5. **Logs** — filter by service + status + route; sample 5–10 failing traces
6. **Stabilize if bleeding** — rollback / scale / circuit-break **before** deep RCA

## Forbidden until scoped

- Broad config changes without evidence
- Restarting everything
- Declaring root cause without trace or log proof

## Output contract

Every incident reply MUST use three sections (do not merge process and fix):

### 问题 / 背景
### 过程（定位）
### 方案（处理）

## References

Worked example (gateway 503 after deploy):
`skill_view(name="incident-triage", file_path="references/example-gateway-503.md")`
