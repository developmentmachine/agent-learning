# Pre-deploy Checklist

## Manifest

- [ ] Image tag is immutable (not `latest`)
- [ ] `replicas` matches expected load
- [ ] `livenessProbe` and `readinessProbe` configured
- [ ] `resources.requests` and `limits` set

## Cluster

- [ ] Namespace exists and RBAC is correct
- [ ] Secrets / ConfigMaps referenced and present
- [ ] NetworkPolicy allows required ingress/egress

## Post-deploy

- [ ] `kubectl rollout status` succeeded
- [ ] Error rate in metrics is flat
- [ ] Rollback command documented in runbook
