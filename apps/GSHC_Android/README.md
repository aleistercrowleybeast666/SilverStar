# SilverStar GSHC Android — 0.1.3-dev.1

原生 Android 开发版已迁入 SilverStar monorepo 的 `apps/GSHC_Android`。来源文件、哈希与保留目录见 [MIGRATION_SOURCE.json](MIGRATION_SOURCE.json)，迁入后构建/测试见 [迁入报告](../../docs/evidence/monorepo_import_20261014/REPORT.md)。真实 USB 仍关闭，未安装手机或发布。

下列 APK 哈希和旧验证属于 2026-10-13 的独立目录交付，原始证据保持不变；本轮新构建的路径/哈希另见迁入报告。

## 交付与实际验证

历史 debug APK（原外部目录 `build` 中保留） · versionCode **1** · **2527905 字节**。

SHA-256：`ebd76cfd2bc0be8c566d47cfec01628aaa150d37d4558bf5ef80e108ebcacd77`

- Java17 / 原生 Android Views；minSdk26，compile/target36；AGP8.13.2、Gradle8.13、现有JDK21。
- `:app:assembleDebug :app:lintDebug :app:testDebugUnitTest` **BUILD SUCCESSFUL**；14项Robolectric框架测试通过。lint 0错误、9警告（依赖新版本提示与字符串国际化）。
- 核心56、LOGFILE287、存储113、共享格式56项断言通过；冻结PC解析152帧一致，full/raw-only均得到31个模拟飞行样本。
- debug/release均 `ALLOW_USB=false`。APK签名已验证；不申请网络或全盘存储权限，不增加云账号/同步。
- 没有模拟器或真机验收。Robolectric不是手机系统、USB驱动或第三方SAF provider的实测。

详细证据：[VERIFICATION](evidence/VERIFICATION.md)、[机器可核对构建记录](evidence/android-build.json)、[当前交接](HANDOFF.md)。

## 四页 GUI 与数据流

顶部统一管理地面站端口与飞控调试口：600dp及以上横排，窄窗竖排。独立权限请求、设备身份和端口租约；同一物理端口不能被两路同时占用。断开/拔插立即使旧操作失效，旧资源仍完成关闭，I/O退出和关闭完成后才释放自己的占用。

1. **预飞行**：开始/停止仿真记录、准备和任务状态、不可用的危险命令及保护条件说明。
2. **飞行**：遥测与六条曲线。窄窗2列3行，速度左、位置右，E/N/U同排；840dp起3列2行。只按解码飞行帧采样，保留源顺序和重复时间戳，实时/分片/多帧/回放结果一致。
3. **后期处理**：原始会话列表、命名、查看、JSONL导入/回放、SAF复制/确认剪切、复制分享、确认移入回收站与恢复。卸载/清除数据会丢失内部会话和回收站，界面明确提示先导出。
4. **调试与维护**：真实已解码字段的只读状态；LOGFILE能力/目录/下载校验及明确标识的模拟操作。下载前必须选择SAF保存目录；只有合法持久读写授权才记住目标。权限撤销、磁盘满、取消或回读失败均保留内部原件。

地面站USB接收适配器/仿真/回放 → GSP → AIR → 任务状态与曲线，并保存原始字节和时间。维护口 → 独立LOGFILE客户端 → 内部暂存/CRC校验 → 用户SAF目录新文件 → 关闭并读回SHA-256/长度校验，之后才报告完成。没有默认转发到地面站口。

本版本不发送ACK、解锁、START、开伞或设备DELETE。旧固件没有LOGFILE能力则不支持。f2ce541设备/启动身份仍unknown，跨连接续传禁用：每次新文件从0下载，旧partial/完整文件保留；mock不能授予真实能力。

## 原始数据与 PC 边界

AIR/GSP和PC会话来源冻结于v0.1.2；共享导出格式来自cb944b7c，当前只读文件服务策略来自f2ce541，均有独立原文快照。JSONL新会话格式版本1；旧日志按原字节保留legacy身份。ZIP清单记录真实协议、应用版本、时间和逐文件SHA-256。

PC GSHC兼容测试覆盖JSONL读取/提取，旧版PC应先解压后按其支持方式打开JSONL，不承诺直接打开新ZIP。FLP需要原生.bin/.sslog、精确匹配的.ssdecoder及Descriptor；SSLOG仍0.0、decoder包仍1.2。传输校验不证明decoder匹配，AIR不能补回缺失的板载高频记录。模拟TF内容明确为synthetic-fixture。

剪切要求关闭记录、目标关闭、完整ZIP及逐文件回读、独立人工确认，再次校验后移至内部可恢复回收站；无物理清空。分享始终复制。恢复弹窗绑定请求和目标版本，旧Activity回调或重复确认不生效。详情及未来TF下载/删除设计：[SHARED_CONTRACTS](docs/SHARED_CONTRACTS.md)。

## 复现

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build-android.ps1 -ToolchainRoot $env:SILVERSTAR_ANDROID_TOOLCHAIN_ROOT -CacheRoot $env:SILVERSTAR_ANDROID_CACHE_ROOT -JavaHome $env:JAVA_HOME
powershell -ExecutionPolicy Bypass -File .\tools\test-core.ps1 -JavaHome 'C:\Program Files\Microsoft\jdk-21.0.12.101-hotspot'
python .\tools\test-pc-compatibility.py
powershell -ExecutionPolicy Bypass -File .\tools\test-storage.ps1 -JavaHome 'C:\Program Files\Microsoft\jdk-21.0.12.101-hotspot'
python .\tools\test-shared-export.py
```

[构建环境与SDK许可](docs/SDK_SETUP.md)记录安装来源和授权时间。历史 SDK本体约410.7MiB；原工具链/缓存均继续在外部D盘位置复用，未复制入Git。构建脚本使用显式 ToolchainRoot/CacheRoot/BuildRoot/JAVA_HOME，Gradle离线构建并禁止自动SDK下载。本机14项测试使用SDK36框架；minSdk26的静态兼容检查通过，但未在Android26设备上实测。

[四页布局预览](docs/layout-preview.html)及20案例/6张图属于浏览器设计证据，**不是APK截图**。真实手机Host/OTG、CDC/USB-UART芯片、Hub/供电、USB拔插/后台通知及外部SAF持久权限仍需另行授权实测，不承诺所有机型。

官方依据：[USB Host](https://developer.android.com/develop/connectivity/usb/host)、[SAF](https://developer.android.com/training/data-storage/shared/documents-files)、[connectedDevice服务](https://developer.android.com/develop/background-work/services/fgs/service-types)、[备份排除规则](https://developer.android.com/identity/data/autobackup)。
