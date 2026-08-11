# Project Analysis Summary

分析日期：2026-08-11

## 研究对象

ChaosAtlas 不是一个单一微服务应用，而是一个研究工作区。它把真实
Chaos YAML 转换为以 TestNode 为中心的局部影响子图，并通过适用性门禁、
有界注入、业务 oracle、恢复/清理证据和知识卡形成可审计闭环。

核心抽象是：

```text
YAML -> TestNode -> local impact slice -> applicability gate
-> baseline/inject/recover/cleanup -> conservative verdict
-> source/runtime evidence -> knowledge card
```

## 当前已完成材料

- Train Ticket：最完整的主线案例，已形成 Station 延迟边界、CPU stress、Basic->Station 网络和知识卡闭环。
- Online Boutique：完成 payment/shipping/email/product catalog、probe restart race 和 multi-fault 语义对照，并有重复实验。
- OpenTelemetry Demo：补充多语言调用链、Jaeger span、deadline 和 HTTP/gRPC 协议差异证据。
- Sock Shop：作为第四项目完成跨项目迁移和 ChaosEater 分层对照；证明调用契约层与部署可用性层可以统一记录。
- 工具链：selector、局部图、适用性门禁、runner、分类器、知识库 validator、decision engine 和回归测试均已归档。

## 当前论文可用主张

1. TestNode-centered 影响子图可以把 YAML 层候选与真实服务、调用、业务 oracle、观测和恢复路径连接起来。
2. 适用性门禁可以区分平台阻断、业务不可达、静态存在和运行时已验证，避免把“注入成功”误写成“系统有韧性”。
3. Train Ticket Station 证明响应保持、延迟退化、客户端超时和服务端晚完成是不同结果。
4. Online Boutique 与 OTel Demo 证明相同故障族会因下游实现和协议不同而产生 fatal、degraded、restart-converted 等不同语义。
5. Sock Shop 支持知识迁移、规则边界发现、调用契约/可用性分层覆盖和结构化证据输出的描述性贡献。

## 暂缓轨道

知识库选择-only 消融和最终方法 head-to-head 对比均标记为
`parked_future_work`。已有 protocol、snapshot、prompt、selection record、
ChaosEater 输出和台账全部保留，但以下闭环未完成：

- formal runtime execution and confirmation;
- independent full-pool oracle;
- remaining human review gates;
- common candidate pool/oracle for the final comparison;
- project-clustered statistical analysis;
- final claim-evidence closure.

因此当前论文不使用这些轨道的中间数字作为正式效果量，也不声称知识库或
完整方法全面优于其他方法。

## 推荐论文结构

1. 方法：TestNode、局部影响子图、四层适用性门禁和证据链；
2. 工程实现：选择器、runner、分类器、知识卡和停止规则；
3. 主案例：Train Ticket Station 延迟边界；
4. 跨项目语义：Online Boutique、OTel Demo、Sock Shop；
5. 评估：延迟、错误、恢复、观测和证据完整度；
6. 限制：项目数量、环境前置条件、oracle、SLO、样本和确认偏误；
7. 未来工作：知识库消融和最终方法对比。
