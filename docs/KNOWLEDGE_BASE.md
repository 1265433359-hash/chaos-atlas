# Knowledge Base Guide

The knowledge base is a retrieval and decision artifact, not a list of
conclusions. A card records what was tested, what was actually observed, what
remains unknown, and when the selector must stop repeating the same experiment.

## Card Layout

Each project knowledge base has an `index.json`, one JSON/Markdown pair per
card, and a generated `validation_report.json`:

```text
artifacts/<project>/knowledge_base/
  index.json
  KB-<project>-<family>-<path>-NNN.json
  KB-<project>-<family>-<path>-NNN.md
  validation_report.json
```

The validator requires the card identity, project commit, test-node descriptor,
test-node-centered graph, four-layer validation, and a non-empty `next_evidence`
list. The graph should distinguish static, runtime, hypothesis, and unreachable
edges.

## Four-Layer Validation

Cards follow the same gate used by the runners:

1. **Declaration:** the YAML parses and its test-node fields are meaningful.
2. **Resource:** selector/namespace/target exists in the isolated project.
3. **Business:** the workload and oracle are reachable and repeatable.
4. **Runtime:** injection, effect, observation, recovery, and cleanup are evidenced.

Only a card that reaches the runtime layer can support a defense or weakness
claim. A card may still be valuable when it stops at a blocked or unreachable
layer, but its status must say so.

## Retrieval Rules

Prefer exact matches on `family`, `operation`, target service, direction, and
oracle. Use project-wide or fault-family matches only as hypotheses. A matching
card with a `closed_runtime_boundary_no_reinjection` stop rule must prevent
automatic reinjection until new evidence changes the boundary.

Examples:

```powershell
python tools/query_knowledge_base.py --list
python tools/query_knowledge_base.py --family NetworkChaos --operation delay
python tools/query_knowledge_base.py --root-cause missing_timeout
```

The decision engine (`tools/decision_engine.py`) is the auditable rule layer.
The LLM is an optional decision enhancer and must not silently bypass hard
filters, frozen snapshots, or the applicability gate.

## Updating a Card

1. Preserve the previous version and add a new versioned card or an explicit
   audit entry; do not erase contradictory evidence.
2. Link every new claim to a run, source span, manifest, log, trace, or oracle.
3. Record the change reason, confidence, protocol/environment fingerprint, and
   next evidence.
4. Run `tools/validate_knowledge_base.py` for the affected project.
5. Add the validator result and the card ID to the session/protocol ledger.

The automatic backfill tool is useful for evidence linkage, but it is not
allowed to auto-delete or auto-rewrite rules. Contested selection, defense, and
judgment rules require human adjudication.

## Ablation Track Status

The knowledge-base selection ablation is currently **parked**. Its protocol,
snapshots, prompts, selection records, and leakage-audit artifacts are retained
for a later continuation, but Gate 1 onward, independent runtime truth, and
project-clustered statistical analysis are not complete. The current cards and
static selection records must not be presented as evidence that the knowledge
base improves LLM selection.

The same boundary applies to the unfinished final method head-to-head
comparison. Existing comparison artifacts remain useful as descriptive and
audit material, not as a completed superiority evaluation.

## Sensitive Data

Cards must use redacted references for secrets, credentials, tokens, and private
endpoints. The validator performs a warning-level sensitive-value scan; a clean
validator report is necessary but not sufficient for publication review.

## RCA Loop Artifacts

The automated RCA loop (`tools/rca_loop.py`, `tools/sock_shop_rca.py`) writes
its machine-generated products under per-project `rca_loop/` directories (for
example `artifacts/sock-shop/rca_loop/`). These are project-local investigation
artifacts and are NOT formal knowledge-base cards:

- `rca_loop/knowledge_drafts/` holds provisional drafts. They are queryable only
  via the explicit `--rca-root` option of `tools/query_knowledge_base.py` and
  are never counted in the formal card totals.
- The three statuses `weakness_status`, `rca_status`, and `knowledge_status`
  must be interpreted independently. `weakness_status=confirmed` with
  `rca_status=bounded` is a valid and expected outcome: the failure is real and
  its affected boundary is known, but the internal mechanism is unproven.
- `bounded` is an allowed successful RCA outcome. It must not be promoted to
  `confirmed` without complete required evidence plus a discriminating action,
  and an HTTP abort may only support a service-boundary propagation claim -
  never an automatic `missing_timeout` naming - without source/config evidence.
- Provisional drafts may only generate `discriminate`/`reproduce` regression
  intents. Only `knowledge_status=local_reusable` cards may influence this
  project's high-impact candidate ranking through the decision engine's
  `rca_snapshot` parameter; `provisional` and `cross_project_pending` cards are
  explanation-only, and `contested` cards generate no executable intents.
- Cross-project reuse still requires the existing feedback protocol
  (`tools/feedback_protocol.py`); the RCA module never bypasses review,
  round, or order isolation.
- Counter-evidence demotes a card to `provisional` or `contested` but never
  deletes the original card, its evidence references, or prior snapshot hashes.
