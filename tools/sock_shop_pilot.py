"""Static contract and read-only preflight for a Sock Shop PodKill pilot."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.project_onboarding import validate_project_profile
from tools.rca_loop import _contains_sensitive_value


Runner = Callable[..., tuple[int, str, str]]


def _default_runner(args: list[str], timeout: int = 30, input_text: str | None = None) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            ["kubectl", *args],
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return completed.returncode, completed.stdout or "", completed.stderr or ""
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 124, "", str(exc)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write_contract(output_root: Path, contract: dict[str, Any]) -> None:
    output_root = Path(output_root)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"output {output_root} already exists and is not empty")
    output_root.mkdir(parents=True, exist_ok=True)
    contract_text = json.dumps(contract, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
    if _contains_sensitive_value(contract_text):
        raise ValueError("pilot contract contains sensitive values")
    (output_root / "contract.json").write_text(contract_text, encoding="utf-8")
    (output_root / "mutation.yaml").write_text(
        yaml.safe_dump(contract["mutation_manifest"], sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


def build_sock_shop_podkill_contract(
    *,
    manifest_path: Path,
    profile_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Freeze the single-replica front-end PodKill contract offline."""

    profile_result = validate_project_profile(_read_json(profile_path))
    if not profile_result["valid"]:
        raise ValueError("invalid Sock Shop project profile: " + "; ".join(profile_result["errors"]))
    profile = profile_result["profile"]
    namespace = str((profile.get("namespace_policy") or {}).get("allowed_namespaces", [""])[0]).strip()
    if namespace != "sock-shop-lab":
        raise ValueError("Sock Shop pilot requires namespace sock-shop-lab")
    oracle = next(iter(profile.get("business_oracles") or []), None)
    if not isinstance(oracle, dict) or str(oracle.get("entrypoint") or "") != "/" or str(oracle.get("success_contract") or "") != "http_200":
        raise ValueError("Sock Shop pilot requires the frozen GET / http_200 oracle")

    docs = [doc for doc in yaml.safe_load_all(Path(manifest_path).read_text(encoding="utf-8-sig")) if doc]
    target = next(
        (
            doc
            for doc in docs
            if doc.get("kind") == "Deployment"
            and (doc.get("metadata") or {}).get("name") == "front-end"
            and (doc.get("metadata") or {}).get("namespace") == namespace
        ),
        None,
    )
    if not isinstance(target, dict):
        raise ValueError("front-end deployment is missing from the frozen manifest")
    replicas = (target.get("spec") or {}).get("replicas")
    if replicas != 1:
        raise ValueError("Sock Shop PodKill pilot requires a single replica")
    selector = ((target.get("spec") or {}).get("selector") or {}).get("matchLabels") or {}
    if not isinstance(selector, dict) or not selector:
        raise ValueError("front-end deployment selector is required")
    if any(not isinstance(key, str) or not isinstance(value, str) or not key or not value for key, value in selector.items()):
        raise ValueError("front-end deployment selector must contain string labels")

    mutation_manifest = {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "PodChaos",
        "metadata": {
            "name": "chaosatlas-sock-shop-front-end-podkill-r1",
            "namespace": namespace,
            "labels": {"chaosatlas.dev/owner": "chaosatlas", "chaosatlas.dev/pilot": "sock-shop-front-end-podkill-r1"},
        },
        "spec": {
            "action": "pod-kill",
            "mode": "one",
            "selector": {"namespaces": [namespace], "labelSelectors": dict(sorted(selector.items()))},
        },
    }
    contract = {
        "schema_version": "chaosatlas-sock-shop-podkill-pilot-v1",
        "status": "static_ready",
        "project_id": profile["project_id"],
        "project_commit": profile["project_commit"],
        "namespace": namespace,
        "target": "deployment:front-end",
        "target_selector": dict(sorted(selector.items())),
        "source_manifest": str(Path(manifest_path).resolve()).replace("\\", "/"),
        "source_manifest_sha256": hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest(),
        "oracle": {
            "id": oracle.get("id"),
            "entrypoint": oracle.get("entrypoint"),
            "success_contract": "HTTP 200",
            "timeout_s": oracle.get("timeout_s", 5),
        },
        "recovery": profile["recovery"],
        "cleanup": {"resource_kind": "podchaos", "resource_name": mutation_manifest["metadata"]["name"], "namespace": namespace, "must_be_absent": True},
        "mutation_manifest": mutation_manifest,
        "live_execution": {"approval_required": True, "apply_allowed": False},
    }
    _write_contract(Path(output_root), contract)
    return contract


