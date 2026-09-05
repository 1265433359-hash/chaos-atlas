# Helm chart appVersion remains 1.16.1 when deploying Dify 1.17.0 images

**Affected project:** Dify Helm chart and Kubernetes release metadata

**Suggested labels:** `bug`, `helm`, `release-management`, `kubernetes`

## Summary

The Helm chart metadata reports `appVersion: 1.16.1`, while the deployment values select Dify `1.17.0` images. The resulting Kubernetes resources retain an `app.kubernetes.io/version: 1.16.1` label even though the running API and web images are `1.17.0`.

This makes inventory, monitoring, alert routing, and incident investigation report an incorrect application version.

## Environment

- Helm chart: `dify-0.38.0`
- Chart `appVersion`: `1.16.1`
- API and web image tags: `1.17.0`
- Installation type: Self Hosted
- Kubernetes context: `chaosatlas-dify`
- Namespace: `dify-k8s-lab`

## Steps to Reproduce

1. Render or install the Dify chart with API and web image tags set to `1.17.0`.
2. Inspect the chart metadata and the `app.kubernetes.io/version` labels on the generated Deployments.
3. Compare those values with the image tags actually running in the Pods.

## Actual Behavior

The chart metadata and Kubernetes version labels report `1.16.1`, while the deployed API image is `langgenius/dify-api:1.17.0` and the configured application image tags are `1.17.0`.

## Expected Behavior

Chart metadata and generated application version labels should match the application version being released, or the chart should clearly distinguish chart metadata from an explicitly overridden image version. A release using `1.17.0` images should not silently advertise `1.16.1` as the application version.

## Impact

This can cause incorrect information in Kubernetes inventory, monitoring,
alerting, release audits, and incident investigation.

## Suggested Investigation

- Update `appVersion` as part of the Dify release process.
- Define whether `app.kubernetes.io/version` represents the chart application version or the selected image version.
- Add a Helm template test that compares the rendered version label with the configured application version.
- Document the supported override behavior when image tags are changed independently of the chart.

## Acceptance Criteria

- A Dify `1.17.0` deployment reports `1.17.0` consistently in chart metadata or explicitly documented release labels.
- Resource labels and image tags have an unambiguous relationship.
- CI catches stale `appVersion` values before a chart release.

## Reproduction Evidence

- Chart: `dify-0.38.0`
- Observed chart `appVersion`: `1.16.1`
- Observed API image: `langgenius/dify-api:1.17.0`
- Observed configured web image tag: `1.17.0`

This is a release metadata and deployment observability issue; it does not by itself indicate a runtime outage.
