# SilverStar 夜间修复最终交接

完整回归已结束；本次仅澄清聚合配置与回放证据边界，不重新执行测试，不宣称全绿。

22:27发现的真实FLP阻塞已修复：最初生产加载拒绝`mechanization_aggregation`，失败日志`.work/p51_decoder_identity_driver.log`保留。最终可信契约仅允许int32/1或2/samples/value，区分固件配置与回放调参，旧包不补写默认值；文件头/SYSTEM_CONFIG/INERTIAL_INCREMENT必须与新声明一致。未知字段、错误类型/值、错误身份继续拒绝。**最终ExistingHardware/ImportedHardware候选均为聚合2，真实生成decoder与同身份合成日志的按记录配置重算测试通过并输出有限。** 聚合1的合法同身份日志可加载查看，但不支持当前要求2子样本的PureINS/KF6重算器；ESKF15不得把单采样corrected-IMU静默配成双采样，独立身体输入仍遵守其精确记录契约。限制针对聚合1，不是聚合2不可重算。

Recorded查看与重算分别判断：新导入默认分析源为“飞控记录”，不会自动启动离线复算。两份候选均启用ESTIMATOR和PURE_INS导航记录（40000µs周期），实际日志包含有效记录时，Recorded路径可显示固件位置/速度/姿态并优先使用KF6，不要求运行重算器。原生真实decoder配对fixture未包含这些导航快照，因此截图Recorded N/A不代表真实候选不能看轨迹。该fixture仅证明加载、缓存往返及按记录配置重算有有限输出，不证明与候选固件记录逐点一致；“离线插件默认配置”也是单独模式，不能当作实录参数。既有C数值/联合对照不替代板上步行实录、轨迹完整性或真值验收；这些仍未测。本次澄清仅改文档和晨报副本，数学源码、固件、decoder及已记录完整测试结果不变。

## 明早使用的候选

固件/生成器来源：`ddb73bb40b15decbf5914933f2822aa98849b8f6`。最终应用及测试源码：`b3f53a76432b464020199605501a82d589b6988a`。499531d仅修正需求迁移测试，cd9d99f修FLP读取/回放准入，b3f53a7修C联合测试的源码所有者定位；生成器/固件/decoder字节均未再变，二进制来源准确保留ddb73bb，未无意义重复四构建。

**推荐：`D:\stm32_project\SS_0_5_TEST_4_versions\FinalCandidate_ddb73bb_20261001\ExistingHardware\SilverStar.ssproject`。** 备用导入路线为同版本目录 `ImportedHardware\SilverStar.ssproject`。先读该目录 `README_FIRST.md`，精确配置、decoder、ELF/MAP/BIN/HEX及源码哈希对应表为 `ARTIFACT_CONFIG_DECODER_MANIFEST.json`。两路线均KF6 / F407 SS0.5 Flight + F103 UART Ground，显示名FINAL_EXISTING / FINAL_IMPORTED。

原SS_0_5_TEST_4、ImportedHardware_20261001、FinalCandidate_18afe8c_20261001和FrozenRound5保留。未覆盖用户源码；未push、发布、打包、刷写、START或连接执行器；未改网络/安全/电源，未卸载Python、未关机。

## P0逐项结论

| 要求 | 结论 |
|---|---|
| 传感器标题不泄漏内部ID/变量 | PASS：面向用户的中英文名称API，稳定机器ID不变，未知插件有展示fallback。 |
| 新建默认KF6及算法顺序 | PASS：纯惯导、KF6、ESKF15，默认KF6，保留旧工程迁移。 |
| 日志/开伞无需回跳勾惯导 | PASS：新建流程可直接配置；原生新建、保存重开覆盖。 |
| 初对准日志真实依赖 | PASS：必需结果/证据日志已勾选且说明锁定原因；可选项按生产者依赖处理，未放宽必要校验。 |
| Ground配置/硬件拆分 | PASS：PC接口等逻辑在独立配置页，硬件页保留使用已有、使用导入、保存硬件及生成；八页契约回归。 |
| 确认工程立即建三目录 | PASS：Flight_Controller、Ground_Station、Log立即建立，失败明确提示，不提前覆盖数据；另存为草稿三目录为空。 |
| 稳定ID、旧工程、无线共享 | PASS：保存重开、旧配置、双方兼容、UI/模型一致；双方独立引脚和PC串口不强制同值。SPI扩展仍延期。 |
| 初对准原生边界 | 已测PASS：外部姿态往返、矢量增删/失焦/确认取消/快速操作，保留2–6条、恰好1重力/至多1磁场和延后事件修复。 |

