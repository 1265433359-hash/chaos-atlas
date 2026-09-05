"""External atomic persistence for isolation leases and audits."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any

from chaosatlas.isolation.contracts import ACTIVE_LEASE_STATES, SAFE_ID, validate_audit, validate_lease
from chaosatlas.workspace import state_root


class LeaseStore:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root).expanduser().resolve() if root else state_root() / "isolation"
        self.leases = self.root / "leases"
        self.audits = self.root / "audits"

    def _atomic_write(self, path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def save(self, lease: dict[str, Any], *, require_new: bool = False) -> dict[str, Any]:
        errors = validate_lease(lease)
        if errors:
            raise ValueError("invalid lease: " + "; ".join(errors))
        path = self.leases / f"{lease['lease_id']}.json"
        claimed = False
        if require_new:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                raise FileExistsError(f"lease already exists: {lease['lease_id']}") from None
            else:
                os.close(descriptor)
                claimed = True
        try:
            self._atomic_write(path, lease)
        except Exception:
            if claimed:
                path.unlink(missing_ok=True)
            raise
        return deepcopy(lease)

    @contextmanager
    def creation_lock(self):
        """Serialize active-lease checks across processes without stale locks."""
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / ".creation.lock"
        stream = path.open("a+b")
        acquired = False
        try:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError as exc:
                raise RuntimeError("isolation lease creation is already in progress") from exc
            yield
        finally:
            try:
                if acquired:
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            finally:
                stream.close()

    def load(self, lease_id: str) -> dict[str, Any]:
        if not SAFE_ID.fullmatch(str(lease_id or "")):
            raise ValueError(f"unsafe lease identity: {lease_id}")
        path = self.leases / f"{lease_id}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError, UnicodeError) as exc:
            raise ValueError(f"lease unavailable or damaged: {lease_id}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"lease is not an object: {lease_id}")
        errors = validate_lease(value)
        if errors:
            raise ValueError(f"lease integrity failure: {lease_id}: {'; '.join(errors)}")
        return value

    def list(self) -> list[dict[str, Any]]:
        if not self.leases.is_dir():
            return []
        return [self.load(path.stem) for path in sorted(self.leases.glob("*.json"))]

    def active(self, *, project_id: str | None = None, provider: str | None = None) -> list[dict[str, Any]]:
        return [
            lease for lease in self.list()
            if lease.get("state") in ACTIVE_LEASE_STATES
            and (project_id is None or lease.get("project_id") == project_id)
            and (provider is None or lease.get("provider") == provider)
        ]

    def save_audit(self, audit: dict[str, Any], name: str) -> Path:
        errors = validate_audit(audit)
        if errors:
            raise ValueError("invalid isolation audit: " + "; ".join(errors))
        lease_id = str(audit.get("lease_id") or "")
        if not SAFE_ID.fullmatch(lease_id) or not SAFE_ID.fullmatch(str(name or "")):
            raise ValueError("unsafe isolation audit identity")
        path = self.audits / lease_id / f"{name}.json"
        self._atomic_write(path, audit)
        return path
