# Sock Shop YAML confidence r4 protocol amendment

- Source baseline: `runtime-exec-r3`
- Affected report: `chaosatlas-ablation/net-delay-catalogue-rep-2`
- Change: increase `recovery-timeout` from `180` to `240` seconds only
- Unchanged: baseline count, washout seconds, washout stable successes, washout timeout, oracle, namespace, selector, and mutation content

## Rationale

The r3 failure was not an injection-window business failure. Chaos recovered and the resource was deleted, but the business recovery window expired before five consecutive post-recovery successes could be observed.

In the captured timeline, `/catalogue` returned HTTP 500 for a short period after the resource had already recovered. Extending the recovery budget by 60 seconds gives the same run enough time to separate:

1. injected-window effect
2. post-cleanup recovery
3. washout stability

This is a data-driven observation-budget adjustment, not a change to the mutation, oracle, or classification rules.