前期完整矩阵见 [P0/P1](NIGHT_ACCEPTANCE_20261001.md)。42项整组与最后第43项独立复验均留有记录，不能改写成同一次43项整组。

## 原51失败的处理

原干净检出679项：51 FAIL、627 PASS、1 SKIP，1151.81s，退出1；`.work/night_finish_clean_final.log`保留。

- **产品缺陷：**插入Ground配置页后，错误导航仍用旧数字索引。改为从实际编辑控件确定所属页，保留焦点/高亮，新增六类页面归属和模型不变负例。Ground PC错误指向配置页，缺存储设备指向设备页，缺SDIO指向硬件资源页。
- **需求迁移预期：**七页/旧序列按Ground配置拆分更新，仍检查真实硬件页对象及字段归属；日志依赖文字更新，原已选中、锁定、点击不能取消、模型强制恢复断言保留；另存为改为三个目录存在且为空，继续保证没有隐式生成固件。最初两处dirty预期来自本任务，未恢复或覆盖他人修改。
- **文档误报：**收窄“所有Existing均非法”的过宽判断到废弃校准操作；合法ExistingHardware路线不再误报，旧校准入口未恢复。
- **Windows深路径：**普通Win32/工具链支持边界实际触发，不能称固件数学失败。不改长路径/安全设置。干净检出缩短为`.work/c`，临时目录应用内`.work/t*`。产品复制统一WorkspacePolicy：全文件路径小于260字符、父目录小于248；超限在复制前返回`WINDOWS_PATH_TOO_LONG`并建议缩短根目录。权限错误继续传播，所有权/原子回滚保护不变。新增真实生成超限、复制无副作用、权限错误负例。**不承诺任意深路径可生成，不隐藏失败。**
- **冻结字节：**Git自动文本换行导致AIR原始哈希在干净检出不同，协议逻辑未变。两份冻结协议C使用`-text`并提交原始字节，期望哈希没改；AIR/SSLOG原工作区与干净检出原始SHA256已一致，忽略行尾的协议diff为空。`.work/p51_wire_clean_bytes.json`。

分类子集46 PASS、短路径干净检出42 PASS。原51选择器在ddb73bb执行48 PASS/3 FAIL/1065.31s：另存为旧断言后来需求修正并独立1 PASS/12.46s，另两项为真实Rule5门禁失败。未将分批PASS拼接成全套。

**499531d单次完整回归已结束：688项，685 PASS/2 FAIL/1 SKIP，1787.51s，退出1。** 新增9项：六页面归属、两WorkspacePolicy、一个实际生成路径负例。`.work/p51_full.log`、`.work/p51_full.xml`、`.work/p51_full.exit.txt`记录全失败/跳过；失败均为原KF6/PureINS矩阵的真实Rule5门禁，跳过为`test_prompt_acceptance.py:283`本机没有只读历史参考固件。十项实际ARM artifact测试均执行。FLP新增修复之后，**最终同源码b3f53a7的FCCG完整688也已结束：685 PASS/2 FAIL/1 SKIP，退出1。** 2 failed, 685 passed, 1 skipped in 1796.75s (0:29:56)。独立记录`.work/fccg_final_full.log/.xml/.exit.txt`；两失败仍是KF6/PureINS真实PoT门禁，唯一跳过仍为缺少只读历史参考固件。没有把旧结果充作新源码运行。

最终b3f53a7干净检出FLP完整：**512 PASS/9 SKIP，362.09s，退出0**，`.work/flp_final_full.log/.xml/.exit.txt`。16个可信聚合契约负例/旧兼容/单采样准入测试和六个真实生成decoder+合成日志生产开对、缓存往返、三算法回放/拒绝测试全部执行。九跳过详情：SS0000当前实录1项、SS0007历史实录3项、SS0014任务1项、SS_TEST_0历史Golden实录3项、一个明确要求历史revision2 C Golden配对的联合门禁未提供。最后一项不是实机数据，不能把当前revision3数据冒充历史revision2。均不计PASS；原始明细保留。

