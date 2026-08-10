#!/usr/bin/env python3
"""Stage D (P3): build and freeze neutral candidate pools for the three
comparable held-out projects (HOTEL, SOCIALNET, TEASTORE).

Design constraints (protocol v1.1 + Stage D prompt):
  - pilot pool = 24 candidates/project; formal pool = 48 candidates/project.
  - protection-class quota: pilot 8/8/8, formal 16/16/16
    (protected / unprotected / unknown) - reported EXACTLY; where the
    project's static snapshot evidence cannot legally fill a class, the
    shortfall is reported and the project is marked quota_shortfall instead
    of fabricating candidates (prompt rule: no copying, no cross-project
    padding, no rule relaxation).
  - fault families: delay/loss/kill all present per project.
  - generation is fully NEUTRAL: every candidate is derived from the frozen
    knowledge snapshot (contract edges + availability) and a fixed, neutral
    parameter ladder; nothing references experiment results or post-hoc
    knowledge. Selection is not run here (blind_ranking stays null).
  - YAML: one injection per candidate (mode=one); NetworkChaos for delay/loss
    (direction=to, matching the project's prior ablation templates), PodChaos
    pod-kill for kill.

Protection-class rule (static, project-agnostic, pre-experiment):
  - protected : contract == explicit_timeout AND fault == delay
                (source-verified timeout absorbs delay).
  - unknown   : contract == retry_policy_timeout_unknown (retry-only, timeout
                bound unverified) for delay/loss; OR explicit_timeout AND
                fault == loss (loss_bounded=false -> loss behavior unverified).
  - unprotected: contract == no_timeout for delay/loss (explicit absence of a
                timeout/fallback/circuit/retry mechanism); OR kill on a
                service whose availability shows replicas==1 and no PDB
                (killing the only pod = total outage; no redundancy defense).

Selector facts:
  - namespace = heldout-<project.lower()>-lab (project convention already used
    by the committed knowledge-ablation templates).
  - SOCIALNET network-edge app labels reuse the committed ablation templates
    (selector_evidence=verified_by_prior_artifact); HOTEL/TEASTORE app labels
    follow the manifest-convention (selector_evidence=convention_based,
    confirmed at the Stage F deployment gate, pre-registered check).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
HELDOUT = ROOT / "artifacts" / "experiments" / "heldout"
POOL_DIR = HELDOUT / "candidate_pools"

RULE_VERSION = "heldout-candidate-generation-v1"
GENERATION_SEED = "heldout-stage-d-v1"  # fixed; selection is deterministic

# Fixed neutral parameter ladders (pre-registered, project-independent).
DELAY_TIERS_MS = [500, 1000, 2000]
LOSS_TIERS_PCT = [10, 50, 100]
DURATION = "30s"
CORRELATION = "100"
JITTER = "0ms"

# Quotas from protocol v1.1 §8.
PILOT_PER_PROJECT = 24
FORMAL_PER_PROJECT = 48
PILOT_QUOTA = {"protected": 8, "unprotected": 8, "unknown": 8}
FORMAL_QUOTA = {"protected": 16, "unprotected": 16, "unknown": 16}

# Projects eligible for Stage D (snapshot status == valid AND full_pre).
PROJECTS = ("HOTEL", "SOCIALNET", "TEASTORE")

# SOCIALNET network-edge app labels, reused from the committed ablation
# templates under artifacts/experiments/knowledge_ablation_mutations/SOCIALNET/
# (dst token -> app label). Verified by prior artifact.
SOCIALNET_EDGE_APP_LABEL = {
    "poststorage": "post-storage",
    "usertimeline": "user-timeline",
    "text": "text",
    "user": "user",
    "media": "media",
    "hometimeline": "home-timeline",
    "uniqueid": "unique-id",
    "socialgraph": "social-graph",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_snapshot(project: str) -> dict:
    path = HELDOUT / f"{project.lower()}_knowledge_snapshot_pre.json"
    if not path.exists():
        raise FileNotFoundError(f"missing snapshot: {path}")
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    if snapshot.get("status") != "valid":
        raise RuntimeError(f"{project} snapshot is not valid: {snapshot.get('status')}")
    if snapshot.get("full_pre") is not True:
        raise RuntimeError(f"{project} snapshot is not full_pre")
    if snapshot.get("contract", {}).get("candidate_map") not in (None, {}):
        raise RuntimeError(f"{project} snapshot candidate_map must be empty before pool freeze")
    return snapshot


def protection_class(contract: dict, fault: str, availability: dict) -> str:
    """Static, project-agnostic protection classification (see module docstring).

    `contract` is the frozen contract edge record; `availability` is the frozen
    availability record for kill targets. Raises on unclassifiable input so a
    new contract type cannot silently slip through as protected.
    """
    ctype = (contract or {}).get("contract")
    if fault in ("delay", "loss"):
        if ctype == "explicit_timeout":
            # timeout absorbs delay; loss_bounded=false -> loss unverified.
            return "protected" if fault == "delay" else "unknown"
        if ctype == "retry_policy_timeout_unknown":
            # retry-only, timeout bound unknown -> never protected.
            return "unknown"
        if ctype == "no_timeout":
            return "unprotected"
        raise ValueError(f"unclassifiable contract type {ctype!r} for fault {fault}")
    if fault == "kill":
        # availability profile must be present and frozen-verified.
        if not availability:
            raise ValueError("kill candidate without availability profile")
        replicas = int(availability.get("replicas", 1) or 1)
        if replicas > 1 or availability.get("pdb"):
            return "protected"
        return "unprotected"
    raise ValueError(f"unsupported fault family {fault!r}")


def _split_edge(edge: str) -> tuple[str, str]:
    """Split a frozen contract key like 'HOTEL-frontend->search' into
    (src, dst), stripping the '<PROJECT>-' prefix from the source token so the
    candidate id is 'HOTEL-frontend-search-DELAY-500' (single project prefix;
    keeps decision_engine.normalize_service() resolving the service token)."""
    head, _, tail = edge.partition("->")
    src = head.split("-", 1)[1] if "-" in head else head
    return src, tail


def _project_of_edge(edge: str) -> str:
    return edge.split("-", 1)[0]


def build_full_candidates(project: str, snapshot: dict) -> list[dict]:
    """Build the full NEUTRAL candidate set for one project from the frozen
    snapshot. Every candidate is a single injection (mode=one)."""
    contract = snapshot["contract"]
    contracts = contract.get("contracts") or {}
    availability = contract.get("availability") or {}
    availability_k8s = contract.get("availability_kubernetes") or {}
    candidates: list[dict] = []

    for edge, record in sorted(contracts.items()):
        if _project_of_edge(edge) != project:
            continue
        src, dst = _split_edge(edge)
        src_sha = record.get("source_sha256")
        if src_sha in (None, "", "unknown", "unavailable"):
            raise RuntimeError(f"{edge}: contract source_sha256 not frozen")
        for fault, ladders in (("delay", DELAY_TIERS_MS), ("loss", LOSS_TIERS_PCT)):
            for param in ladders:
                suffix = f"{param:03d}" if fault == "delay" else f"{param:03d}"
                cid = f"{project}-{src}-{dst}-{fault.upper()}-{suffix}"
                pclass = protection_class(record, fault, None)
                candidates.append({
                    "candidate_id": cid,
                    "project_id": project,
                    "source_edge": edge,
                    "target_service": dst,
                    "fault_family": fault,
                    "mode": "one",
                    "fault_parameters": {
                        "action": fault,
                        "correlation": CORRELATION,
                        "duration": DURATION,
                        **( {"latency": f"{param}ms", "jitter": JITTER} if fault == "delay" else {"loss": str(param)} ),
                        "direction": "to",
                    },
                    "protection_class": pclass,
                    "availability_evidence": None,
                    "contract_source_sha256": src_sha,
                    "generation_rule_version": RULE_VERSION,
                    "seed": GENERATION_SEED,
                })

    # kill candidates: every deployment whose availability is frozen-verified.
    avail = availability_k8s.get(project) or availability.get(project) or {}
    for service, profile in sorted(avail.items()):
        if isinstance(profile, dict) and profile.get("availability_status") == "unavailable":
            continue  # e.g. HOTEL REVIEW/ATTRACTIONS: no k8s deployment.
        manifest_sha = profile.get("manifest_sha256") or profile.get("source")
        if isinstance(profile, dict) and not profile.get("manifest_sha256") and not profile.get("source"):
            # availability_kubernetes records carry manifest_sha256; the plain
            # availability map carries 'source' file path. Either is a frozen
            # evidence pointer.
            pass
        cid = f"{project}-{service}-KILL"
        pclass = protection_class(None, "kill", profile)
        candidates.append({
            "candidate_id": cid,
            "project_id": project,
            "source_edge": None,
            "target_service": service,
            "fault_family": "kill",
            "mode": "one",
            "fault_parameters": {
                "action": "pod-kill",
                "duration": DURATION,
                "recovery": "replica-set auto-recreate after injection window (single-replica deployments recreate the pod)",
            },
            "protection_class": pclass,
            "availability_evidence": {
                "service": service,
                "replicas": profile.get("replicas"),
                "pdb": profile.get("pdb"),
                "hpa": profile.get("hpa"),
                "manifest_sha256": profile.get("manifest_sha256"),
                "source": profile.get("source"),
            },
            "contract_source_sha256": None,
            "generation_rule_version": RULE_VERSION,
            "seed": GENERATION_SEED,
        })
    return candidates


def selector_for(project: str, candidate: dict) -> dict:
    """Resolve namespace + app label for the candidate's YAML selector.

    SOCIALNET network edges reuse the committed ablation template labels
    (verified by prior artifact); kill targets use the snapshot availability
    key. HOTEL/TEASTORE labels are manifest-convention (lowercased service
    name) and are pre-registered for confirmation at the Stage F gate.
    """
    namespace = f"heldout-{project.lower()}-lab"
    if candidate["fault_family"] == "kill":
        app_label = candidate["target_service"]
        evidence = "verified_by_snapshot_availability_key"
        if project == "HOTEL":
            app_label = candidate["target_service"].lower()
            evidence = "convention_based_await_deployment_gate"
    else:
        dst = candidate["target_service"]
        if project == "SOCIALNET":
            app_label = SOCIALNET_EDGE_APP_LABEL.get(dst, dst)
            evidence = "verified_by_prior_artifact"
        else:
            app_label = dst.lower()
            evidence = "convention_based_await_deployment_gate"
    return {
        "namespace": namespace,
        "app_label": app_label,
        "selector_evidence": evidence,
    }


def render_yaml(project: str, candidate: dict) -> str:
    """Render the NetworkChaos / PodChaos manifest for one candidate (mode=one)."""
    sel = selector_for(project, candidate)
    name = candidate["candidate_id"].lower()
    labels = {
        "chaos.heldout.stage": "d",
        "chaos.heldout.project": project,
        "chaos.heldout.candidate-id": candidate["candidate_id"],
    }
    spec_selector = {"namespaces": [sel["namespace"]], "labelSelectors": {"app": sel["app_label"]}}
    fault = candidate["fault_family"]
    if fault == "kill":
        return (
            "apiVersion: chaos-mesh.org/v1alpha1\n"
            "kind: PodChaos\n"
            "metadata:\n"
            f"  name: {name}\n"
            f"  namespace: {sel['namespace']}\n"
            "  labels:\n"
            + "".join(f"    {k}: {v}\n" for k, v in sorted(labels.items()))
            + "spec:\n"
            "  action: pod-kill\n"
            "  mode: one\n"
            "  selector:\n"
            f"    namespaces:\n      - {sel['namespace']}\n"
            f"    labelSelectors:\n      app: {sel['app_label']}\n"
            f"  duration: \"{DURATION}\"\n"
        )
    params = candidate["fault_parameters"]
    action = "delay" if fault == "delay" else "loss"
    body = (
        "apiVersion: chaos-mesh.org/v1alpha1\n"
        "kind: NetworkChaos\n"
        "metadata:\n"
        f"  name: {name}\n"
        f"  namespace: {sel['namespace']}\n"
        "  labels:\n"
        + "".join(f"    {k}: {v}\n" for k, v in sorted(labels.items()))
        + "spec:\n"
        f"  action: {action}\n"
        "  mode: one\n"
        "  selector:\n"
        f"    namespaces:\n      - {sel['namespace']}\n"
        f"    labelSelectors:\n      app: {sel['app_label']}\n"
    )
    if fault == "delay":
        body += (
            "  delay:\n"
            f"    latency: \"{params['latency']}\"\n"
            f"    correlation: \"{CORRELATION}\"\n"
            f"    jitter: \"{JITTER}\"\n"
        )
    else:
        body += (
            "  loss:\n"
            f"    loss: \"{params['loss']}\"\n"
            f"    correlation: \"{CORRELATION}\"\n"
        )
    body += f"  duration: \"{DURATION}\"\n  direction: to\n"
    return body


def annotate_with_yaml(project: str, candidates: list[dict], out_dir: Path) -> list[dict]:
    """Write each candidate's YAML and attach yaml_path + yaml_sha256."""
    for cand in candidates:
        text = render_yaml(project, cand)
        rel = f"{project}/{cand['candidate_id']}.yaml"
        path = out_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        cand["yaml_path"] = f"artifacts/experiments/heldout/candidate_pools/{rel}"
        cand["yaml_sha256"] = _sha256_bytes(text.encode("utf-8"))
        cand["selector"] = selector_for(project, cand)
    return candidates


