# Sock Shop R5 去重后两臂证据审核

## 主结果

| 方法 | 稳定弱点 | 不稳定 | 非弱点 | 分母 | 稳定弱点率 | Wilson 95% CI |
|---|---:|---:|---:|---:|---:|---:|
| native-full | 2 | 1 | 8 | 11 | 18.18% | 5.14% - 47.70% |
| ChaosAtlas-ablation | 2 | 0 | 9 | 11 | 18.18% | 5.14% - 47.70% |

Fisher 双侧精确检验：odds ratio = 1，p = 1。

两臂在本次冻结主样本中的稳定弱点率相同。小样本且区间很宽，不能据此宣称两种方法具有普遍性优劣。

## 统计口径

- 两次均为 `weakness_observed` 才计为稳定弱点。
- 仅一次复现单列为不稳定，不计入稳定弱点分子。
- 分母仅包含 gate 通过、两次生命周期完成且证据校验通过的冻结 mutation。
- `hyp-003` 属于额外运行样本，仅作 exploratory 观察，不进入主分母。

## 身份敏感性

- 注册的 strict overlap 为 1 个。
- 忽略文字化调用链位置、只比较实际 Chaos mutation 后，executable overlap 为 4 个。
- 其中 3 对仅因调用链措辞不同而被分入 only 集合；主统计不事后改样本，但 only 集合不能解释为完全不同的物理故障。

## 审核状态

- human review: `pending`
- knowledge base updated: `false`
