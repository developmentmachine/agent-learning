---
name: deploy-k8s
description: Deploy services to Kubernetes with rolling updates, health checks, and rollback procedures.
version: 1.0.0
metadata:
  hermes:
    tags: [kubernetes, deploy, devops]
---

# Deploy to Kubernetes

Use this skill when the user asks to deploy, roll out, or update a service on Kubernetes.

## Prerequisites

- `kubectl` configured for the target cluster
- Image already pushed to a registry
- Skill directory: `${HERMES_SKILL_DIR}`

## Standard workflow

1. **Validate manifest** — run `kubectl apply --dry-run=client -f deployment.yaml`
2. **Apply** — `kubectl apply -f deployment.yaml`
3. **Watch rollout** — `kubectl rollout status deployment/<name> -n <namespace>`
4. **Verify health** — check `/health` endpoint or pod readiness
5. **Rollback if needed** — `kubectl rollout undo deployment/<name>`

## Canary / rolling strategy

| Strategy | When to use |
|----------|-------------|
| Rolling update | Default; zero-downtime for stateless services |
| Canary | High-risk changes; route 5–10% traffic first |
| Blue-green | Major version jumps; requires duplicate capacity |

## Pitfalls

- Never skip readiness probes on new deployments
- Always set `resources.requests` to avoid noisy-neighbor scheduling
- Check HPA limits before scaling events

## References

For the full pre-deploy checklist, load:
`skill_view(name="deploy-k8s", file_path="references/checklist.md")`
