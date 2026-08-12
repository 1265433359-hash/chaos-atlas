# Main Experiment Deployment Remediation Queue

This queue is subordinate to the open-discovery protocol. It records what is
needed before a project can contribute runtime results; static method inputs
may be frozen before these gates pass. No item authorizes an LLM request or a
fault injection.

| Priority | Project | Current gate | Next bounded action | Runtime result condition |
|---|---|---|---|---|
| 1 | P02 Spring Petclinic | Passed | Keep namespace and baseline stable; run only after explicit LLM consent | Health, baseline, business oracle, recovery and cleanup remain valid |
| 2 | P06 Directus | App build and license review | Build the frozen Dockerfile and select one database profile; create namespace-local manifest | Immutable image digest, readiness, schema/items oracle, recovery, cleanup |
| 3 | P03 Saleor | Compose env and image provenance | Resolve non-secret dev env, pin dashboard/app images, run migration smoke | GraphQL health/catalog oracle plus recovery and cleanup |
| 4 | P07 Outline | App build and dependency profile | Build frozen app image and run only local Postgres/Redis dependencies | Health/document oracle plus recovery and cleanup |
| 5 | P10 Keycloak | Build or immutable image provenance | Prefer source build; otherwise record exact digest and local realm/client fixture | Ready endpoint and token oracle plus recovery and cleanup |
| 6 | P05 Immich | Resource pilot and mutable ML image | Disable ML or use a pinned CPU-only image; measure memory before namespace apply | Server/library oracle plus recovery and cleanup |
| 7 | P09 Dify | Local mock model profile | Replace external model calls with deterministic mock and validate reduced Compose profile | API/mock workflow oracle plus recovery and cleanup |
| 8 | P08 Appsmith | Resource pilot and mutable release image | Pin single-node image and measure resource footprint | API oracle plus recovery and cleanup |
| 9 | P01 eShop | No committed Compose/Kubernetes app manifest | Produce a separately hashed Aspire-to-kind normalization; do not modify frozen source | HTTP transaction oracle and full lifecycle evidence |
| 10 | P04 Medusa | No bounded reproducible deployment entry | Remains out of domain unless a documented server profile is found | Do not include in method-quality denominator until gate changes |

## Gate discipline

- A static profile or image build is not a runtime pass.
- Every generated manifest must pass Kubernetes server-side dry-run before apply.
- Each project gets one isolated namespace and one deterministic oracle.
- Environment failures are recorded separately from method-invalid outputs.
- Official ChaosEater remains blocked until a native Skaffold/Kubernetes input is
  available; the adapter is not an official-baseline substitute.
