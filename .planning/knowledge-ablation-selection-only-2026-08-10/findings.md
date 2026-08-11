# Findings

## Initial state

- Phase 1 feasibility reports classify ESHOP as `deployment_unavailable` and SOCIALNET as `environment_blocked`.
- The corrected selection-only run is complete: 36/36 records are valid, and static-oracle analysis is descriptive only.
- TeaStore has a valid static snapshot but cannot pass runtime feasibility on the current machine because Docker is unreachable and `kind` is unavailable. This is an infrastructure blocker, not a project or method verdict.
- 18/30 frozen SOCIALNET delay/loss mutation YAML selectors do not match deployed Pod labels; frozen artifacts must not be edited in place.
- No LLM selection, formal injection, or runtime oracle result exists.
- ESHOP formal pool has 40 candidates; SOCIALNET formal pool has 30. The original formal-48 protocol is not conformant.

## Selection-only scope

Allowed endpoints: selected candidate IDs, static protection-oracle hit rate, protected-waste, unknown/unprotected selection counts, schema/duplicate/unknown-ID failures, token/call cost, and selection latency.

Forbidden endpoints: confirmed weakness, runtime recall, execution invalid-rate, evidence completeness, RCA accuracy, unique issue yield, and any claim of end-to-end fault-discovery improvement.

## Implementation issue

- First clean-bundle build attempt used the pilot seed for the formal source prompt and failed closed with `FileNotFoundError`; the script was corrected to use the first seed registered for each phase. No source artifact was overwritten.
- Second build attempt failed its own leakage gate because the audit-only `forbidden_fields_removed` list was placed inside the generated bundle. The list was moved to the external manifest/audit; no LLM call occurred.
- First post-run analysis invocation exposed a relative-path normalization bug in the analyzer. The selection outputs and ledger were unaffected; the analyzer was corrected to resolve the selection root before emitting repository-relative paths.
