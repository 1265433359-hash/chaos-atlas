from __future__ import annotations

import json
from pathlib import Path

from tools.kubernetes_evidence import KubernetesEvidenceCollector


def test_collect_pod_state_accepts_dns_prefixed_label_keys() -> None:
    pod_list = {
        "kind": "PodList",
        "items": [
            {
                "metadata": {
                    "name": "api-gateway-abc",
                    "namespace": "chaosatlas-p02",
                    "labels": {
                        "app.kubernetes.io/name": "api-gateway",
                        "app.kubernetes.io/part-of": "chaosatlas-p02",
                    },
                },
                "status": {"phase": "Running", "conditions": []},
            }
        ],
    }

    def runner(args, timeout=30, input_text=None):
        assert args[:2] == ["--context", "minikube"]
        return 0, json.dumps(pod_list), ""

    root = Path("artifacts/.test-kubernetes-evidence")
    root.mkdir(parents=True, exist_ok=True)
    collector = KubernetesEvidenceCollector(
        root=root,
        allowed_namespaces={"chaosatlas-p02"},
        runner=runner,
        kube_context="minikube",
    )

    evidence = collector.collect_pod_state(
        namespace="chaosatlas-p02",
        selector={
            "app.kubernetes.io/name": "api-gateway",
            "app.kubernetes.io/part-of": "chaosatlas-p02",
        },
        claim_scope="deployment:api-gateway",
        evidence_id="p02-pod-state",
    )

    assert evidence["polarity"] == "supports"
    assert evidence["satisfies"] == ["ready_pods"]


def test_collect_events_can_scope_to_mutation_object() -> None:
    event_list = {"kind": "EventList", "items": []}
    calls = []

    def runner(args, timeout=30, input_text=None):
        calls.append(args)
        return 0, json.dumps(event_list), ""

    root = Path("artifacts/.test-kubernetes-events")
    root.mkdir(parents=True, exist_ok=True)
    collector = KubernetesEvidenceCollector(
        root=root,
        allowed_namespaces={"chaosatlas-p02"},
        runner=runner,
        kube_context="minikube",
    )

    evidence = collector.collect_events(
        namespace="chaosatlas-p02",
        claim_scope="deployment:api-gateway",
        evidence_id="p02-pod-events",
        involved_object_name="atlas-live-r3-pod-kill",
    )

    assert evidence["polarity"] == "supports"
    assert "--field-selector" in calls[0]
    selector_index = calls[0].index("--field-selector")
    assert calls[0][selector_index + 1] == "involvedObject.name=atlas-live-r3-pod-kill"
