# ChaosAtlas 产品运行入口

产品仓库只保存可复用的编排、策略、契约、适配器、项目 profile、测试和文档。未审核的运行证据与临时状态默认写入 `%LOCALAPPDATA%\ChaosAtlas`，不写回产品代码树。

## 本地运行状态

Windows 默认状态根目录是 `%LOCALAPPDATA%\ChaosAtlas`；需要放到其他磁盘时，
设置 `CHAOSATLAS_STATE_ROOT`。其中 `runs/` 保存待审核实验输出，`tmp/` 保存临时状态，
`archive/` 保存带清单的历史归档。只有经过来源核对、脱敏和人工审核的证据，才能复制到
仓库的 `artifacts/` 或 `reporting/`。

提交前检查：

```powershell
python scripts/check_workspace_hygiene.py --root .
```

预览外置归档操作：

```powershell
& scripts/archive_root_workspace.ps1 -IncludeDependencies -WhatIf
```

正式归档会在外置目录生成 `MANIFEST.json` 和 `RESTORE.md`。旧的
`.email-notify-outbox` 只保留审计记录，不得复制到当前邮件待发送队列。

## Dry-run

```powershell
python -m chaosatlas run `
  --profile projects/sock-shop/profile.json `
  --mode dry-run
```

dry-run 只读取 profile 并生成计划摘要，不调用 LLM，也不修改 Kubernetes。

## 统一执行入口

dry-run、单候选 live 和多候选 live 都先构造 `RunRequest`，再进入唯一的
`RunEngine`。单候选 live 使用同一个候选循环，预算固定为 1；Oracle 通过注册表解析，
不再由 CLI 或项目脚本选择另一套编排器。

## 兼容入口

迁移期间原有入口继续可用：

```powershell
python tools/chaosatlas.py --help
python tools/run_closed_loop.py --help
```

新代码统一从 `src/chaosatlas` 导入；`tools/` 入口只负责转发，不拥有另一套运行状态机。

## Live 安全门

live 执行必须显式提供允许的 namespace、executor、业务 Oracle、恢复和清理契约。缺少任一契约时应停在 preflight，不得注入。

## Dify Compose E2E

Dify 1.17.0 is a Docker Compose workload, so use the Compose adapter instead
of the Kubernetes live runner. The default matrix is one service at a time:
`api`, `nginx`, `worker`, `redis`, `sandbox`, and `plugin_daemon`.

From the repository root, run a dry-run first:

```powershell
$env:PYTHONPATH = "$PWD;$PWD\src;$PWD\.venv\Lib\site-packages"
& scripts/invoke_python.ps1 scripts\run_dify_compose_e2e.py --service api
```

After reviewing `plan.json`, an explicitly approved live matrix is:

```powershell
& scripts/invoke_python.ps1 scripts\run_dify_compose_e2e.py --approve-live --compose-dir "$env:CHAOSATLAS_DIFY_COMPOSE_ROOT" --output "$env:LOCALAPPDATA\ChaosAtlas\runs\dify-docker\e2e-<run-id>"
```

The runner stops on the first failed recovery by default. It always attempts
to restore the current service, requires three stable recovery probes, redacts
  secret-like log assignments, and writes results under the external state root.
It does not test PostgreSQL, Weaviate, Docker Desktop, or host resource
exhaustion.

## Dify Kubernetes Unified Loop

The Dify Kubernetes profile uses the published Chatflow as its business-path
oracle. The key is read from `C:/APP/project/Dify_APIkey.txt` at runtime and is
never written to evidence. Run a read-only dry-run first:

```powershell
$env:PYTHONPATH = "$PWD;$PWD/src"
python tools/chaosatlas.py run `
  --profile projects/dify-kubernetes/profile.json `
  --mode dry-run `
  --output .runs/dify-unified-dry-run
```

For a bounded policy-controlled live run, use one candidate per round and keep
the output directory new:

```powershell
python tools/chaosatlas.py run `
  --profile projects/dify-kubernetes/profile.json `
  --mode live `
  --approve-live `
  --kube-context chaosatlas-dify `
  --all-candidates `
  --policy-mode guarded `
  --policy-budget 20 `
  --max-candidates 20 `
  --output .runs/dify-unified-guarded-<run-id>
```

The batch records the frozen candidate pool, policy decisions, runtime
feedback, posterior state, and stop reason. The current Dify profile has 17
live-verified fault families. HTTPChaos families are inapplicable on the
current WSL2 kernel, while high-risk platform and native-resource families
remain gated behind a disposable isolated environment.
