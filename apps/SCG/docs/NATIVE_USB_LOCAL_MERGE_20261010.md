# SCG USB 实验候选本地合并与日常工作区验证（2026-10-10）

依据用户“做完之后告诉我，然后 merge，我再验收”及“SCG 可以覆盖到本地工作区”的授权，已把 ordinary 独审通过的 exact-target USB 软件候选合入日常分支。没有硬件、push、发布、FINAL 或其他应用修改。formal release/Generate All 保持 BLOCKED；b66 独立安全审查仍为 NO_PASSED_OUTCOME，未重试、未绕过。本报告交父任务核对及用户验收，不等同正式发布。

## 合并点与保护

- 日常路径 `D:\python_software\SilverStar`，分支 `fix/nightly-user-ready-20261003`；合并前重新确认 HEAD `56448bd35736221d7885a26704f2f953b0fe5055`，无 tracked 改动，原三份 inventory untracked 文件的路径/状态/原始 SHA256 全部保留。
- 输入 code `f61cbd851b8ac32b865deb1a3997058685dfebbd`，evidence `5b99438ba4005ea02935e9734307e749e2e758e7`，ordinary review `gui-f61-review/review.md` 确认无新增 P1/P2；此前及最新证据原样保留。
- 创建备份分支 `backup/pre-usb-candidate-20261010-051716` 指向合并前 HEAD。明确的 no-ff 本地 merge `2016a1279fa529c96d5b108d7d67326e2fda3653`，两父分别为上述日常旧 HEAD 与候选 evidence HEAD；无实质冲突，merge tree 与已审候选一致。所有差异均在 apps/SCG，没有重置、删除或覆盖用户 payload。
- 以下新验证使用日常路径 delivery code `e1357b417ee98df5990a1fff18c55d6b35183896`。最终后续提交仅报告/证据，不能把它们冒称为新产品代码的测试。

## Windows 实际交付问题及修正

首次 merge 后 dm01 为 10 failed/2 passed、dmr01 为 93 passed/6 errors、dmg01 为 1 failed/2 errors，均由正常导入/Plan 的原 radio payload hash 校验拒绝产生。日常 Git core.autocrlf=true 把 accepted sx1281_device.c 混合换行重写为全 CRLF，raw SHA 从审核所用 `56ee9b35e54535249816363d0328120a6018f157ce51f8bad93185ebea78428c` 变成 `0bdf0cfc1c950bd8fcda97898d8842a34f1e536f5e34bdc5b96758d46a8638ef`。Git 原 normalized blob 为 `0c9096e56e659f28319221ac9d56e559b375c1174787844946f2517e8dc22bed`；不能用宽松归一化来修改已有 byte pin。

e1357b4 仅为 delivery correction：在 apps/SCG/.gitattributes 对 sx1281_device.c 与 sx1280-hal.c 设 -text，把两份已审核原始 payload bytes 存入 Git，工作字节精确匹配原 hash；sx1280-hal.c 为 `b8caf4dd85dd3307897fa8f923adcaf7153b0d4c91a787eb58537d0b34eb783d`。其 normalized C 内容与合并前 Git 完全相同，无 C 算法、Python、validator、profile hash 或 MCU 行为修改。旧工作字节保存在临时证据中；git checkout-index 到新临时目录逐份验证 hash，证明再次 checkout 不复发。37 项 ordinary byte-pinned builtin/companion 输入审计中，只有上述 device payload 工作字节不匹配；其余 36 项一致。

## 日常路径新验证

