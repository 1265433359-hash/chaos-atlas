# ChaosAtlas External Workspace and Git Cleanup Design

**Date:** 2026-09-05

**Status:** Approved

**Selected approach:** External archive plus curated Git commits

## Goal

Keep the ChaosAtlas repository limited to reviewed source, tests, sanitized
project inputs, curated evidence, and documentation. Runtime output, caches,
dependency installations, notification queues, credentials, and temporary
files must live outside the repository by default.

## External State Boundary

The default local state root is `%LOCALAPPDATA%\ChaosAtlas` on Windows,
`$XDG_STATE_HOME/chaosatlas` when configured, and
`~/.local/state/chaosatlas` otherwise. `CHAOSATLAS_STATE_ROOT` may override the
location explicitly.

The standard subdirectories are:

- `runs/` for unreviewed experiment output;
- `tmp/` for disposable execution state;
- `archive/` for retained historical output and cleanup snapshots.

Formal evidence enters `artifacts/` or `reporting/` only through an explicit
review and redaction step. Application credentials remain in ignored local
secret storage and are never archived into Git.

## Cleanup Decision

The 2026-09-05 cleanup moves repository-local `.runs`, `.tmp-*`, pytest state,
the legacy notification queue, the old `ChaosAtlas-evidence` directory, raw
environment reports, runtime scratch data, and Medusa `node_modules` to a
timestamped external archive. The archive records the source commit, original
paths, file counts, byte counts, SHA-256 tree digests, and restoration
instructions.

The 165 legacy pending notification records are retained for audit but are not
placed in the active mail queue, so they cannot be sent accidentally.

## Prevention

1. Product code obtains default runtime locations from one path module.
2. The CLI defaults new runs to the external `runs/` directory.
3. Pytest disables its repository-local cache by default.
4. Repository inventory skips known local-state and dependency directories.
5. A workspace-hygiene check rejects forbidden local-state directories and is
   part of repository acceptance.
6. The archive command refuses to overwrite an existing archive and refuses
   unsafe source or destination paths.

## Git Strategy

Changes are reviewed and committed in a small number of coherent commits:
workspace hygiene, product/method implementation, unified RunEngine, four-app
deployment assets, and curated evidence/documentation. Generated or sensitive
material is excluded. No remote push is part of this cleanup.