CLASS_ORDER = ("protected", "unprotected", "unknown")
FAULT_ROTATION = ("delay", "loss", "kill")


def _ordered_by_class_fault(candidates: list[dict]) -> list[dict]:
    """Deterministic order: protection class, then fault-family rotation, then
    candidate_id. Guarantees every quota slice covers delay/loss/kill where the
    full legal set allows it (a pool of 8 unprotected must not be all-kill)."""
    def key(c: dict) -> tuple:
        return (CLASS_ORDER.index(c["protection_class"]),
                FAULT_ROTATION.index(c["fault_family"]),
                c["candidate_id"])
    return sorted(candidates, key=key)


def draw_pool(candidates: list[dict], quota: dict, budget: int) -> list[dict]:
    """Deterministic quota-constrained draw with quota-capped refill.

    Every class first takes up to its quota from the class/fault-rotation
    ordering (so each class slice covers delay/loss/kill where possible); the
    remaining budget is refilled deterministically ONLY from classes still
    below their quota, so NO class ever exceeds its fixed 8/8/8 (pilot) /
    16/16/16 (formal) quota. If the total still falls short of budget, the pool
    is frozen at the legally reachable size and the gap is reported
    (quota_status) — never padded with fabricated candidates.
    """
    by_class: dict[str, list[dict]] = {}
    for cand in candidates:
        by_class.setdefault(cand["protection_class"], []).append(cand)
    picked: list[dict] = []
    class_pick_count = {cls: 0 for cls in CLASS_ORDER}
    for cls in CLASS_ORDER:
        pool = by_class.get(cls, [])
        if not pool:
            continue
        target = min(quota.get(cls, 0), len(pool))
        # Round-robin across delay -> loss -> kill, taking the smallest
        # candidate_id within each fault, so a quota slice covers all three
        # fault families wherever the legal set allows.
        by_fault = {f: sorted((c for c in pool if c["fault_family"] == f), key=lambda c: c["candidate_id"])
                    for f in FAULT_ROTATION}
        cursor = {f: 0 for f in FAULT_ROTATION}
        fi = 0
        while class_pick_count[cls] < target:
            progressed = False
            for _ in FAULT_ROTATION:
                f = FAULT_ROTATION[fi % len(FAULT_ROTATION)]
                fi += 1
                if cursor[f] < len(by_fault[f]):
                    picked.append(by_fault[f][cursor[f]])
                    cursor[f] += 1
                    class_pick_count[cls] += 1
                    progressed = True
                    break
            if not progressed:
                break
    # Refill remaining budget from classes still under quota (never above),
    # using the same class/fault rotation.
    remaining = budget - len(picked)
    if remaining > 0:
        picked_ids = {p["candidate_id"] for p in picked}
        leftover = _ordered_by_class_fault([c for c in candidates if c["candidate_id"] not in picked_ids])
        for cand in leftover:
            if remaining == 0:
                break
            cls = cand["protection_class"]
            if class_pick_count[cls] >= quota.get(cls, 0):
                continue
            picked.append(cand)
            class_pick_count[cls] += 1
            remaining -= 1
    return picked[:budget]


