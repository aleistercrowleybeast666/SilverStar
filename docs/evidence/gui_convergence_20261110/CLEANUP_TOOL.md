# 清理入口与复合扩展名保护

`apps/FLP/tools/clean_workspace.py` 将 Git 根与明确的应用 / 任务范围分开。
默认只预览；执行已审核清单前重新检查文件内容、身份、路径、索引和活动标记。
源码、嵌套 Git、reparse point、原始记录、decoder、工程、归档和正式证据不作为普通缓存。
不会根据 ignored 状态或仅有目录名称递归删除。

`73712608` 的 monorepo 修复由完整工具测试文件 **13 passed / 17.30 s** 验证。
本轮进一步发现普通 `.json` 候选会包含 `.tdrun.json` 和 `.retldc.json`；
已有 `.tdmotor.json`、`.sstuning.json` 保护保持不变。
新增回归使用大小写不同的实际文件名，覆盖生成目录和缓存目录，并验证显式夹入保护输入时
整份清单拒绝、文件不半删。修复前 **1 failed / 2.04 s**，修复后完整工具文件
**14 passed / 23.70 s**。没有放宽任何门禁。实际清理曾应用的清单仅包含已确认缓存，
因此没有工程或 run 因这个缺口被删除。

本轮命令（仓库根）：

```powershell
$env:PYTHONPATH = 'apps/FLP'
.venv/Scripts/python.exe -m pytest apps/FLP/tests/test_clean_workspace.py -q `
  --basetemp .work/gui-convergence-20261110/root/cleanup-compound-after
.venv/Scripts/python.exe apps/FLP/tools/clean_workspace.py --dry-run
```

完整[修复前失败日志](cleanup_tool/before.log)和[修复后全文件日志](cleanup_tool/after.log)
已从本任务原文件逐字节复制到正式证据。原文件继续保留在任务 root 目录；
本次补齐收录没有重跑测试，也不把历史批次当作最终 HEAD 的新执行。
实际执行范围、计划与删除结果见本目录的 `cache_cleanup.json`、`worktree_cleanup.json`
和其他两仓的 cleanup 证据。旧 checkout 的归档后删除采用另外的逐文件恢复核验清单，
不借缓存工具绕过原始输入保护。
