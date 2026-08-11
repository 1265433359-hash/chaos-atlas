# Issue draft: Online Boutique - Payment probe behavior under injected delay

> Status: DRAFT - optional, lower priority.
> Target: https://github.com/GoogleCloudPlatform/microservices-demo
> Classification: probe configuration / resilience concern.

## Title

Online Boutique: paymentservice probe restarts the container after a 2-second delay

## Summary

The payment deployment configures a 1-second probe timeout. During a bounded 2-second network delay to the payment service, the probe failed and kubelet terminated the container with exit code 137. The order path recovered after the restart. This may be worth reviewing because a transient dependency delay resulted in a container restart in the test.

## Environment

- Repository: `GoogleCloudPlatform/microservices-demo`
- Commit: `9a4616e7`
- Manifest: `kubernetes-manifests/paymentservice.yaml`
- Runtime: isolated `online-boutique-lab`, Kubernetes 1.36.1, Chaos Mesh 2.8.3

## Evidence

The manifest sets the payment liveness/readiness probe `timeoutSeconds` to `1`. With a 2-second outbound delay injected toward `paymentservice`:

- probe failed;
- the container exited with code 137;
- Kubernetes restarted the container;
- the checkout path recovered after restart.

The same 100% loss experiment did not trigger a restart, so the behavior depends on how the probe request is affected by delay versus connection loss.

## Impact

Under similar conditions, transient latency may cause a payment container restart, adding recovery latency and potentially increasing disruption during an incident. Probe behavior may therefore contribute materially to the observed fault response.

## Suggested direction

Could the probe timeout and failure thresholds be checked against the intended payment-service startup and latency budget? Depending on the health-check contract, it may be worth considering one of the following:

1. Use a separate lightweight health endpoint.
2. Increase the probe timeout.
3. Use a more tolerant failure threshold to avoid restarting the container for transient downstream delay.

## Notes

This is a configuration concern rather than a confirmed universal bug. The appropriate values depend on the project's intended health-check contract.
