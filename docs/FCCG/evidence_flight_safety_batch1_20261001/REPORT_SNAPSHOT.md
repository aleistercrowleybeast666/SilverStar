# Flight安全契约第一批与AGENTS验收规范

**阶段结果：AGENTS规范已补充；Power of Ten尚未补齐。原检查器Flight从181降至180个Rule5缺口，仍FAIL；Ground继续0缺口、门禁通过。** 本报告不是全固件原版十条合规声明，也不是外场、硬件或完整应用验收。

本批固件源码提交为`95abac8c06535e144e0e91f3dfafaaf02a4bd782`；Host错误路径修正和最终AGENTS说明为`5920139a8daf7bd4812043a11606df7b42450af4`。后者没有改变固件源码、生成器、数学、配置或decoder；重新生成后618份C/头文件/汇编/链接/构建文件及decoder与已编译镜像逐字节相同。原PoT检查器与ca74c379的Git字节一致，阈值、允许列表、源码范围和真实失败预期未改。

## 实际修复

- `SystemNavigationHealth_GroupGet`在普通时间错误返回前完成验证，输出保持不变，避免失败却发布部分快照。已锁存的模型/IMU故障仍可在早于epoch的查询时间输出INVALID，未削弱故障优先语义。
- `Observe`拒绝四个非布尔标志，以及早于epoch或上次成功评估的评估时间；拒绝前不修改组状态。延迟的物理/接收时间可早于epoch；不同来源相同序号和接收tick仍合法。KF6/ESKF15生产者使用其当前状态时间作为evaluation，未把延迟测量时刻误当评估时间。
- 组状态的枚举、质量及有效标志在临界区内检查，损坏时先锁存真实断言故障，阻止输出/状态提交。Overall移除对本地对象地址的无效断言，使用受保护的模型故障/IMU故障mask快照及真实存储状态约束，补齐该函数的门禁缺口。没有修改导航数学或滤波参数。
- SPSC入队/出队在复制前检查最大容量、各自拥有的槽位游标和序号距离。损坏游标不再越过逻辑队列边界；距离超过容量不再当作普通满队列/可读数据。普通FULL/EMPTY/BAD_PARAM及统计语义保持。没有比较跨所有者的槽位关系，亦未将槽位游标错误等同16位序号模容量。
- 队列头文件明确单生产者/单消费者、独占Reset、存储跨度及不可变容量/元素大小、目标16位原子访问要求；Count仍是有界建议值，不是预留。当前volatile/fence实现不宣称为可移植C多线程队列，也不能检测所有仍在范围内的元数据损坏或证明调用者真实分配跨度。

新增Host故障fixture编译实际队列、导航健康和断言实现，只拦截终端trap以核对真实fault record和未提交状态。setjmp/longjmp只存在于测试，不进入固件；这不是MCU故障恢复证据。额外canary存储确保修复前的逻辑越界可安全观测，不利用宿主C未定义行为冒充故障复现。

## 验证及失败记录

| 验证 | 实际结论 |
|---|---|
| 修改前新增20项契约测试 | 18 FAIL、2正常PASS；基线产品为ca74c379，失败日志完整保留。 |
| 修改后20项新契约与26项已有SX1281负例/正常测试 | 46 PASS。包括输出原子性、epoch/成功时间回退、四布尔错误、组/模型/IMU状态损坏、队列游标/容量/序号损坏，以及正常延迟/恢复/故障锁存。非二次幂容量3累计21万次入/出队，覆盖16位序号回绕。 |
| Ground ARM | 新生成、新编译链接退出0；独立目录起初没有旧ELF。 |
| Ground静态分析 | 选中14份第一方源码实际`-fanalyzer -c`，全部退出0；double-free canary被分析器预期拒绝，退出1。不是syntax-only结果。 |
| Flight ARM Release | 新生成、新编译链接退出0，F407 hard M4F、-O2。 |
| Flight StaticAnalysis Release | 独立StaticAnalysis目录实际重新编译/链接，第一方`-fanalyzer`及严格warning，退出0；没有复用普通Release对象。 |
| 首次完整Host尝试 | 在estimator_preparation_actual的LTO编译拒绝，退出2；不计PASS。 |
| 最终单次完整Host | 72程序、4,393,820检查、0失败，8编译正例、16预期编译拒绝；完整退出0。包含存储完整性附加门禁，未拼接分批通过结果。 |
| 原PoT门禁 | 最终重新生成镜像Flight退出2、180真实Rule5缺口；Ground退出0、0缺口。未skip/xfail这些失败。 |
| Flight架构、静态任务栈、链接产物 | 分别退出0，范围见原始报告；不代替PoT或硬件验证。 |

首次Host失败是测试在`TEST_CHECK(GroupGet(...) == OK)`后仍继续访问可能未初始化的输出。TEST_CHECK记录失败而不终止函数；原代码错误返回时也写输出，新的原子错误契约使GCC16.1 LTO发现该用法。测试现在保存返回码、保留原成功断言，并在已记录失败后返回，避免错误路径读取未初始化对象；原状态、时间、variance和NIS数值断言与容差全部保留。正常路径检查数量未变。未用零初始化或删断言掩盖失败。中间一次声明放错函数的编译错误也保留为开发中记录，不当作有效基线或产品回归结论。

