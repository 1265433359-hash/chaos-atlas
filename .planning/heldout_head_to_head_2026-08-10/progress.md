# Progress

2026-08-10: v1.1 protocol corrections completed in the working tree. JSON parsing and diff checks pass. P0 is complete.

2026-08-10: Hotel intake remains blocked because the repository contains no Hotel source/manifest. No cluster, deployment, injection, download, or new experiment has been run. The next gate is a human decision on the Hotel source and nomination of two additional held-out projects; do not enter P2 or pilot before that decision.

2026-08-10: Hotel intake upgraded to ready_for_snapshot. Canonical source delimitrou/DeathStarBench @ 6ecb0970 (hotelReservation/, sparse checkout via WSL, outside repo, not committed). Static intake done: 10 business services, frontend->search/profile/recommendation + search->geo/rate edges, Jaeger observability, compose single-replica. hotel_knowledge_snapshot_pre.json created with status=blocked (five-source provenance all experiment-pre; provenance_completeness=partial because kubernetes replicas/PDB not yet verified per-file). P1b candidate list drafted (ESHOP, SOCIALNET, MEDIA) pending human approval. No cluster/deployment/injection/pilot/formal run.

2026-08-10: Audit fixes applied locally: candidate count downgraded to not_yet_constructed; Compose availability explicitly scoped away from Kubernetes; unavailable service/Kubernetes hashes are recorded instead of guessed; Hotel snapshot builder now fail-closes on SE/DP/JE hash drift. WSL source was unavailable during this rebuild, so the Hotel snapshot remains status=blocked and P2 is not passed.

2026-08-10: Stage A provenance was rechecked from WSL. Snapshot now records 33 source files, 8 verified Kubernetes business deployments, and REVIEW/ATTRACTIONS as Kubernetes-unavailable. Intake JSON/Markdown and builder are synchronized; P2 is complete for the documented supported scope. No candidate pool or experiment has started.

2026-08-10 (Stage B): Project selection completed (no fetch). Recommended ESHOP (low leakage, cross-stack .NET) + SOCIALNET (medium leakage, stripping rules defined) as the two additional held-out projects; MEDIA as backup (excluded from double-counting with SOCIALNET since same DeathStarBench infra). Knowledge-leakage audit: SE/DP/JE contain 0 hits for DeathStarBench/Hotel/SOCIALNET/MEDIA - baseline clean. Stripping rules: SOCIALNET/MEDIA project-specific contracts must be rebuilt from their own source; shared infra (dialer 120s) re-verified and marked shared_infra_deathstarbench. Needs human approval of canonical URLs before any fetch.
