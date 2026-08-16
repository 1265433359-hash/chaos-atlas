# ChaosAtlas Paper Mainline and Historical Freeze

## Goal

Align the repository's paper-facing narrative with the confirmed research
mainline while preserving every historical artifact at its existing path.

## Confirmed Mainline

The paper-facing story has four stages:

1. Build the initial ChaosAtlas architecture around TestNode, local impact
   slices, applicability gates, bounded injection, evidence classification, and
   a knowledge base.
2. Validate the architecture's real issue-discovery capability on three real
   microservice projects: Online Boutique, OpenTelemetry Demo, and Sock Shop.
3. Improve the method and run a real Sock Shop ablation: the complete method
   uses the knowledge base, while the ablation removes the knowledge view. The
   current user-confirmed headline is 114 full-method hypotheses with 70 not
   yet injected and 10 discovered issues, versus 12 ablation hypotheses and 2
   discovered weaknesses. The machine-readable execution ledger remains the
   authority for exact denominators, repetition status, and review state.
4. Run a future formal comparison against the complete official ChaosEater
   method. Existing adapter and historical ChaosEater artifacts are not this
   experiment.

## Frozen Historical Material

Same-candidate-pool/preselected-candidate experiments, historical
ChaosEater-adapter comparisons, old Sock Shop pilots, and superseded summary
numbers remain available for audit but are not paper-mainline evidence. They
are marked as frozen rather than moved, renamed, deleted, or rewritten.

## Evidence Rules

- Mainline claims must link to the smallest machine-readable runtime or
  discovery artifact and then to a human-readable review.
- Generated hypotheses, not-injected candidates, completed injections, observed
  issues, stable weaknesses, and confirmed root causes are separate quantities.
- `human_review=pending` and `knowledge_base_updated=false` remain visible until
  human review is complete.
- A business issue/weakness observation is not automatically an internal root
  cause claim.
- ChaosEater remains future work until the official full method completes a
  fair real deployment and review.

## Non-Goals

- Do not delete or physically relocate experiment artifacts.
- Do not reuse same-pool percentages as the primary evaluation.
- Do not convert historical or pending artifacts into validated knowledge cards.
- Do not claim universal superiority from the three-project or Sock Shop
  evidence.
