"""Project contexts for the ChaosEater adapter (information tier I0).

ChaosEater's FaultScenarioAgent is fed a k8s overview and steady states. To
keep the adapter at information tier I0 (YAML-visible facts only), these
contexts are derived from the candidate pool itself — service names, edges,
and declared intensities — plus a generic steady-state declaration. They never
reference our runtime measurements or knowledge-card conclusions, so M1 does
not benefit from I1/I2 evidence that M0/M3/M4 tiers are meant to separate.
"""

from __future__ import annotations

from typing import Any

PROJECT_NAMES = {
    "train-ticket": "Train Ticket (Spring Cloud microservices benchmark)",
    "online-boutique": "Online Boutique (Google microservices-demo)",
    "otel-demo": "OpenTelemetry Demo (checkout-based microservices demo)",
}

# Generic steady-state declaration: only manifest-visible contracts, no measured
# thresholds, no knowledge-card conclusions.
STEADY_STATES_TEXT = """\
Steady states declared by the manifests:
- Every selected service must preserve its response contract (success response
  with the documented fields) while the fault is injected and after recovery.
- Latency-sensitive edges are expected to stay within any timeout or deadline
  the manifests declare; where no timeout is declared, the edge is expected to
  remain responsive.
- Service availability must be maintained at the replica count declared in the
  deployment (no cascading unavailability beyond the injected target).
"""


def service_topology(project_id: str, candidates: list[dict[str, Any]]) -> list[str]:
    services: list[str] = []
    edges: list[str] = []
    for candidate in candidates:
        if candidate.get("project_id") != project_id:
            continue
        service = str(candidate.get("service", ""))
        edge = str(candidate.get("edge", ""))
        if service and service not in services:
            services.append(service)
        if edge and edge not in edges:
            edges.append(edge)
    return services, edges


def build_user_input(project_id: str | None, candidates: list[dict[str, Any]]) -> str:
    """Build the k8s overview prompt.

    With a project id, only that project's services/edges are listed (the
    ChaosEater single-system view). With None, every service/edge in the pool
    is listed under the three demo projects, so a pool-wide selection can be
    made in one call.
    """
    if project_id is None:
        lines = ["The system under test is a bundle of three demo microservices systems deployed in isolated lab namespaces:"]
        for pid, name in PROJECT_NAMES.items():
            services, edges = service_topology(pid, candidates)
            lines.append(
                f"- {name}: services {', '.join(sorted(services))}; "
                f"pool edges {', '.join(sorted(edges))}."
            )
        lines.append(
            "Fault injections are scoped to the candidate pool services/edges above "
            "and must not touch anything outside the pool."
        )
        return "\n".join(lines)
    services, edges = service_topology(project_id, candidates)
    name = PROJECT_NAMES.get(project_id, project_id)
    lines = [
        f"Project: {name} (deployed in an isolated lab namespace).",
        f"Services relevant to the candidate pool: {', '.join(sorted(services))}.",
        f"Inter-service edges in the pool: {', '.join(sorted(edges))}.",
        "Fault injections are scoped to these services/edges and must not touch anything outside the pool.",
    ]
    return "\n".join(lines)


def build_steady_states(project_id: str) -> str:
    return STEADY_STATES_TEXT
