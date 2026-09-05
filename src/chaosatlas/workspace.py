"""External paths for local ChaosAtlas runtime state.

Repository content is reviewable product material. Unreviewed runs, temporary
files, and archives belong in an operating-system state directory instead.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


STATE_ROOT_ENV = "CHAOSATLAS_STATE_ROOT"


def state_root(env: Mapping[str, str] | None = None) -> Path:
    """Return the configured external state root without creating it."""

    values = os.environ if env is None else env
    configured = str(values.get(STATE_ROOT_ENV, "")).strip()
    if configured:
        return Path(configured).expanduser().resolve()

    local_app_data = str(values.get("LOCALAPPDATA", "")).strip()
    if local_app_data:
        return (Path(local_app_data) / "ChaosAtlas").resolve()

    xdg_state_home = str(values.get("XDG_STATE_HOME", "")).strip()
    if xdg_state_home:
        return (Path(xdg_state_home) / "chaosatlas").expanduser().resolve()

    return (Path.home() / ".local" / "state" / "chaosatlas").resolve()


def runs_root(env: Mapping[str, str] | None = None) -> Path:
    return state_root(env) / "runs"


def temporary_root(env: Mapping[str, str] | None = None) -> Path:
    return state_root(env) / "tmp"


def archive_root(env: Mapping[str, str] | None = None) -> Path:
    return state_root(env) / "archive"


def default_run_output(name: str = "run", env: Mapping[str, str] | None = None) -> Path:
    """Return a stable external location for a named run."""

    normalized = str(name).strip().replace("\\", "-").replace("/", "-") or "run"
    return runs_root(env) / normalized


def is_within(path: str | Path, parent: str | Path) -> bool:
    """Return whether *path* resolves to *parent* or one of its descendants."""

    resolved = Path(path).expanduser().resolve()
    boundary = Path(parent).expanduser().resolve()
    return resolved == boundary or boundary in resolved.parents
