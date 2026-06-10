---
name: escalation
description: When and how to page platform, DBA, or upstream owners — evidence bundle format.
version: 1.0.0
metadata:
  hermes:
    tags: [oncall, escalation]
---

# Escalation

Use when impact persists after standard triage, or required access is missing.

## Escalate when

- Customer-visible SLO breach beyond agreed window
- Data loss or corruption suspected
- Rollback attempted and failed
- Root cause in dependency you do not operate
- Need break-glass access (prod DB, secrets, network ACL)

## Do not escalate without

- Time window and % impact estimate
- Top failing route or feature
- 1–3 log or trace excerpts (redacted)
- Changes attempted and outcomes

## Evidence bundle template

```markdown
## Incident
- Alert:
- Started (window):
- Impact:

## What we proved
1.
2.

## What we tried
-

## Ask
<specific action needed from target team>
```

## Severity guide

| Level | Example |
|-------|---------|
| P1 | Full outage, data at risk |
| P2 | Major feature degraded, workaround exists |
| P3 | Limited blast, business hours fix OK |