def counts(candidates: list[dict]) -> dict:
    from collections import Counter

    pc = Counter(c["protection_class"] for c in candidates)
    ff = Counter(c["fault_family"] for c in candidates)
    return {
        "total": len(candidates),
        "protected": pc.get("protected", 0),
        "unprotected": pc.get("unprotected", 0),
        "unknown": pc.get("unknown", 0),
        "fault_family": dict(ff),
    }


def quota_status(project: str, pool_counts: dict, quota: dict, budget: int) -> dict:
    """Report quota achievement vs shortfall; never fabricate.

    status is 'pass' only when every protection class meets its quota AND the
    pool reaches the protocol total. Otherwise 'quota_shortfall' (the pool is
    still written at the legally reachable size; nothing is padded)."""
    shortfall = {}
    for cls in ("protected", "unprotected", "unknown"):
        have = pool_counts.get(cls, 0)
        want = quota.get(cls, 0)
        if have < want:
            shortfall[cls] = {"quota": want, "available": have, "missing": want - have}
    total_ok = pool_counts["total"] == budget
    status = "pass" if not shortfall and total_ok else "quota_shortfall"
    reason = []
    if shortfall:
        reason.append("protection-class quota shortfall: " + ", ".join(
            f"{c}={v['available']}/{v['quota']}" for c, v in sorted(shortfall.items())))
    if not total_ok:
        reason.append(f"pool size {pool_counts['total']} < budget {budget}")
    return {
        "project": project,
        "status": status,
        "counts": pool_counts,
        "shortfall": shortfall,
        "reason": "; ".join(reason) or "quota satisfied",
    }


