"""Contracts shared by the ChaosAtlas offline closed-loop orchestrator."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STAGES = (
    "onboard",
    "inventory",
    "server_deployment_detection",
    "mapping",
    "retrieval",
    "hypotheses",
    "gate",
    "baseline",
    "execute",
    "observe",
    "classify",
    "rca",
    "learn",
    "regression",
)
_STAGE_SET = set(STAGES)
_STATUSES = {"completed", "failed", "blocked", "skipped", "not_run"}
_CLAIM_SCOPES = {"static", "synthetic", "advisory", "runtime", "none"}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    if isinstance(value, bytes):
        data = value
    elif isinstance(value, str):
        data = value.encode("utf-8")
    else:
        data = _canonical(value).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return path


def _profile_fingerprint(profile_path: str | Path) -> str:
    path = Path(profile_path)
    if path.is_file():
        return _sha256(path.read_bytes())
    return _sha256(str(path).replace("\\", "/"))


@dataclass(frozen=True)
class RunContext:
    run_id: str
    profile_path: str
    mode: str
    seed: int
    input_snapshot_sha256: str
    output_root: str

    @classmethod
    def create(
        cls,
        *,
        profile_path: str | Path,
        mode: str,
        seed: int,
        output_root: str | Path,
    ) -> "RunContext":
        if mode not in {"dry-run"}:
            raise ValueError("offline run mode must be dry-run")
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise ValueError("seed must be an integer")
        profile_text = str(profile_path).replace("\\", "/")
        snapshot = {
            "profile_fingerprint": _profile_fingerprint(profile_path),
            "profile_path": profile_text,
            "mode": mode,
            "seed": seed,
        }
        input_hash = _sha256(snapshot)
        return cls(
            run_id=f"dry-run-{input_hash[:12]}",
            profile_path=profile_text,
            mode=mode,
            seed=seed,
            input_snapshot_sha256=input_hash,
            output_root=str(Path(output_root)),
        )


@dataclass(frozen=True)
class StageResult:
    stage: str
    status: str
    payload: dict[str, Any]
    claim_scope: str = "static"
    errors: tuple[str, ...] = ()
    next_stage: str | None = None

    def __post_init__(self) -> None:
        if self.stage not in _STAGE_SET:
            raise ValueError(f"unknown stage: {self.stage}")
        if self.status not in _STATUSES:
            raise ValueError(f"unsupported stage status: {self.status}")
        if self.claim_scope not in _CLAIM_SCOPES:
            raise ValueError(f"unsupported claim scope: {self.claim_scope}")
        if not isinstance(self.payload, dict):
            raise ValueError("stage payload must be an object")
        if self.next_stage is not None and self.next_stage not in _STAGE_SET:
            raise ValueError(f"unknown next stage: {self.next_stage}")

    @classmethod
    def completed(
        cls,
        stage: str,
        payload: dict[str, Any],
        *,
        claim_scope: str = "static",
        next_stage: str | None = None,
    ) -> "StageResult":
        return cls(
            stage=stage,
            status="completed",
            payload=payload,
            claim_scope=claim_scope,
            next_stage=next_stage,
        )


def write_stage_artifact(output_root: str | Path, result: StageResult) -> Path:
    output_root = Path(output_root)
    payload_hash = _sha256(result.payload)
    artifact = {
        "schema_version": "chaosatlas-stage-result-v1",
        "stage": result.stage,
        "status": result.status,
        "claim_scope": result.claim_scope,
        "payload": result.payload,
        "output_sha256": payload_hash,
        "errors": list(result.errors),
        "next_stage": result.next_stage,
        "written_at": datetime.now(timezone.utc).isoformat(),
    }
    return _write_json_atomic(output_root / f"{result.stage}.json", artifact)


def write_checkpoint(
    output_root: str | Path,
    *,
    next_stage: str | None,
    completed_stages: list[str],
) -> Path:
    if next_stage is not None and next_stage not in _STAGE_SET:
        raise ValueError(f"unknown stage: {next_stage}")
    if any(stage not in _STAGE_SET for stage in completed_stages):
        unknown = next(stage for stage in completed_stages if stage not in _STAGE_SET)
        raise ValueError(f"unknown stage: {unknown}")
    indices = [_STAGES_INDEX[stage] for stage in completed_stages]
    if indices != sorted(set(indices)):
        raise ValueError("completed stages must be unique and ordered")
    if next_stage is not None and completed_stages and _STAGES_INDEX[next_stage] <= indices[-1]:
        raise ValueError("next stage must follow completed stages")
    payload = {
        "schema_version": "chaosatlas-checkpoint-v1",
        "completed_stages": completed_stages,
        "next_stage": next_stage,
    }
    return _write_json_atomic(Path(output_root) / "checkpoint.json", payload)


def load_checkpoint(output_root: str | Path) -> dict[str, Any]:
    path = Path(output_root) / "checkpoint.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != "chaosatlas-checkpoint-v1":
        raise ValueError("invalid checkpoint")
    write_checkpoint(
        Path(output_root),
        next_stage=value.get("next_stage"),
        completed_stages=list(value.get("completed_stages") or []),
    )
    return value


_STAGES_INDEX = {stage: index for index, stage in enumerate(STAGES)}
