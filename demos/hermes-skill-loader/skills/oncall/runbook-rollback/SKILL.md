---
name: runbook-rollback
description: Safe rollback and post-rollback verification for deployments and config changes.
version: 1.0.0
metadata:
  hermes:
    tags: [oncall, rollback, deploy]
---

# Runbook Rollback

Use when a recent deploy or config change correlates with incident start time.

## Pre-rollback checks

1. Confirm **blast radius** — rollback fixes majority of errors, not a side symptom
2. Check **data migrations** — irreversible migrations may forbid full rollback
3. Notify **stakeholders** if rollback affects in-flight transactions

## Rollback steps (generic)

1. Identify last known-good revision (deploy tag, config version)
2. Execute platform rollback (K8s `rollout undo`, feature flag off, etc.)
3. Watch error rate and latency for 10–15 minutes
4. Sample traces on previously failing routes

## Verification metrics

| Metric | Pass criterion |
|--------|----------------|
| Error rate | returns to pre-incident baseline |
| p99 latency | within 20% of baseline |
| Saturation | conn pool / CPU not pegged |

## If rollback fails

Stop further mutations; load `escalation` with evidence bundle:
alert time, deploy id, rollback command output, current error sample.
