# P08 Static Gate Review

- Project: `P08`
- Namespace: `chaosatlas-p08`
- Gate status: `blocked`
- Runtime apply allowed: `false`
- Server-side dry-run: `not_run`
- Deployment or Kubernetes mutation: `false`
- DeepSeek/API call: `false`

## Passed Checks

- Restored source tree is complete at `sources_restored_r2/P08`.
- Deployment assets are present: `Dockerfile`, Docker Compose profile, Helm chart, and Helm README.
- The static profile is namespace-local and contains one bounded Appsmith service.
- The declared health contract is `GET /api/v1/health`.
- No external model call is part of the declared oracle.

## Blocking Checks

- `immutable_image_provenance_missing`: the Compose profile uses mutable `index.docker.io/appsmith/appsmith-ce:release`.
- `deterministic_oracle_unverified`: only an offline contract exists; no runtime response evidence exists.
- `resource_limits_unverified`: the proposed resource values have not passed a resource pilot.
- `resource_pilot_required_very_high`: P08 is explicitly gated on the high-resource pilot.

## Decision

P08 remains static-gate blocked. No image was pulled, no namespace was created or changed, no server-side dry-run was attempted, and no Chaos resource was applied. The next valid step requires immutable image provenance, a reviewed deterministic oracle, and a successful bounded resource pilot, followed by explicit namespace authorization.

## Evidence

- `static-gate.json`
- `preparation-report.json`
- `image-digest-manifest.json`
- `profile-preflight.json`
- `server-side-dry-run.json`
- `bounded-profile.json`
