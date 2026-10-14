# 两应用迁入记录 — 2026-10-14

DeviceService 与 Android GSHC 已迁入统一仓库，分别位于 `apps/DeviceService`、
`apps/GSHC_Android`。来源都不是 Git 仓库，没有可导入的独立 Git 历史；逐文件来源路径、
大小、SHA-256 和引用的旧协议提交已保留，应用的 MIGRATION_SOURCE.json 是完整入口。
基础提交为 355b3df2d297658eb958d02882902ec6a502c98e。

导入前核对 116 文件 / 946575 字节，没有覆盖已有应用目录。原始源码在迁入测试通过后，
使用 PowerShell 原生 Move-Item 逐文件移到 `.work/dev013_monorepo01/origins/`，
每项移动前后都核对精确路径和 SHA。原目录保留 MIGRATED.md；原 SDK、Gradle、缓存、
旧 APK 和其他未列入源码清单的文件保持原位置。没有永久删除来源目录或文件。
原始源码快照也保存在 evidence.zip 的 origins/ 中；它们是恢复证据，不是第二个活动项目。
没有复制嵌套 Git、SDK、Gradle 缓存、虚拟环境、APK 或私钥到 Git。

Android 脚本增加 ToolchainRoot / CacheRoot / BuildRoot / JavaHome 参数；复用外部 D 盘环境，
使用 Gradle --offline 和 sdkDownload=false，本轮所有新输出在版本任务目录。
Java 核心/存储及 Python兼容检查读取同一个可配置 BuildRoot。普通用户入口见
[Android MONOREPO](../../../apps/GSHC_Android/MONOREPO.md)。根 README/AGENTS 更新了应用布局。
应用级 .gitattributes 禁用导入文件的自动换行转换，Git blob也逐项核对未改文件原SHA。
原协议/reference 和历史 evidence 保持原字节；没有把快照提升为新的共享协议权威。

| 执行 | 结果 |
|---|---|
| DeviceService unittest | 18 tests，0 errors/failures/skips，退出0 |
| Android Java core / LOGFILE | 56 / 287 断言通过，152 RX帧，456 PC记录 |
| Java storage | 113 断言通过；只用本轮生成输入 |
| 冻结 PC 兼容 | 152 Java GSP/AIR帧逐字段一致，full/raw-only各31模拟样本 |
| 共享格式 | 56 schema/golden/ZIP断言通过 |
| Android assembleDebug/lintDebug/testDebugUnitTest | BUILD SUCCESSFUL，58 tasks执行，1m26s |
| Robolectric XML | 14 tests，failures=0，errors=0，skipped=0 |
| Lint XML | 0 errors，7 SetTextI18n warnings；Gradle9弃用提示也保留 |
| 生成 BuildConfig | ALLOW_USB=false，版本0.1.3-dev.1，versionCode1 |
| 已有 apksigner | debug APK签名验证退出0；未安装手机或发布 |

APK留在 `.work/dev013_monorepo01/android-build/app/outputs/apk/debug/app-debug.apk`，
2479069字节，SHA-256为
`7e2d2118c0da9ef0b9643e3335fe63f782ac626b3cfa785771ebebed10605b66`。
这是本轮重新构建的产物，不沿用历史 APK 的哈希或大小，也不宣称二者逐字节等同。
原 APK 仍保留在外部旧 build 目录。没有新设备/运动控制、远程删除、USB实测、手机安装、
模拟器验收或服务部署；DeviceService仍mock-only，两种Android构建类型的USB gate均false。

完整命令、退出码、日志、XML、原始源码和来源移动清单在 [evidence.zip](evidence.zip)；
[verification.json](verification.json)记录新APK、签名和归档哈希。core/storage兼容检查所用
环境变量的补充记录在 execution_configuration.json；未把旧报告的通过当作本轮执行。
Task inventory记录路径/大小/哈希/保留用途，没有执行清理。三份原有未跟踪用户清单哈希
保持不变；v0.1.2 commit保持c31c13cc0686a56a3184d4f207fd3816c5d39696。

本提交仅应用迁入及构建接入；ST-Link后端留在后续独立提交。没有push/tag/Release。