启用当前FCCG C联合测试时发现五个测试文件写死已删除core0_0_12目录；三项初始编译FAIL日志`.work/flp_current_c_probe.log`保留。现在从明确选中的检出里定位唯一声明Common所有者，找不到/多重都失败，不回退旧源码；数学断言/容差未改。实际14项C编译/codec/数值/实际C产生日志与真实生成ESKF decoder回放一致性通过，已包含在完整FLP运行。

## 四次新ARM构建

均在新目录、无旧ELF前提下重新生成并编译链接。命令、工具版本、时刻、退出码、ELF/MAP/BIN/HEX/hash见`.work/p51_candidates/*.json`及同名日志。现有路线选择仓库真实硬件/固件资源；导入路线通过原生QFileDialog导入从合法CubeMX快照派生的有效IOC并配置真实资源，来源记录`.work/night_import_sources_20260930`。不冒称本轮由CubeMX GUI新产出。

| 路线 | 目标 | 退出码 | text/data/bss(B) | ELF SHA256 |
|---|---|---:|---|---|
| ExistingHardware | Flight | 0 | 312492/1136/155576 | `40913eeb7b1eba8951308d41a270f6b35002683b99169f7a87b124e6b0fce6a9` |
| ExistingHardware | Ground | 0 | 20844/12/14112 | `115e3cc7e4e7d6cb17b625b5616e4643f12557e7785d220b3bd0d5810b3ef596` |
| ImportedHardware | Flight | 0 | 312492/1136/155584 | `6cf7e186a118ada8f386d082796d2e3f1496b80fd850a0c42da0389a9219399f` |
| ImportedHardware | Ground | 0 | 20844/12/14112 | `21cccbb48b383a23f2456f2e73fcaae132e383c0e8cd768ac6d67a80742edb95` |

ArmGNU14.3.Rel1/GCC14.3.1 20250623、Make4.4.1。Flight：`mingw32-make -j2 all CONFIG=Release GCC_PATH="D:/Arm GNU Toolchain/14.3 rel1/bin"`；Ground：同一ARM PATH下`mingw32-make -j2 all`。Ground哈希与旧件相同是独立新编译结果。两路线Flight最新栈报告退出0。

## 原生GUI与五门禁

实际Windows Qt/QtTest可见窗口（非offscreen/mock）：两路线新建/取消/三个目录/KF6/导入/保存/生成，八页中英文/主题/1.25缩放，外部姿态、矢量、失焦、确认取消、错误恢复、无线兼容、重复点击和生成关闭PASS。`.work/p51_generation`、`.work/p51_edges`退出0。额外真实错误计划窗口：硬件错误、缺存储且开日志（首错误协议传输）、缺存储且关日志均拒绝生成并导航至首错误实际页，模型/文件不变；`.work/p51_native_validation3.exit.txt`为0。此前该harness错误预期多错误场景一律跳设备页，失败日志保留；产品按首错误定位并无该缺陷。

GSHC小窗16字体四页/断开状态、FLP浅色工程名与五页原生通过；FLP只使用精确配对合成日志/decoder/Descriptor，源哈希不变，不当实机证据。用户所称SCG五项真实入口映射为FCCG BuildRunner五按钮，证据见 [质量报告](NIGHT_QUALITY_20261001.md)。本轮重新实际点五按钮，`.work/p51_quality`保存：

最终b3f53a7再次运行FLP可见Windows Qt新建/非法名/取消/缺文件/导入、五页双语言/主题、浅色工程名、保存和原生Qt文件选择重开：PASS/退出0，`.work/flp_final_native_realdecoder_1`。这次包是**最终ExistingHardware真正生成的未修改decoder**，日志明确为合成；原包/日志哈希未变，不再以简化合成语义替代候选契约。实际ARM ELF Descriptor函数反汇编及48字节链接常量与原始生成C/生产FLP包精确校验，已有/导入各两份包PASS，并执行错误身份拒绝，`.work/p51_decoder_identity`。这是链接/软件证据，不是MCU运行实测。 原生截图中的Recorded N/A及integrity warnings来自合成fixture未提供完整实机记录流；不把该窗口当作实录完整性、记录导航解或导航精度通过。三算法数值回放和拒绝契约另由生产加载器专项测试验证。

