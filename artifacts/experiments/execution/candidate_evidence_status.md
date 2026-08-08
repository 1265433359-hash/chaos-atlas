# Candidate evidence status (ground-truth backbone)

Only candidates whose OWN mutation was executed with a concluded classification count toward discovery.
Same-service card conclusions without that candidate's mutation are inherited references, not candidate evidence.
Not-executed candidates are reported as `not_executed` and never counted as hit or miss.

| Candidate | Executed | Own discovery conclusion | Same-service card root cause |
|---|---|---|---|
| TT-STATION-DELAY-100 | yes | response_observed | - |
| TT-STATION-DELAY-2000 | no | not_executed | - |
| TT-STATION-CPU-80 | no | not_executed | - |
| TT-BASIC-DELAY-100 | no | not_executed | - |
| OB-PAYMENT-DELAY-2000 | yes | grpc_response_observed | missing_timeout_on_downstream_call |
| OB-PAYMENT-LOSS-100 | yes | grpc_error_observed | missing_timeout_on_downstream_call |
| OB-PRODUCTCATALOG-KILL | yes | client_timeout_observed | missing_timeout_and_fallback_on_core_data_path |
| OB-PRODUCTCATALOG-DELAY-500 | no | not_executed | missing_timeout_and_fallback_on_core_data_path |
| OTEL-PAYMENT-DELAY-2000 | yes | grpc_response_observed | missing_timeout_on_downstream_calls |
| OTEL-PAYMENT-LOSS-100 | yes | grpc_error_observed | missing_timeout_on_downstream_calls |
| OTEL-EMAIL-DELAY-2000 | no | not_executed | - |
| OTEL-EMAIL-LOSS-100 | no | not_executed | - |

Candidates with own discovery evidence: 6
Not executed: 6 (TT-STATION-DELAY-2000, TT-STATION-CPU-80, TT-BASIC-DELAY-100, OB-PRODUCTCATALOG-DELAY-500, OTEL-EMAIL-DELAY-2000, OTEL-EMAIL-LOSS-100)
