# Project Analysis Risks

分析日期：2026-08-11

## 论文风险

- 项目数量有限，Train Ticket 是最完整主线，跨项目结果来自特定 demo。
- 多数运行是小样本或有界观察窗口；实验客户端 timeout 不是生产 SLO。
- HTTPChaos 在当前 WSL2 内核受 ebtables 前置条件阻断。
- Order->Station 的真实业务路径尚未形成可重复 oracle。
- 部分 Online Boutique/OTel 知识卡使用 generated candidate，保留 source_yaml warning。
- Sock Shop 的 6/8 + 2/8 是论文边级口径；机器台账还按 delay/loss 变体记录 4/8 + 4/8，loss 防御未单独复跑，不能混用。
- Sock Shop 可用性对照是在已知 ChaosEater 结果后设计，存在确认偏误，不能称双盲复现。

## 未完成实验风险

- 知识库消融尚未完成 Gate 1-6、独立 runtime oracle 和项目聚类统计。
- 最终方法 head-to-head 尚未完成 common pool、common oracle 和统计闭环。
- held-out 环境存在 deployment、CoreDNS/selector 或内核门禁；blocked 不等于 weakness 或 defense。
- 任何当前中间排名都不支持 superiority claim。

## 工程和归档风险

- 工作区仍可能包含用户生成的未跟踪产物，不等于 release branch。
- 论文数字必须优先引用 JSON/CSV/ledger，再引用人读报告。
- GitHub 上传仍需敏感值、第三方许可证、二进制和 nested checkout 审核。
