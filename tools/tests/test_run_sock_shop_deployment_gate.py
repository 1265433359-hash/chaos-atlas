from tools.run_sock_shop_deployment_gate import build_rehearsal_mutation, deployment_health


def test_deployment_health_requires_every_desired_replica_available() -> None:
    payload = {
        "items": [
            {"metadata": {"name": "front-end"}, "spec": {"replicas": 1}, "status": {"availableReplicas": 1}},
            {"metadata": {"name": "orders"}, "spec": {"replicas": 1}, "status": {"availableReplicas": 0}},
        ]
    }
    blocked = deployment_health(payload)
    assert blocked["deployments_total"] == 2
    assert blocked["deployments_available"] == 1
    assert blocked["all_ready"] is False
    payload["items"][1]["status"]["availableReplicas"] = 1
    assert deployment_health(payload)["all_ready"] is True


def test_rehearsal_mutation_is_exactly_namespace_local_payment_podkill() -> None:
    mutation = build_rehearsal_mutation("sock-shop-runtime-gate-payment-kill")
    assert mutation["kind"] == "PodChaos"
    assert mutation["metadata"] == {
        "name": "sock-shop-runtime-gate-payment-kill",
        "namespace": "chaosatlas-sock-shop",
    }
    assert mutation["spec"]["mode"] == "one"
    assert mutation["spec"]["selector"] == {
        "namespaces": ["chaosatlas-sock-shop"],
        "labelSelectors": {"name": "payment"},
    }
