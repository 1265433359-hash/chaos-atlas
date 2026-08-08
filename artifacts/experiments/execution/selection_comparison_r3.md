# Selection comparison — replicate 3

Known discovered candidates (6): OB-PAYMENT-DELAY-2000, OB-PAYMENT-LOSS-100, OB-PRODUCTCATALOG-KILL, OTEL-PAYMENT-DELAY-2000, OTEL-PAYMENT-LOSS-100, TT-STATION-DELAY-100

Metric: **known-positive recall@10** = fraction of known-weakness candidates selected.
Full U@10 is not computable until the remaining 6 candidates are executed with concluded findings.

| Method | Selected | Known hits | recall@10 | Unknown selected (exploration) |
|---|---|---:|---:|---:|
| M0 random-template | 10 | 5 | 0.833 | 5 |
| M1 ChaosEater-adapter | 10 | 5 | 0.833 | 5 |
| M3 graph-only | 10 | 6 | 1.000 | 4 |
| M4 ours-full | 10 | 6 | 1.000 | 4 |

Bias note: D_known was selected for execution by our earlier methodology (M4 lineage); M3/M4 recall is partly circular. M1 used no execution history and is the least biased signal. Unknown candidates count as exploration, never as misses.
