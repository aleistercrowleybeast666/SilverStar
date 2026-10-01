# 用户 16:12 指令后的安全暂停

用户明确要求“安全停止然后回退版本”。在该指令到达时，最近的写入/读取命令已经结束；未启动 B 的 Host、ARM、PoT、静态分析或 GUI 测试。停止后仅记录、保存、提交自己的成果并切换分支，不继续补实现或启动测试。

本轮开始于实验分支 `feature/post-field-firmware-20261001`、已验证的 A 提交 `4dd0fdef17c79040ab38e36800281e28e501be5a`，工作区干净。停止时只有自己修改的 `apps/FCCG/src/silverstar_fccg/project/model.py` 和本目录两个新文件，没有用户改动冲突。

B 当前是未验证 WIP。只加入了 GroundRadioConfiguration、选择辅助操作、实验格式 15 的部分序列化/解析准备；默认单实例仍拟保留格式 14。解析调用尚未接入新标志，schema、资源分配、生成路径、适配器实例索引及 UI 都未完成。不能生成或宣称已经支持多模块，不能当作可测试交付，更不能 FIELD READY。完整 WIP 差异及哈希见 `pause_snapshot.json`、`WIP_source_delta.patch`。

审查发现：Ground 现有配置只生成 radio0，适配器固定调用实例 0；GSP opaque AIR forwarding、GSHC 单一 controller/session/command owner，没有完整跨路去重身份。计划的第一片是构建时选一个活动实例，避免运行时切换、并行接收或结果未知命令自动重发。该计划尚未实现。默认链路和硬件没有任何动作。

## 稳定基线的独立最小修复

准确稳定基线仍为 `d410f4a7254f0433e91a22adb237b2944939fd99`。其 0.1.1 生成目标名是 `SilverStar_0_1_1`，但两个检查脚本硬编码 `SilverStar_0_1_0`，可能导致架构/产物检查错误拒绝。没有将修复擅自应用到 main。

`version_identity_only.patch` 只包含以下三项，不含实验内存宏、MEMORY_LAYOUT 参数、ELF 放置验证或 B 的模型改动：

1. 新增 `apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools/read_firmware_identity.ps1`。
2. `check_architecture.ps1` 的 eide_consistency 目标名检查 hunk（基线约第 473 行），改为读取并精确匹配工程 identity。
3. `check_firmware_artifact.ps1` 开头目标名 hunk（基线约第 7 行），替换固定名称读取。

patch 已在仓库外的独立基线副本上执行 `git apply --no-index --check`、实际 apply，并核对三个文件内容；结果、路径、exit 和 SHA256 在 `version_patch_validation.json`。早期仓库内检查因 CWD prefix 跳过文件、字节比较因 autocrlf 不同的两次尝试也在该记录里说明；最终成功以真实隔离副本内容为准。

若用户以后选择保留修复，可在从基线另建的修复分支上明确执行 `git apply --check <此patch绝对路径>` 后再 `git apply <此patch绝对路径>`；它不是自动回退步骤。切回 main 后本目录不在其工作树，可从实验分支读取：

```powershell
git show feature/post-field-firmware-20261001:docs/FCCG/post_field_ground_radios_20261001_v1/version_identity_only.patch
```

普通重新生成继续保留用户 payload，不能据此宣称现有外部工程的旧 Tools 自动得到修复。若之后要验证修复，应生成新的独立工程，或在明确授权后针对外部工程的三个 Tools 文件做可审计更新。

此前 A 的所有工具会话均已返回结束，B 本轮没有启动长进程。停止后的全局 Win32_Process 只读枚举被环境权限拒绝；没有尝试关闭未知或无关进程。没有操作 ToDesk、水母、网络、桌面、关机、push、merge、tag、Release、烧录或 START。
