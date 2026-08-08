# Candidate evidence status (ground-truth backbone)

Only candidates whose OWN mutation was executed with a concluded classification count toward discovery.
Same-service card conclusions without that candidate's mutation are inherited references, not candidate evidence.
Not-executed candidates are reported as `not_executed` and never counted as hit or miss.

| Candidate | Executed | Own discovery conclusion | Same-service card root cause |
|---|---|---|---|
| TT-STATION-DELAY-100 | yes | response_observed | - |
| TT-STATION-DELAY-2000 | yes | response_observed | - |
| TT-STATION-CPU-80 | yes | response_observed | - |
| TT-BASIC-DELAY-100 | yes | response_observed | - |
| OB-PAYMENT-DELAY-2000 | yes | grpc_response_observed | missing_timeout_on_downstream_call |
| OB-PAYMENT-LOSS-100 | yes | grpc_error_observed | missing_timeout_on_downstream_call |
| OB-PRODUCTCATALOG-KILL | yes | client_timeout_observed | missing_timeout_and_fallback_on_core_data_path |
| OB-PRODUCTCATALOG-DELAY-500 | yes | response_observed | missing_timeout_and_fallback_on_core_data_path |
| OTEL-PAYMENT-DELAY-2000 | yes | grpc_response_observed | missing_timeout_on_downstream_calls |
| OTEL-PAYMENT-LOSS-100 | yes | grpc_error_observed | missing_timeout_on_downstream_calls |
| OTEL-EMAIL-DELAY-2000 | yes | grpc_response_observed | - |
| OTEL-EMAIL-LOSS-100 | yes | grpc_error_observed | - |

Candidates with own discovery evidence: 12
Not executed: 0 ()