| 执行 | 结果/范围 |
|---|---|
| dm02 | 12 passed、0 skipped，正常 Import/save/reload/export、实际 tool detection、真实启用 Generate/Build button click、新 ARM/analyzer、progress/cancel、错误返回、未知目标拒绝和 stale ELF 拒绝 |
| dmr02 | 99 passed、0 skipped，既有 GUI/target/build/native-control/clock/radio/ABI/runtime 普通回归 |
| dma01 | 16 passed、0 skipped，读取本次新 daily outputs，完整 Plan 每次一次/off-GUI；20ms live Qt timer、pending、切换、迟到 success/error、取消、关闭/销毁、artifact 验证 |
| dmg03 | 5 passed、45 deselected，直接执行 F103/F407/C071 正式 generation/Build refusal；只有所选函数，未声称所有 50 tests 全通过 |
| dmgates01 | 四个原样 emitted gates × 两目标，共 8 条 command，全部 exit 0；architecture、ordinary Host、实际 object/ELF CPU/ABI/独立 SDK IRQ/vector、Power-of-Ten |
| startup | 默认 system Python 实际 application.main/MainWindow show/event loop/normal close，37 ticks，exit 0；准确 daily 源/插件，只有 writable workspace/settings/logs 隔离到 Temp；正常 public launcher SCG.py --version 返回 0.1.2 |

实际 startup probe 最初在 restricted default execution 创建临时 .fccg/logs 被权限限制；相同 application/probe 在已授权权限下通过，没有为通过启动检查修改产品或用户 settings。日志明确为转录 tool 证据，未伪装新的执行。

- `STM32F103C8T6`：新输出 `C:\Users\chdxm\AppData\Local\Temp\dm02\usb-ec449283761c`，saved project `C:\Users\chdxm\AppData\Local\Temp\dm02\p_f353a348`；339 条实际 compiler/link/analyzer commands 全 exit 0，normal/analyzer link 成功、firmware/analyzer diagnostics 为 0。source snapshot `df5b92fdefd8c15dd85061767dce64515040ff216040aea9cc05b1ba171e233c`（52 个模块）；normal ELF `fde957fe80fdf038f4c5c6640bc851446e8ef7acb7605258fd94dca87c81240b`，analyzer ELF `fde957fe80fdf038f4c5c6640bc851446e8ef7acb7605258fd94dca87c81240b`；toolchain `arm-none-eabi-gcc (Arm GNU Toolchain 14.3.Rel1 (Build arm-14.174)) 14.3.1 20250623`。
- `STM32C071FBP6`：新输出 `C:\Users\chdxm\AppData\Local\Temp\dm02\usb-a37383e595c2`，saved project `C:\Users\chdxm\AppData\Local\Temp\dm02\p_0a727c40`；351 条实际 compiler/link/analyzer commands 全 exit 0，normal/analyzer link 成功、firmware/analyzer diagnostics 为 0。source snapshot `779f3112325bb690b051c4a5d2c2b15b618adb385e0a438ea3ec47251c45eb7c`（161 个模块）；normal ELF `ee90e6871f5f5723982701e8b6783dd2638f4bd76f352f5099d2d38e031028b9`，analyzer ELF `ee90e6871f5f5723982701e8b6783dd2638f4bd76f352f5099d2d38e031028b9`；toolchain `arm-none-eabi-gcc (Arm GNU Toolchain 14.3.Rel1 (Build arm-14.174)) 14.3.1 20250623`。

新 compiler/backend/model/pointer/quality receipts 的来源提交均是 e1357b4，tracked dirty diff 为空，完整 source-snapshot 模块逐份核对实际 daily raw bytes。normal/analyzer ELF 的 code 语义与已审核候选相同；旧证据不冒充本次新执行。

| 刷新目标 | 同步 view 填充 | 全刷新 | 后台 ticks | 最大后台 gap |
|---|---:|---:|---:|---:|
| STM32C071FBP6 | 0.498s | 3.248s | 86 | 0.081s |
| STM32F103C8T6 | 0.495s | 2.418s | 55 | 0.077s |

后台 cadence 从同步 view 填充返回后计量；同一刷新只有一个 Plan，旧有界面填充仍有约半秒开销。上轮并跑 0.94–0.98s 的已知限制继续保留，不能声称全部 GUI 工作都在 0.5s 内。

