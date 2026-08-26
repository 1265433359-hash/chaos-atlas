"""Read-only evidence collectors for the automated RCA loop.

Collectors normalize existing artifacts into the shared evidence contract.
They do not execute faults, call Kubernetes, read credentials, or infer RCA
state from missing data.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable

from tools.rca_loop import (
    _contains_sensitive_value,
    _path_errors,
    make_evidence,
    validate_evidence_scope,
)


COLLECTOR_KINDS = {
    "manifest",
    "config",
    "source_span",
    "runtime_log",
    "kubernetes_event",
    "trace",
    "business_path_replay",
    "recovery",
}


class EvidenceCollectorError(ValueError):
    """Raised when a collection request cannot be safely normalized."""


def _safe_source_path(root: Path, source_ref: str) -> Path:
    errors = _path_errors(source_ref)
    if errors:
        raise EvidenceCollectorError("; ".join(errors))
    root_path = Path(root).resolve()
    candidate = (root_path / source_ref.replace("\\", "/")).resolve()
    try:
        candidate.relative_to(root_path)
    except ValueError as error:
        raise EvidenceCollectorError("source_ref resolves outside collector root") from error
    return candidate


def _validate_kind(kind: str) -> None:
    if kind not in COLLECTOR_KINDS:
        raise EvidenceCollectorError(f"unsupported collector kind: {kind}")


def _base_evidence(
    *,
    evidence_id: str,
    kind: str,
    claim_scope: str,
    source_ref: str,
    interpretation: str,
    polarity: str,
    sha256: str | None,
    window: dict[str, str] | None,
    satisfies: Iterable[str],
) -> dict[str, Any]:
    try:
        evidence = make_evidence(
            evidence_id=evidence_id,
            kind=kind,
            polarity=polarity,
            claim_scope=claim_scope,
            source_ref=source_ref,
            interpretation=interpretation,
            sha256=sha256,
            window=window,
        )
    except ValueError as error:
        raise EvidenceCollectorError(str(error)) from error
    evidence["collector"] = kind
    evidence["satisfies"] = (
        sorted({value for value in satisfies if isinstance(value, str)})
        if polarity == "supports"
        else []
    )
    validation = validate_collected_evidence(evidence, claim_scope)
    if not validation["valid"]:
        raise EvidenceCollectorError("; ".join(validation["errors"]))
    return evidence


def collect_unavailable_evidence(
    *,
    root: Path,
    source_ref: str,
    evidence_id: str,
    kind: str,
    claim_scope: str,
    reason: str,
    window: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Record an unavailable diagnostic attempt without treating it as negative evidence."""

    _validate_kind(kind)
    _safe_source_path(root, source_ref)
    reason = str(reason).strip()
    if not reason:
        raise EvidenceCollectorError("unavailable reason must not be empty")
    evidence = _base_evidence(
        evidence_id=evidence_id,
        kind=kind,
        claim_scope=claim_scope,
        source_ref=source_ref.replace("\\", "/"),
        interpretation=f"diagnostic unavailable: {reason}",
        polarity="unavailable",
        sha256=None,
        window=window,
        satisfies=[],
    )
    evidence["unavailable_reason"] = reason
    return evidence


def collect_file_evidence(
    *,
    root: Path,
    source_ref: str,
    evidence_id: str,
    kind: str,
    claim_scope: str,
    interpretation: str,
    polarity: str = "supports",
    satisfies: Iterable[str] = (),
    window: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Collect one evidence record from an immutable file under ``root``."""

    _validate_kind(kind)
    path = _safe_source_path(root, source_ref)
    normalized_ref = source_ref.replace("\\", "/")
    if not path.is_file():
        return collect_unavailable_evidence(
            root=root,
            source_ref=normalized_ref,
            evidence_id=evidence_id,
            kind=kind,
            claim_scope=claim_scope,
            reason="source_not_found",
            window=window,
        )

    data = path.read_bytes()
    text = data.decode("utf-8", errors="replace")
    if _contains_sensitive_value(text):
        raise EvidenceCollectorError(f"sensitive values detected in {normalized_ref}")
    digest = hashlib.sha256(data).hexdigest()
    return _base_evidence(
        evidence_id=evidence_id,
        kind=kind,
        claim_scope=claim_scope,
        source_ref=normalized_ref,
        interpretation=interpretation,
        polarity=polarity,
        sha256=digest,
        window=window,
        satisfies=satisfies,
    )


def validate_collected_evidence(
    evidence: dict[str, Any],
    claim_scope: str,
) -> dict[str, Any]:
    """Validate a collector result against the consumer's expected claim scope."""

    return validate_evidence_scope(evidence, claim_scope)