def attach_pilot_contract_to_case(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    """Attach a frozen pilot mutation to a pending case without changing verdict fields."""

    if not isinstance(case, dict) or not isinstance(contract, dict):
        raise ValueError("case and contract must be objects")
    if contract.get("project_id") != case.get("project_id"):
        raise ValueError("pilot contract project_id does not match case")
    if contract.get("project_commit") != case.get("project_commit"):
        raise ValueError("pilot contract project_commit does not match case")
    target = str((case.get("test_node") or {}).get("target") or "")
    if target != contract.get("target"):
        raise ValueError("pilot contract target does not match case target")
    namespace = str(contract.get("namespace") or "")
    mutation = contract.get("mutation_manifest")
    cleanup = contract.get("cleanup")
    if not namespace or not isinstance(mutation, dict) or not isinstance(cleanup, dict):
        raise ValueError("pilot contract requires namespace, mutation_manifest and cleanup")
    if (mutation.get("metadata") or {}).get("namespace") != namespace:
        raise ValueError("pilot mutation namespace does not match contract")
    enriched = deepcopy(case)
    enriched["namespace"] = namespace
    enriched["pilot_contract"] = {
        "schema_version": contract.get("schema_version"),
        "target": contract.get("target"),
        "oracle": deepcopy(contract.get("oracle") or {}),
    }
    enriched["cleanup_contract"] = deepcopy(cleanup)
    enriched.setdefault("test_node", {})["mutation_manifest"] = deepcopy(mutation)
    return enriched


def _kubectl_json(runner: Runner, args: list[str]) -> tuple[dict[str, Any] | None, str | None]:
    code, stdout, stderr = runner([*args, "-o", "json"], timeout=30)
    if code != 0:
        return None, (stderr or stdout).strip() or f"kubectl returned {code}"
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return None, f"invalid kubectl JSON: {exc}"
    return value if isinstance(value, dict) else None, None


def run_sock_shop_preflight(contract: dict[str, Any], *, runner: Runner | None = None) -> dict[str, Any]:
    """Run read-only cluster checks; never applies or deletes a resource."""

    runner = runner or _default_runner
    errors: list[str] = []
    namespace = str(contract.get("namespace") or "")
    target = str(contract.get("target") or "")
    if namespace != "sock-shop-lab" or target != "deployment:front-end":
        return {"status": "blocked", "apply_allowed": False, "errors": ["invalid Sock Shop pilot contract"]}
    ns, error = _kubectl_json(runner, ["get", "namespace", namespace])
    if error:
        errors.append(f"namespace check failed: {error}")
    deployment, error = _kubectl_json(runner, ["get", "deployment", "front-end", "-n", namespace])
    if error:
        errors.append(f"front-end deployment check failed: {error}")
    else:
        spec = deployment.get("spec") or {}
        status = deployment.get("status") or {}
        if spec.get("replicas") != 1:
            errors.append("front-end deployment is not single replica")
        if status.get("readyReplicas") != 1:
            errors.append("front-end deployment is not Ready")
    crd, error = _kubectl_json(runner, ["get", "crd", "podchaos.chaos-mesh.org"])
    if error:
        errors.append(f"PodChaos CRD check failed: {error}")
    pods, error = _kubectl_json(runner, ["get", "pods", "-n", namespace, "-l", "name=front-end"])
    if error:
        errors.append(f"front-end Pod check failed: {error}")
    elif not (pods.get("items") or []):
        errors.append("front-end target Pod is missing")
    return {
        "schema_version": "chaosatlas-sock-shop-preflight-v1",
        "project_id": contract.get("project_id"),
        "namespace": namespace,
        "target": target,
        "checks": {"namespace": ns is not None, "deployment": deployment is not None, "podchaos_crd": crd is not None, "target_pods": len((pods or {}).get("items") or [])},
        "status": "ready_for_approval" if not errors else "blocked",
        "apply_allowed": False,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    contract = build_sock_shop_podkill_contract(
        manifest_path=args.manifest,
        profile_path=args.profile,
        output_root=args.output,
    )
    print(json.dumps({"status": contract["status"], "output": str(args.output).replace("\\", "/"), "target": contract["target"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
