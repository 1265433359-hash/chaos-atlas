# Selection robustness — replicate 3

## B1: bootstrap CI (baseline schema 3/2/1, n=1000)

| Method | mean w-recall | 95% CI |
|---|---:|---:|
| M0 | 0.605 | 0.342–0.842 |
| M1 | 0.655 | 0.368–0.947 |
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
| M1-vs-M3 | 0.104 | -0.237–0.447 | False |
| M1-vs-M4 | 0.104 | -0.237–0.447 | False |
| M1-vs-M0 | 0.050 | -0.263–0.368 | False |

## B2: weight-schema sensitivity

| Schema | 3-2-1 | 5-2-1 | 4-3-1 | 3-1-0 | 2-2-1 |
|---|---|---|---|---|---|
| 3-2-1 | M1 > M0 > A0 > M3 > M4 > A1 > A2 > A3 > A4 |
| 5-2-1 | M1 > M0 > A0 > M3 > M4 > A1 > A2 > A3 > A4 |
| 4-3-1 | M1 > M0 > A0 > M3 > M4 > A1 > A2 > A3 > A4 |
| 3-1-0 | M1 > M0 > A0 > M3 > M4 > A1 > A2 > A3 > A4 |
| 2-2-1 | M0 > M1 > M3 > M4 > A0 > A1 > A2 > A3 > A4 |

**Rank order stable across schemata: False**
