# Local workspace policy

ChaosAtlas keeps the repository root focused on product code and reproducible project inputs.

## Keep in the repository

- `src/`, `cli/`, `tools/`, `scripts/`, `tests/`
- `projects/`, `workloads/`, and product documentation under `docs/`
- Repository metadata and sanitized examples such as `README.md`, `AGENTS.md`, and `pyproject.toml`

## Keep outside the repository

- Live and dry-run evidence (`.runs/`)
- Review renders, temporary extracts, pytest scratch directories, and local runtime state
- Top-level research attachments (`*.docx`) and generated snapshots
- Virtual environments and machine-local configuration

The external state root is:

```text
%LOCALAPPDATA%\ChaosAtlas
```

Set `CHAOSATLAS_STATE_ROOT` to override it. The standard subdirectories are
`runs/`, `tmp/`, and `archive/`; this avoids user-specific paths in scripts.

Each cleanup pass uses a dated subdirectory and preserves relative names. Files are moved, not deleted, so an archived artifact can be restored without rewriting repository history.

The cleanup script recognizes these root-level local patterns:

- Review/render output: `.academic_review*`, `.lo_profile_review*`, `.review_*`
- Test/run scratch: `.pytest*`, `.tmp-*`, `.runs/`, `runtime/`
- Local environments and snapshots: `.docker-config*`, `.zcode/`, `build/`, `.worktrees/`, `.migration/`, `ChaosAtlas-evidence*/`
- Imported project snapshots: `train-ticket/`, `online-boutique/`, `otel-demo/`
- Research attachments: top-level `*.docx`, `*.pdf`, and `github_candidate_snapshot_*.csv`

The script checks every candidate against `git ls-files` and skips an item if it contains any tracked path. Protected product directories and local control state are never moved.

Moves are attempted independently. If a cache is locked or denied by Windows ACLs, the script records the error in `MANIFEST.txt` and continues with the remaining candidates. Close pytest, editors, or other processes that hold the failed path, then rerun with a new `-ArchiveName`.

Run `scripts/archive_root_workspace.ps1 -WhatIf` first to preview a cleanup pass. Run it without `-WhatIf` from a normal PowerShell after stopping any active experiment that writes to `.runs/`.

New experiment output must use the external `runs/` directory. Run Python
commands through `scripts/invoke_python.ps1` so bytecode caches also go to the
external `tmp/` directory. Do not commit machine-local credentials, kubeconfigs,
Docker state, or raw evidence.