- 实际 `C071` Build + 完成审核：68.944s、3399 ticks、最大 gap 0.525s。
- 实际 `F103` Build + 完成审核：64.654s、3120 ticks、最大 gap 0.674s。

## 附加失败与边界

dmg02 是额外 generic→pinned dispatch 审计：2 passed/1 failed/19 deselected；失败的 F103 完整 model equality 断言原样保留。普通 descriptor audit 确认仅 evidence_source 和 evidence_sha256 不同：generic fixture 绑定 daily plugin.json/其当前 raw bytes，而 pinned backend 绑定已审核 .work/ccdi 的 metadata/原 raw bytes。芯片、CPU、内存、IRQ、startup 等全部其他字段一致。snapshot identity 包含 authority provenance，因此两种来源不同不能宣称相同 snapshot。没有修改此测试、放宽 checksum 或静默改 pinned descriptor；真实用户入口从开始就采用 pinned backend，dm02 两目标 Import/Generate/Build 全通过。附加跨 authority equality case 仍是失败，留给父普通独审核对，不拼接成全 suite PASS。

精确 pinned profile 的独立 SDK 和 metadata/source evidence 路径仍为本机既有依赖，包含 .work/ccdi 的 F103 metadata authority；本次没有删除该 worktree 或将其标为无需保留。此次验收是明确本地 exact-target 软件实验，不宣称单独搬走日常目录即可在任意机器支持任意 CubeMX 配置。保存 import 后的 immutable source snapshot；源、SDK 或产物 hash 变化必须被原校验拒绝。

原 HAL/CMSIS/startup/linker/clock/GPIO/IRQ/PCD/middleware ownership、bounded queues/session/protocol 及旧路由门禁均保留。F103C8T6/72MHz、C071FBP6/48MHz 之外配置继续拒绝；F407 保留 private candidate，未新增 GUI 通用放行。manual critical-contract、whole-program stack/WCET、PCD/PMA/IRQ interleaving 和物理 USB/硬件仍 NOT PROVEN；PoT command exit 0 不能替代这些结论。硬件不是本轮普通软件验收的新增前置条件。

## 最短用户验收

1. 从日常根目录执行 `python apps/SCG/SCG.py`，使用现有 Ground Station Hardware 页，将 PC transport 选为 USB CDC Virtual Serial。
2. 用原 Import CubeMX 目录/IOC 按钮选择受支持 exact native source；F103 参考目录为 `C:\Users\chdxm\Documents\Codex\2026-10-08\task\usb-validation\cube-f103-usb`；C071 为 `C:\Users\chdxm\Documents\Codex\2026-10-08\task\c071-cubemx-input\full-native-clean\C071FBP6_PCD_TEST`。其 SDK/companion 原始输入只读保留。
3. 保存为新实验项目，点击 Ground 原 Generate；Build 页选择已安装 ARM GCC 路径后点击原 tool detection，再点击启用的 Ground Build。每次 output 在新 disjoint sibling，原 native/user inputs 不覆盖。
4. 查看正常进度及 receipt/ELF，验证 Cancel/项目切换/正常关闭体验；状态应同时显示 software candidate 和 formal release BLOCKED。Generate All/正式发布不作为本次候选验收目标。不要连接硬件或 START。

## 证据

归档 [verification.json](evidence/native_usb_local_merge_20261010/verification.json)，736 个 listed files 加 manifest，listed bytes 19909524，manifest SHA256 `cb68d8992fda067f83a61ea0c3794cb0fe9a928e755db54cd692297aa98d59c9`。保存 merge/备份/hash receipt、字节交付证明、前后失败/通过、fresh compiler/backend/source-snapshot/model/quality/pointer、全部声明生成文件、ELF/map/.su、ordinary gates、startup 和 Qt 时序。未大量复制原 vendor inputs，其 pinned original paths/hash 保留。
