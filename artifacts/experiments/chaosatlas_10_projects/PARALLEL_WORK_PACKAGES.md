# Parallel Work Packages

This document defines safe work that can run in separate conversations. All
packages are offline or source-preparation work unless explicitly stated.

## Critical path

The first usable next project is the one with a complete, exact source tree,
an immutable image/profile, a deterministic business oracle, and a passed
namespace-local runtime gate. Do not spend parallel sessions on repeated P02
injection or unapproved DeepSeek calls.

## Package A: restore exact source trees

Goal: recover P03, P06, and P09 at their registered commits into quarantine
directories, then compare file inventories and commit hashes with the frozen
manifests. Do not overwrite `artifacts/experiments/chaosatlas_10_projects/sources/`
until the comparison is reviewed.

Suggested outputs:

- `artifacts/experiments/chaosatlas_10_projects/source_restore/<project>/`
- `source_restore/<project>/restore_manifest.json`
- exact commit, tree SHA, file count, and SHA-256 inventory

Constraints: no source edits, no mutable branch checkout, no secrets in output.

## Package B: P09 reduced runtime profile

Goal: from the restored P09 source, derive a minimal profile containing only
API, worker, worker-beat, web, Postgres, Redis, and required initialization.
Disable vector stores, plugin daemon, sandbox, SSRF proxy, agent backend, Nginx,
and all external model integrations. Pin every image by digest.

Required outputs:

- namespace-local Kubernetes YAML
- non-secret env manifest
- image digest manifest
- deterministic health and local mock-workflow oracle
- server-side dry-run report

Do not apply until the runtime gate is reviewed.

## Package C: P03 reduced runtime profile

Goal: restore the exact Saleor tree, resolve only documented non-secret dev env
values, pin Postgres/Valkey/Mailpit/dashboard images, and define a deterministic
GraphQL health/catalog read oracle. Keep the application commit unchanged.

## Package D: ChaosEater official-baseline audit

Goal: inspect `C:/APP/tools/chaos-eater` read-only and determine whether its
native Skaffold/Kubernetes input can run against one selected project. Record
the exact required files, command, namespace, and cleanup behavior. Do not call
the adapter when the official path is unavailable, and do not rename adapter
results as official results.

## Package E: experiment statistics and reporting

Goal: implement an offline analyzer for project-clustered results. It must
report KB-minus-noKB paired differences by project, with seeds as repeated
measurements. Keep valid-output rate, compiler rate, executable rate, confirmed
weakness yield, protected yield, method-invalid rate, environment-blocked rate,
coverage/depth, recovery, tokens, and human review time separate.

## Package F: user-review package

Goal: review the protocol and source-restore manifests only. Verify that no
runtime observation, oracle verdict, RCA, mutation path, or same-project
feedback can reach the KB prompt. This package may update documentation but
must not change experiment inputs.

## Shared safety rules

- Never touch Docker Desktop.
- Use the WSL-native Docker endpoint only when a runtime package is explicitly
  authorized: `DOCKER_HOST=tcp://localhost:2375`.
- Keep each project in its own namespace and work directory.
- Do not read the DeepSeek key or send model requests during source/profile
  preparation.
- Do not overwrite frozen evidence; create a new protocol/artifact version if
  a registered input changes.
- Before any model call, require a passed runtime gate and an explicit call
  plan with model, token cap, retry policy, and cost ceiling.

## Recommended assignment order

1. Package A: restore P09 first, then P03 and P06.
2. Package B: build the P09 reduced profile and oracle.
3. Package D: determine whether the official ChaosEater arm is executable.
4. Package E: prepare the analyzer while runtime work proceeds.
5. Package F: review the resulting manifests before any API call.
