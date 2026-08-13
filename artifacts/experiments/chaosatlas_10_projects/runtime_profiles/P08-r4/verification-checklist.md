# P08 Pre-runtime Verification Checklist

- [ ] Verify `index.docker.io/appsmith/appsmith-ce` with an immutable digest from an approved registry path.
- [ ] Confirm the digest provenance is recorded without changing the frozen source commit.
- [ ] Render a namespace-local profile with one replica and bounded requests/limits.
- [ ] Confirm `/api/v1/health` readiness and liveness against the deployed image.
- [ ] Verify a fixed, read-only deterministic API oracle with stable response shape.
- [ ] Run server-side dry-run using an authorized Kubernetes session.
- [ ] Obtain explicit authorization for `chaosatlas-p08` before apply.
- [ ] Keep runtime serial with no other project in the cluster.
- [ ] After every injection, verify recovery, delete the Chaos object, and confirm global no-residual-Chaos.

Current status: blocked. This checklist is preparation evidence only.