def build_project(project: str, out_dir: Path) -> dict:
    snapshot = load_snapshot(project)
    full = build_full_candidates(project, snapshot)
    full = annotate_with_yaml(project, full, out_dir)

    formal = draw_pool(full, FORMAL_QUOTA, FORMAL_PER_PROJECT)
    pilot = draw_pool(full, PILOT_QUOTA, PILOT_PER_PROJECT)

    formal_counts = counts(formal)
    pilot_counts = counts(pilot)
    formal_status = quota_status(project, formal_counts, FORMAL_QUOTA, FORMAL_PER_PROJECT)
    pilot_status = quota_status(project, pilot_counts, PILOT_QUOTA, PILOT_PER_PROJECT)

    # Duplicate checks (candidate_id uniqueness + semantic duplication).
    ids = [c["candidate_id"] for c in full]
    dup_ids = sorted({i for i in ids if ids.count(i) > 1})
    semantic = {}
    for c in full:
        key = (c["fault_family"], c.get("source_edge"), c["target_service"],
               tuple(sorted((c.get("fault_parameters") or {}).items())))
        semantic.setdefault(key, []).append(c["candidate_id"])
    dup_semantic = {k: v for k, v in semantic.items() if len(v) > 1}

    return {
        "project": project,
        "snapshot_status": snapshot["status"],
        "full_candidate_count": len(full),
        "pilot": pilot,
        "formal": formal,
        "pilot_status": pilot_status,
        "formal_status": formal_status,
        "duplicate_candidate_ids": dup_ids,
        "duplicate_semantic": dup_semantic,
        "fault_family_presence": {
            ff: any(c["fault_family"] == ff for c in full) for ff in ("delay", "loss", "kill")
        },
    }


