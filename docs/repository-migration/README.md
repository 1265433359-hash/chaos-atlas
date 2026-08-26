# Repository Migration

本目录记录 ChaosAtlas 从混合实验工作区迁移到“产品仓库 + 证据归档仓库”的过程。

## 当前边界

- `src/chaosatlas`、`cli`、`projects`、`tests`、`docs`、`scripts` 是产品边界。
- `ChaosAtlas-evidence-v2` 是本次通过校验的本地证据归档工作树，远端发布目标为 `chaos-atlas-evidence`。
- 根目录已切换为产品结构；历史实验目录保留在 `ChaosAtlas-evidence-v2/legacy-workspace/`。
- `tools/` 在兼容期保留；新入口必须从产品包导出。
- kubeconfig、凭据、虚拟环境、本机临时状态不会被迁移。

## 迁移命令

```powershell
python scripts/repository_inventory.py --root . --output .migration/baseline-inventory.json
python scripts/migrate_evidence.py --root . --evidence-root ChaosAtlas-evidence --manifest .migration/evidence-migration.json --dry-run
python scripts/migrate_evidence.py --root . --evidence-root ChaosAtlas-evidence --manifest .migration/evidence-migration.json
python scripts/verify_evidence_archive.py --manifest .migration/evidence-migration.json --evidence-root ChaosAtlas-evidence
```

迁移脚本只复制，不删除源文件。当前根目录的历史目录移出操作已在哈希校验后完成，原始内容保留在 `legacy-workspace/`；Git 提交和远端发布仍需在具备 `.git` 写权限和 GitHub 凭据的终端完成。
