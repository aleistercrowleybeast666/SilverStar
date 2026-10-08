# Documentation

Current application implementation: `apps/SCG`. The Python package and plugin IDs retain FCCG compatibility names. `docs/FCCG` and frozen evidence paths are historical namespaces; their recorded bytes and hashes are preserved.

建议阅读顺序：[用户流程总览](USER_WORKFLOW.md) → [硬件与四档/推荐边界](SilverStar_Recommended_Configurations.md) → [SCG 配置生成](FCCG/USER_GUIDE.md) → [GSHC 采集](GSHC/APP_README.md) → [FLP 分析](FLP/APP_README.md) → [四算法原理与实际实现](algorithms/NAVIGATION_IMPLEMENTATION.md) → [当前验证边界与明日静态清单](NIGHTLY_SOFTWARE_CLOSEOUT_20261008.md)。

- [FCCG documentation](FCCG/README.md), [application guide](FCCG/APP_README.md), [historical validation](FCCG/VALIDATION.md)
- [GSHC documentation](GSHC/README.md), [application guide](GSHC/APP_README.md), [historical validation](GSHC/VALIDATION.md)
- [FLP documentation](FLP/APP_README.md), [architecture](FLP/Architecture.md), [historical validation](FLP/VALIDATION.md)
- [推荐组合与验证范围](SilverStar_Recommended_Configurations.md)
- [2026-10-08 GUI 收尾、文档核对与未通过项](RELEASE_GUI_CLOSEOUT_20261008.md)
- [本机软件收尾与当前边界：菜单生命周期、四档、Windows路径及静态清单](NIGHTLY_SOFTWARE_CLOSEOUT_20261008.md)
- [当前静态任务与一次复查](STATIC_BENCH_ACCEPTANCE_20261008.md)、[000045 复查边界](STATIC_BENCH_REPEAT_20261008.md)、[实际 TF 文件与 FLP 离线验收](STATIC_LOG_FILE_ACCEPTANCE_20261008.md)
- [Monorepo architecture](architecture/MONOREPO_ARCHITECTURE.md)
- [2026-10-08 TEST_5 与生产 GSHC 对比、DAP 拒绝现场](TEST5_GSHC_DAP_COMPARISON_20261008.md)
- [Flight and Ground target model](architecture/TARGET_MODEL.md), [AIR Link](architecture/AIR_LINK.md), [Ground Station firmware](architecture/GROUND_STATION.md), [Device variants](architecture/DEVICE_VARIANTS.md)
- [Project folder contract](architecture/PROJECT_FOLDER_CONTRACT.md)
- [Mission snapshot and final status](architecture/MISSION_SNAPSHOT.md)
- [Round 4 device and navigation report](architecture/ROUND4_DEVICE_NAVIGATION_REPORT.md)
- [Round 5 field qualification report](architecture/ROUND5_FIELD_QUALIFICATION_REPORT.md), [frozen software reference](field/FIELD_TEST_REFERENCE.md), [field-test checklist](field/FIELD_TEST_CHECKLIST_0_1_0.md)
- [Round 2 multi-target report](architecture/ROUND2_MULTI_TARGET_REPORT.md)
- [0.1.0 migration report](architecture/MIGRATION_0_1_0.md)
- [Canonical navigation contract](../contracts/navigation_v1.json)

The imported `VALIDATION.md` files are historical records. Their old absolute paths and test counts describe the former workspaces, not a fresh monorepo validation result.