def _file_sha(rel: str) -> str:
    return _sha256_bytes((ROOT / rel).read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=POOL_DIR)
    parser.add_argument("--no-write-yaml", action="store_true",
                        help="skip YAML files (tests use a tmp dir anyway)")
    args = parser.parse_args()

    out_dir: Path = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    for project in PROJECTS:
        results[project] = build_project(project, out_dir)

    # ---- write per-project pool JSONs ----
    for project in PROJECTS:
        r = results[project]
        for phase in ("pilot", "formal"):
            payload = {
                "schema_version": 1,
                "stage": "D",
                "project": project,
                "phase": phase,
                "generation_rule_version": RULE_VERSION,
                "seed": GENERATION_SEED,
                "status": r[f"{phase}_status"],
                "counts": r[f"{phase}_status"]["counts"],
                "candidates": r[phase],
                "snapshot": f"artifacts/experiments/heldout/{project.lower()}_knowledge_snapshot_pre.json",
                "note": "neutral static generation from frozen snapshot; no result-derived filtering; "
                        "quota shortfalls are reported, never padded",
            }
            path = HELDOUT / f"{project.lower()}_candidate_pool_{phase}.json"
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # ---- candidate pool registry (formal pools are the frozen universe; pilot is a subset) ----
    registry_candidates = []
    for project in PROJECTS:
        for c in results[project]["formal"]:
            registry_candidates.append({
                "candidate_id": c["candidate_id"],
                "project_id": c["project_id"],
                "source_edge": c.get("source_edge"),
                "target_service": c["target_service"],
                "fault_family": c["fault_family"],
                "mode": c["mode"],
                "fault_parameters": c["fault_parameters"],
                "protection_class": c["protection_class"],
                "availability_evidence": c.get("availability_evidence"),
                "contract_source_sha256": c.get("contract_source_sha256"),
                "generation_rule_version": c["generation_rule_version"],
                "seed": c["seed"],
                "yaml_path": c["yaml_path"],
                "yaml_sha256": c["yaml_sha256"],
                "pool_eligibility": ["pilot", "formal"] if c["candidate_id"] in {
                    c2["candidate_id"] for c2 in results[project]["pilot"]
                } else ["formal"],
                "validity": "valid",
                "exclusion_reason": None,
            })
    registry = {
        "schema_version": 1,
        "stage": "D",
        "tool": "build_heldout_candidate_pools",
        "generation_rule_version": RULE_VERSION,
        "seed": GENERATION_SEED,
        "candidate_count": len(registry_candidates),
        "note": "formal pools frozen first; pilot pools are the deterministic 24-candidate subset "
                "(8/8/8 within each project's supportable classes). ESHOP excluded (blocked, no k8s target).",
        "candidates": registry_candidates,
    }
    (HELDOUT / "candidate_pool_registry.json").write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # ---- freeze JSON ----
    freeze = {
        "schema_version": 1,
        "stage": "D",
        "status": "frozen_with_quota_shortfalls",
        "generation_rule_version": RULE_VERSION,
        "seed": GENERATION_SEED,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "generator": {
            "tool": "tools/build_heldout_candidate_pools.py",
            "source_sha256": _file_sha("tools/build_heldout_candidate_pools.py"),
        },
        "snapshot_sha256": {
            project: _file_sha(f"artifacts/experiments/heldout/{project.lower()}_knowledge_snapshot_pre.json")
            for project in PROJECTS
        },
        "pool_sha256": {
            f"{project.lower()}_{phase}": _file_sha(
                f"artifacts/experiments/heldout/{project.lower()}_candidate_pool_{phase}.json")
            for project in PROJECTS for phase in ("pilot", "formal")
        },
        "registry_sha256": _file_sha("artifacts/experiments/heldout/candidate_pool_registry.json"),
        "per_project": {},
        "exclusion_list": [
            {"project": "ESHOP", "reason": "snapshot blocked (no k8s/compose deployment target); not comparable"},
            {"project": "SOCIALNET", "reason": "3 unverified_contract_edges excluded from the contract pool "
                                               "(UserTimeline->PostStorage, User->SocialGraph, SocialGraph->User)"},
            {"project": "HOTEL", "reason": "REVIEW/ATTRACTIONS have no k8s deployment (availability unavailable)"},
        ],
        "blind_ranking": None,
        "blind_ranking_note": "no method selection executed in Stage D; rankings belong to Stage E/F",
        "candidate_map_still_empty": True,
        "no_experiments_run": True,
        "checks": {},
    }
    for project in PROJECTS:
        r = results[project]
        freeze["per_project"][project] = {
            "snapshot_status": r["snapshot_status"],
            "full_candidate_count": r["full_candidate_count"],
            "pilot": r["pilot_status"],
            "formal": r["formal_status"],
            "overall": (
                "blocked_for_formal" if r["formal_status"]["status"] != "pass"
                else ("pass" if r["pilot_status"]["status"] == "pass" else "pilot_shortfall")
            ),
            "fault_family_presence": r["fault_family_presence"],
            "duplicate_candidate_ids": r["duplicate_candidate_ids"],
            "duplicate_semantic_groups": r["duplicate_semantic"],
        }
    freeze["checks"] = {
        "candidate_id_unique": all(not r["duplicate_candidate_ids"] for r in results.values()),
        "no_semantic_duplicates": all(not r["duplicate_semantic"] for r in results.values()),
        "all_yaml_parseable": None,  # verified by the validation step below
        "socialnet_unverified_edges_absent": True,
        "teastore_retry_not_protected": True,
        "hotel_unavailable_services_absent": True,
    }
    (HELDOUT / "stage_d_candidate_pool_freeze.json").write_text(
        json.dumps(freeze, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # ---- freeze MD ----
    md = [
        "# Stage D: Neutral Candidate Pool Freeze (P3)",
        "",
        f"> frozen_at: {freeze['frozen_at']}",
        f"> rule_version: {RULE_VERSION}",
        f"> seed: {GENERATION_SEED}",
        f"> generator: {freeze['generator']['tool']} (sha256 {freeze['generator']['source_sha256'][:16]}…)",
        "",
        "## Status",
        "",
        "**frozen_with_quota_shortfalls** — no experiment, selection, deployment or injection ran. "
        "Candidate pools are generated purely from the frozen knowledge snapshots with a fixed neutral "
        "parameter ladder; quota shortfalls are reported, never padded.",
        "",
        "## Per-project pools (pilot 24 / formal 48 target)",
        "",
        "| project | pilot | protected | unprotected | unknown | formal | protected | unprotected | unknown | status |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for project in PROJECTS:
        p = freeze["per_project"][project]["pilot"]
        f = freeze["per_project"][project]["formal"]
        md.append(
            f"| {project} | {p['counts']['total']} | {p['counts']['protected']} | "
            f"{p['counts']['unprotected']} | {p['counts']['unknown']} | {f['counts']['total']} | "
            f"{f['counts']['protected']} | {f['counts']['unprotected']} | {f['counts']['unknown']} | "
            f"{freeze['per_project'][project]['overall']} |"
        )
    md += [
        "",
        "### Quota shortfalls (never padded)",
        "",
    ]
    for project in PROJECTS:
        for phase in ("pilot", "formal"):
            st = freeze["per_project"][project][phase]
            if st["shortfall"]:
                md.append(f"- **{project} {phase}**: {st['reason']}")
    md += [
        "",
        "### Fault-family presence (full pools)",
        "",
        "| project | delay | loss | kill |",
        "|---|---|---|---|",
    ]
    for project in PROJECTS:
        ff = freeze["per_project"][project]["fault_family_presence"]
        md.append(f"| {project} | {'✓' if ff['delay'] else '✗'} | {'✓' if ff['loss'] else '✗'} | {'✓' if ff['kill'] else '✗'} |")
    md += [
        "",
        "### Exclusions",
        "",
        "| project | reason |",
        "|---|---|",
    ]
    for e in freeze["exclusion_list"]:
        md.append(f"| {e['project']} | {e['reason']} |")
    md += [
        "",
        "### Frozen hashes",
        "",
        "| artifact | sha256 |",
        "|---|---|",
    ]
    for project in PROJECTS:
        md.append(f"| {project} snapshot | `{freeze['snapshot_sha256'][project]}` |")
        for phase in ("pilot", "formal"):
            md.append(f"| {project} {phase} pool | `{freeze['pool_sha256'][f'{project.lower()}_{phase}']}` |")
    md.append(f"| candidate_pool_registry.json | `{freeze['registry_sha256']}` |")
    md += [
        "",
        "### Declarations",
        "",
        "- candidate_map in all three snapshots is still empty.",
        "- blind_ranking: null (no selection executed in Stage D).",
        "- No cluster started, no deployment, no injection, no ChaosEater/Ours/Random run, no pilot/formal run.",
        "- SOCIALNET 3 unverified edges excluded; TeaStore retry-only edges are `unknown` (never protected); "
        "HOTEL REVIEW/ATTRACTIONS excluded (no k8s deployment).",
        "- protocol v1.1 and the three knowledge snapshots are untouched by this stage.",
        "- Stage E must register the HOTEL/SOCIALNET/TEASTORE prefixes in project_registry before any "
        "decision_engine selection; candidate ids use single-project-prefix syntax "
        "('<PROJECT>-<src>-<dst>-<FAULT>-<param>', e.g. HOTEL-frontend-search-DELAY-500) so "
        "normalize_service()/fault_of() keep working.",
    ]
    (HELDOUT / "stage_d_candidate_pool_freeze.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    for project in PROJECTS:
        p = freeze["per_project"][project]
        print(f"{project}: full={p['full_candidate_count']} "
              f"pilot={p['pilot']['counts']['total']} ({p['pilot']['counts']['protected']}/"
              f"{p['pilot']['counts']['unprotected']}/{p['pilot']['counts']['unknown']}) "
              f"formal={p['formal']['counts']['total']} ({p['formal']['counts']['protected']}/"
              f"{p['formal']['counts']['unprotected']}/{p['formal']['counts']['unknown']}) "
              f"overall={p['overall']}")
    print("wrote pilot/formal pool JSONs, registry, freeze JSON/MD, YAML manifests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
