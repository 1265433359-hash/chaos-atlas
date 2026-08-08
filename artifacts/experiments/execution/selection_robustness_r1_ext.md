# Selection robustness — replicate 1

## B1: bootstrap CI (baseline schema 3/2/1, n=1000)

| Method | mean w-recall | 95% CI |
|---|---:|---:|
| M0 | 0.525 | 0.263–0.789 |
| M1 | 0.654 | 0.368–0.921 |
| M3 | 0.551 | 0.316–0.816 |
| M4 | 0.551 | 0.316–0.816 |
| A0 | 0.579 | 0.342–0.842 |
| A1 | 0.551 | 0.316–0.816 |
| A2 | 0.551 | 0.316–0.816 |
| A3 | 0.551 | 0.316–0.816 |
| A4 | 0.551 | 0.316–0.816 |

## B1: pairwise difference CI (M1 minus other)

| Pair | mean diff | 95% CI | 5% significant |
|---|---:|---:|---|
| M1-vs-M3 | 0.102 | -0.263–0.474 | False |
| M1-vs-M4 | 0.102 | -0.263–0.474 | False |
| M1-vs-M0 | 0.128 | -0.237–0.500 | False |

## B2: weight-schema sensitivity

| Schema | 3-2-1 | 5-2-1 | 4-3-1 | 3-1-0 | 2-2-1 |
|---|---|---|---|---|---|
| 3-2-1 | M1 > A0 > M3 > M4 > A1 > A2 > A3 > A4 > M0 |
| 5-2-1 | M1 > A0 > M0 > M3 > M4 > A1 > A2 > A3 > A4 |
| 4-3-1 | M1 > A0 > M3 > M4 > A1 > A2 > A3 > A4 > M0 |
| 3-1-0 | M1 > A0 > M0 > M3 > M4 > A1 > A2 > A3 > A4 |
| 2-2-1 | M1 > M3 > M4 > A0 > A1 > A2 > A3 > A4 > M0 |

**Rank order stable across schemata: False**
