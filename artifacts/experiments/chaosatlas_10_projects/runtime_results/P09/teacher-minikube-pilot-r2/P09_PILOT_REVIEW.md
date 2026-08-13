# P09 API PodKill Pilot Review

- Context: `minikube`
- Namespace: `chaosatlas-p09`
- Candidate: `P09-api-pod_kill-01`
- Runtime target: `Deployment/api`
- Fault: `PodChaos` `pod-kill`, mode `one`
- Report: `rep-1.json`
- Status: `completed`
- Human review: `pending`

## Evidence Review

The pre-injection baseline produced 5 consecutive HTTP 200 responses from the
API `/health` endpoint. Chaos Mesh selected and injected one API Pod. The API
Pod UID changed from `cd255385-32e3-43bf-9375-49c0bb514e9e` to
`68d0dd67-e6e7-425e-ad40-f057e974207f`, which confirms that the selected Pod
was replaced rather than merely observed through a transient status change.

The PodChaos resource was deleted and its absence was explicitly confirmed.
The replacement API Pod became Ready for 3 consecutive checks, all six P09
Deployments returned to their desired Ready/Available/Updated counts, and the
washout produced 10 consecutive HTTP 200 responses. The report recorded no
remaining PodChaos, NetworkChaos, or StressChaos object in `chaosatlas-p09`.

The mutation SHA-256 recorded by `rep-1.json` and the provenance file matches
the actual mutation file:

`5960fc92b648307b8a0567106f00b555d51bb857b64554fc2d17a5f7482ac9c8`

## Bounded Conclusion

This pilot confirms that the frozen API PodKill candidate can be mapped to the
P09 Kubernetes deployment, injected once, cleaned up, and followed by stable
deployment and `/health` recovery. It supersedes the earlier gate statement
that no executable P09 mutation was available.

The oracle exercised only `/health`. It did not execute a user workflow,
background job, plugin operation, model call, or data-integrity assertion.
Accordingly, this evidence does not establish end-to-end business resilience,
request continuity during the kill interval, or correctness of queued work.
It is one bounded pilot and is not a formal multi-arm experiment result.

No external model or credential was used. No knowledge-base entry was changed.
Human review remains `pending`.
