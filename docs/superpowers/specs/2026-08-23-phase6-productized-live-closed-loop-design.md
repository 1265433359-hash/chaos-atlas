# Phase 6 Productized Live Closed Loop Design

## Goal

把现有 `chaosatlas.py run` 的单候选 live 路径收束为可审计的 Phase 6 运行契约，并保持三项目离线回放、原项目隔离和显式 live 审批边界。

## Scope

本阶段不重新实现 discovery、executor、RCA 或知识晋级。新增的产品化层只负责：

- 在运行 manifest 中记录 approval、namespace allow-list、候选/时长预算、输入快照和模式；
- 在运行结束后生成稳定的 artifact index，记录每个输出文件的大小和 SHA-256；
- 生成 Phase 6 audit，汇总阶段状态、cleanup、知识更新状态和阻断原因；
- 让 dry-run、live success、environment blocked、method invalid 都产出同一组审计文件；
- 对敏感值和越界 namespace 继续 fail closed。

## Data Flow

```text
profile + run options
  -> execution contract
  -> existing onboard/inventory/discovery/RCA/learn stages
  -> cleanup report
  -> artifact index
  -> phase6 audit
```

`artifact_index.json` 不包含自身，避免自引用哈希；`phase6_audit.json` 引用 index 的相对路径和 index SHA-256。知识卡仍只有 promotion stage 才能写入显式 `knowledge_write_root`。

## Safety Contract

- live 必须同时满足 `mode=live`、`approve_live=true`、profile namespace 在 allow-list 中和 preflight ready；
- 单次 `run` 的最大候选数固定为 1；批量路径继续由现有 `run_live_batch` 管理；
- 运行失败、业务不可达或注入未确认只能写入审计状态，不能升级 runtime claim；
- artifact index 只列出当前 output root 内的普通文件，路径以 POSIX 相对路径表示；
- index 和 audit 写入失败不得伪装为成功，运行结果保留原始 status。

## Acceptance Criteria

1. dry-run 和 live gate blocked 输出 `phase6_audit.json`、`artifact_index.json` 和统一 execution contract。
2. artifact index 的每个条目可由文件内容重新计算 SHA-256。
3. audit 明确记录 `knowledge_base_updated=false`，除非显式 promotion stage 成功。
4. 三项目既有离线回放继续通过，原 namespace 和全局 Chaos 残留不被修改。
