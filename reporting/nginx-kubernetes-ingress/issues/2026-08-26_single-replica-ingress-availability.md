# nginx-ingress 单副本导致 Pod 重启期间入口路由短暂不可用

## Title

`nginx-ingress` 单副本在 Pod 重启期间会造成入口路由短暂不可用

## Summary

在隔离的 Kubernetes namespace 中，`nginx-ingress` Deployment 当前配置为单副本。对该 Deployment 执行一次受控 `PodChaos pod-kill` 后，独立 HTTP Oracle 的首个观测请求无法连接；Pod 被替换并恢复 Ready 后，后续请求恢复 HTTP 200。使用两个不同 seed 的独立运行重复得到相同现象。该结果说明入口层没有可用的并行副本来覆盖 Pod 替换窗口。

## Environment

- Repository: `nginx/kubernetes-ingress`
- Branch / commit pinned: `f92a24e4fd2b52c72739c4a1f4f9bb6424bf5731`
- Deployment (isolated lab): Kubernetes context `chaosatlas-improvement`, namespace `chaosatlas-nginx-ingress`
- Workload: `deployment/nginx-ingress`, image `nginx/nginx-ingress:5.5.4`, replicas `1`
- Chaos Mesh: `PodChaos`, `action=pod-kill`, `mode=one`

## Evidence

### 1. Static evidence

Live inventory records `deployment/nginx-ingress` with `desired_replicas=1`; the Service selects the same `app=nginx-ingress` label. The Ingress route `fixture-route` routes the test host to `fixture-backend`.

### 2. Runtime evidence

Evidence directories:

- `artifacts/policy-rollout/nginx-ingress-registry-guarded-20260826-r3-budget10/runs/server-deployment-46f154f24e1db2da85adebbf-pod_kill`
- `artifacts/policy-rollout/nginx-ingress-podkill-independent-20260826-r1`

| Phase | Metric | Result |
|---|---|---|
| Baseline | HTTP Oracle | 10/10 HTTP 200 in both runs |
| Injected | First observation | Port-forward failed because the selected Pod was Pending/not running |
| Recovered | Subsequent observation | HTTP 200 restored; replacement Pod Ready; stable checks=2 |
| Cleanup | Chaos resource | PodChaos deletion verified absent in both runs |

Both runs have valid lifecycle attestations: baseline, injection, observation, recovery, cleanup and independent Oracle are all true. RCA is bounded to `deployment/service boundary`; no source-level root cause is claimed.

## Reproduction

```bash
kubectl --context chaosatlas-improvement apply -f podchaos.yaml
# podchaos.yaml: namespace=chaosatlas-nginx-ingress,
# selector labelSelectors app=nginx-ingress, action=pod-kill, mode=one

# During the replacement window, repeatedly request:
curl -H "Host: nginx-fixture.local" http://<nginx-ingress-endpoint>/

# Verify recovery and remove the experiment resource:
kubectl --context chaosatlas-improvement -n chaosatlas-nginx-ingress get pods -l app=nginx-ingress
kubectl --context chaosatlas-improvement -n chaosatlas-nginx-ingress delete podchaos <name>
```

## Impact

- A single controller Pod disruption creates a short availability gap for the ingress route.
- Any traffic relying on this controller can observe connection failure during Pod replacement.
- The experiment did not show data loss or a persistent outage; recovery was automatic after replacement.

## Suggested fix

Consider running at least two Ready `nginx-ingress` replicas with appropriate scheduling separation and disruption policy, then verify that one-Pod disruption preserves the business Oracle. If single-replica operation is intentional for a constrained deployment, document the expected availability gap and operational trade-off.

## Notes

- This is a runtime availability finding, not a CVE or source-code defect claim.
- The two runs share the same project, target and service-boundary causal identity but use different run identities and Pod UIDs.
- ChaosAtlas has not submitted this issue externally; user review is required before submission.
