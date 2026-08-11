# TeaStore Held-out Candidate Review

> Status: candidate only; source not fetched, not deployed, and not experimented on.

## Source

- Canonical URL: `https://github.com/DescartesResearch/TeaStore`
- Fixed candidate commit: `34b37f7e7be433ce72d5f9455e66922a13116749`
- License: Apache-2.0
- Repository is independent of TT, OB, OTEL, Sock Shop, Hotel, and DeathStarBench.

## Why It Fits

TeaStore is explicitly a microservice benchmark with five services plus a registry. The repository provides a multi-service Helm chart under `examples/helm`, Kubernetes variants including `examples/kubernetes/teastore-ribbon.yaml`, and Docker Compose under `examples/docker/docker-compose_default.yaml`. `teastore-all.yaml` is an all-in-one Pod fallback and must not be used as the primary multi-service graph. The README documents REST/Ribbon communication and instrumented variants.

This is a better replacement for ESHOP because the deployment target is present in the canonical repository. It also adds a Java/REST/Ribbon stack, independent from Hotel/SOCIALNET and the existing Go/.NET/C++ systems.

## Evidence and Limits

The fixed commit and key Git blob IDs are recorded in the JSON companion. Those Git blob IDs are not local SHA-256 values; after approval, intake must compute local SHA-256 for every source and manifest used.

Service graph, timeout/retry behavior, probes, PDB/HPA, image availability, observability reachability, and the 24/48 candidate capacity are still `unknown`. They must be verified before this project can count as comparable.

The three pinned knowledge files contain zero direct `TeaStore`/`DescartesResearch` hits. This is a direct-text leakage result, not proof that all abstract rules are implementation-independent.

## Decision

Recommended role: replacement for blocked ESHOP. Target set becomes Hotel + SOCIALNET + TeaStore, conditional on static intake and a valid pre-experiment snapshot. No source fetch or experiment is authorized by this record.
