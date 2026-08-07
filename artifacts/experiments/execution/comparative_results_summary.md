# Comparative Execution Summary

This report contains only runs with explicit baseline, injection, recovery, and cleanup evidence.

## Runtime Replicates

| Scenario | Replicates | Valid lifecycle | Observed result |
|---|---:|---:|---|
| TT station delay | 4 | 4/4 | response_preserved_latency_degradation |
| OB productcatalog kill | 4 | 4/4 | client_timeout_observed |
| OB payment delay | 4 | 4/4 | grpc_response_observed |
| OB payment loss | 4 | 4/4 | grpc_error_observed |
| OTel payment delay | 4 | 4/4 | grpc_response_observed |
| OTel payment loss | 4 | 4/4 | grpc_error_observed |

## Interpretation

- The six runtime scenarios each have four valid repetitions (r1-r4).
- K7 probe-restart evidence is reported separately as recovery amplification, not as a clean escape.
- The pilot gate table is an eligibility comparison; it must not be presented as a superiority score.

## Blockers

- HTTPChaos platform path: blocked (WSL2 Chaos Daemon lacks ebtables/tproxy prerequisite).
- Train Ticket order network-delay candidate: defer_unreachable_or_unproven_path (source graph does not reach the selected network target in the current lab).
- ChaosEater and FastFI external adapters: blocked_external_reproduction (official repositories could not be fetched in the current network environment).
