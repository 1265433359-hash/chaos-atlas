# Sock Shop Issue Review Pack

> Status: READY FOR USER REVIEW. Nothing in this pack has been submitted to GitHub.
> Scope: three independently bounded resilience/design candidates selected from
> the Full runtime findings and the RCA closure artifacts.

## Review decision requested

Please review each draft and choose one disposition:

- `approve-draft`: wording is acceptable for a normal issue
- `revise`: keep the candidate but change title, scope, or evidence
- `hold-evidence-only`: retain the finding for the paper/audit, do not submit
- `reject-design-choice`: the observed behavior is intentional for this demo

## Candidates

| ID | Draft | Evidence status | Recommended disposition |
|---|---|---|---|
| SS-ISSUE-001 | `2026-08-24_front-end-single-replica-availability-degradation.md` | Two independent live runs; deployment boundary confirmed | `approve-draft` only as a resilience/design concern |
| SS-ISSUE-002 | `2026-08-24_catalogue-db-single-replica-catalogue-outage.md` | RCA closure: 54 outage samples versus 10 defended counterfactual samples | `approve-draft` as a deployment resilience question |
| SS-ISSUE-003 | `2026-08-24_front-end-catalogue-abort-no-graceful-degradation.md` | RCA closure: 68 business-oracle failures, cleanup clean | `revise` or `hold-evidence-only`; source-level mechanism is not established |

## Why these three

The 15 Full stable families collapse to 10 problem surfaces. The three drafts
below are not a new count of 15 issues: they are the only candidates with a
separate evidence chain, a bounded claim, and a plausible remediation question.
Other PodKill, network, and resource-pressure families remain evidence-only
until an independent source/config contract and a project expectation are
identified.

## Shared boundaries

- The deployment snapshot is pinned by the runtime RCA commit
  `6e83eb6ffdf1bce43e332337a3bb0fc40327d039`; older RCA-loop files use the
  internal alias `sock-shop-fixture-commit` and are linked only as evidence.
- The target is the archived Sock Shop deployment. The drafts therefore ask
  whether stronger resilience is intended; they do not claim a security defect
  or a production SLO violation.
- No GitHub CLI, remote API, or external submission was run.
- Review remains a human gate before any status changes from `draft`.

