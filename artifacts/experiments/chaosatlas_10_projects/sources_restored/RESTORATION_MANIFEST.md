# Isolated Source Restoration Manifest

Date: 2026-08-12

Scope: source recovery and verification only. No deployment, cluster mutation, or DeepSeek/model call was performed.

Existing frozen snapshots under `../sources/{P03,P06,P09}` were not overwritten.

## P09

- Repository: `langgenius/dify`
- Commit: `cd0e88c680dec24dcd423b880302104f13d28462`
- Tree: `f0344ffb88d2bd09a8ab1a5d3949623abe91aca9`
- Isolated path: `sources_restored/P09`
- Git tree files: `13,455`
- Restored files: `13,455`
- Status: `complete`
- Required files: all present
  - `package.json`
  - `pnpm-lock.yaml`
  - `docker/.env.example`
  - `docker/docker-compose.yaml`
  - `docker/docker-compose-template.yaml`
  - `docker/docker-compose.middleware.yaml`
  - `api/Dockerfile`
  - `web/Dockerfile`

## P03

- Repository: `saleor/saleor`
- Commit: `15575bd85a8e0b87bfa867bb8a01cb76bca913ad`
- Tree: `f7de71af55ea09258b3cd24ce43633bf11cce3e2`
- Existing local tree file count: `4,664`
- Status: `blocked_incomplete`
- Reason: the existing partial clone exposes only 7 local blobs; GitHub archive download timed out in the current network channel. No incomplete snapshot was promoted as a complete restoration.
- Expected deployment assets from manifest: `Dockerfile`, `.worktree-container/docker-compose.yml`, `.devcontainer/docker-compose.yml`, `socket.yml`.

## P06

- Repository: `directus/directus`
- Commit: `9dca3724a6d65126ea937ef949f986e5aab47a81`
- Tree: `882abaca309ccdaea234bc50dcf5138f1f63e03e`
- Existing local tree file count: `4,529`
- Status: `blocked_incomplete`
- Reason: the existing partial clone exposes only 48 local blobs; GitHub archive download timed out in the current network channel. No incomplete snapshot was promoted as a complete restoration.
- Expected deployment assets from manifest: `Dockerfile`, `docker-compose.yml`, `directus/readme.md`.

## Verification Notes

- P09 commit and tree were resolved from the official remote-backed Git metadata and expanded with Git-native index checkout into the isolated path.
- A first `git archive | tar` attempt was discarded after Windows tar checksum errors; it did not modify the original snapshots.
- P03/P06 full-blob fetches and archive attempts were read-only and did not deploy or invoke any model endpoint.