| 检查 | 退出码 | 结果 |
|---|---:|---|
| Host Tests | 0 | PASS：72程序、4,393,820检查、8编译变体、16预期编译拒绝 |
| Architecture | 0 | PASS |
| Power of Ten | 2 | **FAIL：Flight194个Rule5覆盖缺口** |
| Static Analysis | 0 | PASS：实际ARM -fanalyzer |
| Firmware Artifact | 0 | PASS：KF6 Flash313628B/main SRAM101280B/CCMRAM55432B |

Ground PoT独立重跑退出2、13个Rule5缺口；`.work/p51_additional_gates`。要求PoT通过的KF6/PureINS测试保留失败，不改skip/xfail，不塞无意义断言。194/13是覆盖债务，不是207个运行故障；风险分组和不变量建议见 [导航报告](NIGHT_NAVIGATION_RESOURCES_20261001.md)。

![GSHC原生大字体](evidence_final_20261001/gshc_native_large_font.png)
![FLP最终真实decoder原生浅色](evidence_final_20261001/REAL_DECODER_en_US_light_page.flight.png)

## 数值、存储及资源边界

共享StorageBinding_Resolve统一校验/生成：必须一个物理TF/SD、正确SDIO、启用且无歧义FatFs三符号，关闭日志仍需存储；无效计划不创建固件/修改模型。未放宽实机TF/START，未强加完整任务到诊断连接。

INS先验证有限候选再原子提交；失败保留最后有限解、标无效、不计成功次数，日志/遥测显示失败。PureINS/KF6/ESKF15实际APP函数/C内核覆盖，融合输入故障锁存至生命周期重置。NaN/Inf/标志/dt边界/极大有限增量/派生溢出/连续恢复17场景在1/2采样聚合均0失败；正常有限2001样本旧/新逐字节一致，`.work/night_finish_nominal/result.json`。未大调滤波参数。

三模式相同配置及最小受支持配置分别实际生成/链接九构建0；完整Flash/RAM/CCM、优化/功能/栈和边界见 [资源报告](NIGHT_NAVIGATION_RESOURCES_20261001.md)。**ESKF15日志CCM64296/65536B，仅余1240B，不能称安全余量。** 最后数值修复ESKF15资源件来源18afe8c，独立目录`.resource/20261001/final_18afe8c/capture_logs_on_eskf15`，实际artifact窗口警告和最新栈检查通过；ddb后续没有导航数学修改。INS估计栈余808B、Flight496B、Device432B、Idle256B不是板测高水位。

![实际ESKF资源警告](evidence_final_20261001/eskf_actual_ccm_warning.png)

没有目标运行周期/真值/硬件测量；主频只给公式和假设，Host时间不是STM32 WCET，未构建型号不保证可运行。明早仅无执行器手持步行采集，不宣称导航精度、飞行资格或输出硬件合格。

## 尚存风险和状态

- 早期Windows访问违规**仍未解释**；后续原生启动/切页/生成/关闭未复现，不能写根因已修复。只对自身测试局部禁交互错误框和启用faulthandler，没有改全系统/结束无关应用。
- PoT194/13仍FAIL；最终FCCG685P/2F/1S、FLP512P/9S均已结束。长路径支持边界如上，使用短根目录。真实串口/TF/执行器/导航精度未测。
- 模型为父工具创建请求证据gpt-6.1-sol/high，非UI读取。最新可信额度为用户17:20UTC的82%，动态未知，未编造；按最新授权未知继续，可信低于60%才停止新工作。
- Python3.7.5已只读盘点：六个Python Software Foundation MSI组件登记，常见位置无旧解释器、查询视图无完整安装入口；当前venv为3.14、仓库要求至少3.11。不代表全盘已无残留，无法证明缓存/无管理员/无重启/其他工程无依赖，所以未尝试卸载或清登记。证据`evidence_final_20261001/PYTHON375_READONLY_INVENTORY.json`。未关机，由父协调。

最终产品与测试提交为`b3f53a76432b464020199605501a82d589b6988a`；本报告和正式证据随后独立本地文档提交，最终仓库HEAD/dirty写入`.work/final_repository_closure.json`并回报父任务。受影响源码及测试已提交，没有未提交产品改动。本任务后台测试已全部退出，日志/退出码均落盘；文档六项检查通过。截图和正式证据保留，原日志不清理。旧21:20部分报告另存`.work/NIGHT_FINAL_HANDOFF_partial_2120.md`，仅供历史审计，不作为最终推荐目录。
