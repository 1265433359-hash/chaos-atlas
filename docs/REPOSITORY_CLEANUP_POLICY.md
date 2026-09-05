# ChaosAtlas Repository Cleanup Policy

## Purpose

Keep the GitHub repository reproducible and reviewable without destroying the historical evidence used to validate ChaosAtlas.

## Data Classes

### A. Mainline source

Track implementation, tests, project profiles, sanitized fixtures, method contracts, governance rules, and reviewed documentation.

### B. Curated evidence

Track selected reports, issue drafts, acceptance summaries, RCA evidence, and knowledge promotion records when they include provenance, hashes, project scope, and review status.

### C. Local generated output

Do not track temporary pytest directories, `.tmp-*` output, virtual environments, notification queues, caches, debug images, local checkpoints, or repeated runtime logs. These may remain on disk and can be deleted later with an explicit, scoped cleanup operation.

The default location for this state is outside the checkout:

- Windows: `%LOCALAPPDATA%\ChaosAtlas`;
- Linux/macOS with XDG: `$XDG_STATE_HOME/chaosatlas`;
- fallback: `~/.local/state/chaosatlas`;
- explicit override: `CHAOSATLAS_STATE_ROOT`.

Use `runs/`, `tmp/`, and `archive/` below that root. Do not create a new
repository-local `.runs`, `.tmp-*`, `environment-reports`, or notification
queue. Runtime output may enter `artifacts/` or `reporting/` only after an
explicit provenance, redaction, and human-review step.

### D. Archive or object storage

Move only by a separately approved operation: bulk experiment outputs, duplicate runs, full upstream repositories, large raw logs, and historical datasets that are useful but not needed in every clone. The archive must retain a manifest, SHA-256, source commit, and restoration instructions.

### E. Never commit

Never commit API keys, kubeconfigs, private keys, certificates, passwords, credential files, local proxy settings, or unredacted external-service responses.

## Operational Rules

1. Do not use `git add .` in this repository.
2. Review `git diff --cached --name-only` before every commit.
3. Use `tools/repository_inventory.py` before a cleanup or release commit.
4. Do not treat a generated artifact as a weakness, RCA, or knowledge card without its lifecycle and evidence gates.
5. Do not delete or move current experiment data as part of routine GitHub publishing.
6. Prefer a separate archive branch or object store over history rewriting. Removing files from existing Git history requires an explicit approval and a coordinated force-push.
7. Run `python scripts/check_workspace_hygiene.py --root .` before each commit; repository acceptance runs the same gate.
8. Use `scripts/archive_root_workspace.ps1` for local cleanup. Its destination must remain outside the repository and its manifest must be retained.

## Recommended Lifecycle

```text
local run output
  -> inventory and provenance check
  -> select evidence worth retaining
  -> redact and review
  -> commit curated report/manifest
  -> archive bulk output with hash
```

