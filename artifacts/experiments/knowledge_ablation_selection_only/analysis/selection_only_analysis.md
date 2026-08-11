# Selection-Only Analysis

Status: **complete**

Valid selection records: 36/36

This report uses only the out-of-band static protection oracle. It does not measure runtime weakness discovery, recall, RCA, or unique issue yield.

| Condition | Valid seeds | Protected waste | Unprotected selection |
|---|---:|---:|---:|
| ESHOP::LLM-blind::formal | 3 | 0.000 | 0.167 |
| ESHOP::LLM-blind::pilot | 3 | 0.000 | 0.250 |
| ESHOP::LLM-generic::formal | 3 | 0.000 | 0.200 |
| ESHOP::LLM-generic::pilot | 3 | 0.000 | 0.333 |
| ESHOP::LLM-partial-pre::formal | 3 | 0.000 | 0.333 |
| ESHOP::LLM-partial-pre::pilot | 3 | 0.000 | 0.500 |
| SOCIALNET::LLM-blind::formal | 3 | 0.433 | 0.567 |
| SOCIALNET::LLM-blind::pilot | 3 | 0.625 | 0.375 |
| SOCIALNET::LLM-full-pre::formal | 3 | 0.033 | 0.967 |
| SOCIALNET::LLM-full-pre::pilot | 3 | 0.042 | 0.958 |
| SOCIALNET::LLM-generic::formal | 3 | 0.200 | 0.800 |
| SOCIALNET::LLM-generic::pilot | 3 | 0.042 | 0.958 |

## Paired Differences vs Blind

Positive protected-waste differences are worse; positive unprotected-selection differences indicate more statically unprotected candidates selected. These are descriptive seed-level comparisons, not cross-project inference.

| Project | Phase | Arm | Median delta protected waste | Median delta unprotected selection | Median delta tokens |
|---|---|---|---:|---:|---:|
| ESHOP | pilot | LLM-generic | 0.000 | 0.125 | 4070 |
| ESHOP | pilot | LLM-partial-pre | 0.000 | 0.250 | 5853 |
| ESHOP | formal | LLM-generic | 0.000 | 0.000 | 2753 |
| ESHOP | formal | LLM-partial-pre | 0.000 | 0.200 | 4430 |
| SOCIALNET | pilot | LLM-full-pre | -0.500 | 0.500 | 16254 |
| SOCIALNET | pilot | LLM-generic | -0.500 | 0.500 | 8122 |
| SOCIALNET | formal | LLM-full-pre | -0.400 | 0.400 | 11449 |
| SOCIALNET | formal | LLM-generic | -0.100 | 0.100 | 5419 |
