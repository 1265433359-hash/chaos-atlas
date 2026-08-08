# Selection comparison — replicate 3

Known discovered candidates (12): OB-PAYMENT-DELAY-2000, OB-PAYMENT-LOSS-100, OB-PRODUCTCATALOG-DELAY-500, OB-PRODUCTCATALOG-KILL, OTEL-EMAIL-DELAY-2000, OTEL-EMAIL-LOSS-100, OTEL-PAYMENT-DELAY-2000, OTEL-PAYMENT-LOSS-100, TT-BASIC-DELAY-100, TT-STATION-CPU-80, TT-STATION-DELAY-100, TT-STATION-DELAY-2000

Metrics: **known-positive recall@10** (fraction of known-weakness candidates selected) and **severity-weighted recall** (3=timeout/hang/cascade, 2=latency amplified, 1=weak).
Full U@10 is not computable until the remaining 8 candidates are executed with concluded findings.

| Method | Selected | Known hits | recall@10 | severity-weighted | Missed (severity) |
|---|---|---:|---:|---:|---|
| M0 random-template | 10 | 6 | 0.500 | 0.520 | OB-PAYMENT-DELAY-2000(2), OB-PAYMENT-LOSS-100(3), OTEL-EMAIL-DELAY-2000(2), OTEL-EMAIL-LOSS-100(3), TT-BASIC-DELAY-100(1), TT-STATION-DELAY-100(1) |
| M1 ChaosEater-adapter | 10 | 7 | 0.583 | 0.680 | OB-PRODUCTCATALOG-DELAY-500(2), OTEL-EMAIL-DELAY-2000(2), OTEL-PAYMENT-DELAY-2000(2), TT-BASIC-DELAY-100(1), TT-STATION-DELAY-100(1) |
| M3 graph-only | 10 | 10 | 0.833 | 0.840 | OTEL-EMAIL-LOSS-100(3), TT-STATION-CPU-80(1) |
| M4 ours-full | 10 | 10 | 0.833 | 0.840 | OTEL-EMAIL-LOSS-100(3), TT-STATION-CPU-80(1) |
| A0 ours-yaml-only | 10 | 10 | 0.833 | 0.880 | TT-STATION-DELAY-100(1), TT-STATION-DELAY-2000(2) |
| A1 ours-global-graph | 10 | 10 | 0.833 | 0.840 | OTEL-EMAIL-LOSS-100(3), TT-STATION-CPU-80(1) |
| A2 ours-local-graph | 10 | 10 | 0.833 | 0.840 | OTEL-EMAIL-LOSS-100(3), TT-STATION-CPU-80(1) |
| A3 ours-local-graph-runtime-gate | 10 | 10 | 0.833 | 0.840 | OTEL-EMAIL-LOSS-100(3), TT-STATION-CPU-80(1) |
| A4 ours-full-evidence-feedback | 10 | 10 | 0.833 | 0.840 | OTEL-EMAIL-LOSS-100(3), TT-STATION-CPU-80(1) |

Bias note: D_known was selected for execution by our earlier methodology (M4 lineage); M3/M4 recall is partly circular. M1 used no execution history and is the least biased signal. Unknown candidates count as exploration, never as misses.