Arm GNU14.3.Rel1/GCC14.3.1 20250623、Make4.4.1；Host GCC16.1.0、Python3.14。所有命令、版本、退出码、时长、工程配置/生成来源和文件hash在[证据索引](evidence_flight_safety_batch1_20261001/INDEX.json)及两个MANIFEST内。

## 隔离工程、资源与边界

编译验证镜像：`D:\python_software\SilverStar\.work\FlightSafety_95abac8\ExistingHardware\SilverStar.ssproject`。

最终Host/原PoT重新生成镜像：`D:\python_software\SilverStar\.work\FlightSafety_5920139\ExistingHardware\SilverStar.ssproject`，只跑Host/PoT；固件618文件与前者字节相同，因此沿用前者的明确固件编译证据，不冒称后者新编译。配置来自原FinalCandidate_ddb73bb ExistingHardware，仍KF6/F407 SS0.5 Flight、F103 UART Ground。

**这些是隔离验证工程，不是新的用户最终候选。** 没有更新D:\stm32_project的FinalCandidate、GroundSafety、FrozenRound5、旧SS_0_5_TEST_4或导入路线；没有开展新四路线验收。最终外场固件由用户自行生成。此次无刷写、START、执行器、原生GUI、串口或实板测试；没有资源压缩、Python卸载、关机、推送或发布。

| 实际Release ELF | SHA256 | Flash占用 | main SRAM占用/剩余 | CCM占用/剩余 |
|---|---|---:|---:|---:|
| Ground | `a69abfea841214951dcf2879bded87f7b43f2b9c8aadb715dcb1ba95652a350b` | 21896 B | 实际地址extent14128/6352 B | 无CCM |
| Flight | `6fd1587b24f51d68e5591cdf1a0117bfaae40a73bc0086481f326d9905ee777a` | 315228 B | 101280/29792 B | 55432/10104 B |

Ground相同hash来自本次独立新编译，不是复制旧ELF。Ground已包含MSP1024及对齐；Flight含MSP1024、CCM任务栈27648；heap预留0，artifact未发现allocator运行符号。Flight Flash较0e1e5e7批增加480B，两个RAM域未增加。`.ssdecoder`仍为`63673624043bfb1064cb6645b8b13837a42c91ea7085162844f035c0d0b217e6`，聚合2、记录/重算契约未变；旧用户晨报的正确澄清也未改动。

| 任务 | 预留B | 最坏已知静态预算B | 静态margin B |
|---|---:|---:|---:|
| Device | 2560 | 2128 | 432 |
| INS | 3072 | 2240 | 832 |
| Estimator | 4096 | 3244 | 852 |
| Flight | 4096 | 3600 | 496 |
| Logger | 3072 | 2104 | 968 |
| Serial | 6144 | 4944 | 1200 |
| Telemetry | 4096 | 2136 | 1960 |
| Idle | 512 | 256 | 256 |

报告来自本次Release ELF与152份.su及库反汇编，在覆盖的任务路径上未知间接调用、动态frame、递归和无法说明的SP写入fail closed。预算沿用保守256B上下文余量。这不是目标HWM；main/MSP调用链与实际ISR嵌套没有完整证明。空闲RAM不保证栈、队列或数值安全，不据此降低主频或宣布步行/飞行适用性。早期Windows访问违规仍未解释，本轮按用户指示不持续复现。

## 原版十条与剩余工作

AGENTS完整保留原工作区约束，增加原版规则、模板与生成件同步、项目偏差及第三方许可证/来源、正反例、真实ARM/分析/Host和hash要求。明确禁止恒真断言、凑数量、为行数重排/拆分、扩大例外、隐藏文件、改失败预期或弱化门禁；任何失败阻断合规声明。参考[原论文](https://spinroot.com/gerard/pdf/P10.pdf)及现有coding standard，原版Rule5平均断言密度与项目每个>20行函数的要求分别记录，不能混为一谈。

**Flight尚余180项，不是180个已发现运行故障。** [完整逐函数清单](evidence_flight_safety_batch1_20261001/REMAINING_RULE5.json)保留原诊断；分布为APP15、GNSS50、IMU14、遥测21、对准12、校准8、指示2、能力2、console27、health2、sensor status3、source selector9、startup15。本批仅消除了Overall一项；SPSC原已过计数门禁，但确有本批负例证明的防护缺陷，不能只追缺口数字。

下一批仍需逐项评审传感器帧/队列元数据、logger配置bundle部分提交、任务/ISR所有权和生命周期/READY。这些是待评审风险，不在本批虚构成已复现缺陷。纯enum/string映射和编译常量serializer若不能提供两条真实运行不变量，保留FAIL并说明语义问题，不塞冗余状态断言。现有context宏、头文件/条件编译、所有返回路径、间接调用与第三方范围仍须独立审查；原检查器绿也不能证明原版Rule1/2/6/7/8/9及全中断栈。此次未新增允许例外，没有声明第三方符合严格原版十条。

最近可信额度：父任务/用户77%（02:40 UTC）；动态未知，未重新探查或编造。模型创建证据仍为gpt-6.1-sol/high。自身两个验证协调器及子测试完成后退出；网站Cloud、其他Python、ToDesk、水母未触碰，其未保存状态未知。
