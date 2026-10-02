# RF + M9N 独立组合候选，2026-10-02

基于 RF `0b98f498f1d2eb27f96bf17d1442c884c9052bb1`，cherry-pick M9N `d3fa28880de65f85cd6cf8f72a21df1485271a3c` 为 `fee89ed`；CPU-only placement `a87eab1`；父审查的软件冲突回归 `6c74cbc`、生产修复 `b2e61d272b8e6e741606042d7aaaa3b36d622df5`。分支 `fix/rf-m9n-integration-20261002`，worktree `D:\python_software\SilverStar\.work\RfM9nIntegration_20261002`。未接触硬件、串口、DAP、共享 venv、其他 worktree、主分支或冻结包；无 push/flash。

交付候选仅 `.work/combo_final2/Flight_Controller`。运行配置完整沿用 RF fixture，仅 project.name 从 SS_RadioHandshake_1 改为 SS_RfM9n_1：KF6 / JY901B / M9N / E28 / Delay10。逐项 JSON 比较证明没有其他参数变更；四份 owning M9N/Host 源与候选副本原始字节相等。RF 提交涉及的24个文件逐个与原提交比较保持相同。完整 source/configuration/gate/日志/产物哈希在 FINAL_MANIFEST.json。

## 修复与父审查点

身份、无 MOD ROM 能力前置和23项 CFG兼容见继承的 `../M9N_PROTOCOL32_20261002/REPORT.md` / CFG_COMPATIBILITY.json。版本仅旧27.00–27.99与新32.01，新档要求FWVER=SPG4.04；无MOD仅实际捕获的ROM CORE4.04(d964f4)/00190000签名，并先读全23键、key/类型/长度匹配后才允许VALSET。它证明驱动能力，不能证明NEO封装身份。CRC、错型号、未知版本、固定字段有界/重复冲突拒绝不放宽。

父审查发现有MOD的新档此前会接受明确跨代软件信息。真实生成C Host加入4个CRC正确的32.01/MOD=NEO-M9N/FWSPG4.04反例，在旧驱动 `a87eab1` 上4918检查/16失败，原始生成测试与源快照、编译命令和失败日志完整保留。最小修正仅对32.01拒绝官方M8 CORE2.x/3.x、M10 SPG5.x的ROM/EXT软件族，使用既有WrongFirmware诊断。保留未知/空软件与旧27兼容，未加入软件白名单；测试同时覆盖7种软件内容在旧27下的保留行为。新M9 Host：4918 checks, 0 failures。

软件族依据：[M8 UBX-13003221 R28 pp6–8](https://content.u-blox.com/sites/default/files/products/documents/u-blox8-M8_ReceiverDescrProtSpec_UBX-13003221.pdf)、[M10 UBX-21035062 R03 pp10–11](https://content.u-blox.com/sites/default/files/u-blox-M10-SPG-5.10_InterfaceDescription_UBX-21035062.pdf)。源码注释把M10章节写成1.5，准确位置为1.2.1/1.2.2；该章节号勘误不影响执行代码。

500ms只在32.01的CFG-SIGNAL键成功ACK后触发，非阻塞Pending，实际时钟计时，不重置外层阶段deadline。probe5000ms、内部200+2200+250+2200ms、stage45000ms、parser1024保持原值；原控制器Ok优先，其余Pending/Failed检查deadline，未更改。KEY_FUNCTIONS.c.txt保存按定义定位的真实关键函数。继承M9档旧KEY_FUNCTIONS对SendUbx误提取调用片段，此处已纠正，原固件源码没有受影响。

## SRAM超限与现成CCM placement

未改placement的全新组合pre：ARM成功，artifact/资源门禁失败；SRAM102424 > 原100KiB门槛102400，超过24B。失败证据保留，不改阈值。仅M9N startup adapter私有上下文384B改用现成PLATFORM_CPU_FAST_BSS；它含controller/target/23项解码数值/标志与计时，不含UART/DMA buffer或handle。owner只供启动控制器CPU调用；UBX写从局部帧复制进平台TX ring，DMA取ring，不持有此上下文。

F407链接 `.ccmram_bss` NOLOAD并ALIGN8；context位于0x1000C5E0，大小0x180，8字节对齐。启动Reset_Handler在构造器/main之前清零_sccmram_bss.._eccmram_bss，Init再memset；Host和无CCM target沿用vendor-neutral普通BSS默认宏。链接脚本、启动代码、资源策略、栈大小均未改。object/ELF section/symbol与map证据已保存，.dma_bss仍8904B。

最终FLASH 321548；SRAM 102040，门槛余360、物理余29032；CCM 55904，余9632；heap0。Device stack估计2128/配置2560/余432，Telemetry2136/4096/1960，与前候选相同。这些静态报告不证明完整MSP/ISR嵌套、WCET或实机高水位。

## 最终候选实际门禁

Release ARM编译/链接、完整Host、architecture、PoT文本、真实ARM-fanalyzer编译/链接、artifact、stack/memory均exit0；RF真实生成Host13/13通过。Host：executables=72 checks=4400646 failures=0 compile_pass_cases=7 expected_compile_failures=17。analyzer编译单元105，warning行0。PoT：6066 checks, 108 first-party C files, 2640 functions; 749 assertion recommendations. Critical-contract review NOT PROVEN; manual acceptance pending.

Debug build与artifact仍exit2，缺既有KF6 SystemNavigationBackend Predict/Initialize/SnapshotGet/Reset实现及伴随relocation错误；原170f1cb基线和本任务旧候选已同样复现，日志保留。本次不改KF6接口、不宣称Debug ELF/BIN成功。PoT全项目关键合同审查NOT_PROVEN，不能宣称原PoT/NASA合规或硬件资格。父报告RF实机2/10仍是独立未解决问题，本任务没有验证/修改其根因，也未合入Baro。

## 交付

ELF SHA256 `f0c0b8dd05bf0d4e10ee44dd1be73a937899abf4247631821f076a6c6514920a`

BIN SHA256 `0546b5d639946fb38e0f1651cdfbf1b9dd7261e24119146f4285b88dd0d55da2`

ZIP `D:\python_software\SilverStar\.work\RfM9nIntegration_20261002\.work\combo_final2_evidence\SS_RfM9n_1_SourceFirmware.zip`，SHA256 `5ab80407be9e861475d51b03051ef002323b74bd473416360f731b363b92f1ab`。内含完整生成项目及Release ELF/BIN/HEX/MAP和独立fixture。所有失败试次保留在独立 .work 及本目录gzip日志；未将旧候选的通过拼成最终结果。
