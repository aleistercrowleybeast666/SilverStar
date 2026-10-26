# 通信、任务与解码统一改造（开发中）

基线 `3ee3dcb340a22c89d2b11c54e2de2ef5068b82fc`，分支 `feature/usb-transport-0.1.3-20261013`。
本次是开发提交，不能视为全部任务验收完成。历史 H743 报告、IOC、估计器数学及旧 M0 payload 保持原样。

## 对应原任务 A–G

| 项 | 已实现 | 未完成/限制 |
|---|---|---|
| A | 共享 wire/对象契约；显式选择新协议；保留 M0 与 1.2 包 | 尚无批量迁移；旧工程选择新协议后需重新生成两端 |
| B | S/H 新 codec、8B头/u16序号/启动会话；SX1281物理方向切换、TX_DONE/恢复、有界事件/ACK调度 | RF/硬件时序未测；最长更新间隔尚无独立断言；NRF组合明确拒绝；新生成物栈闭包尚未证明 |
| C | 绝对GNSS位置、缓存点及电压年龄、真实健康、落地寻回、被动重连、事件去重、坐标/地图 | 系统活性bit9无provider，保持未知；有限历史不宣称完整；自定义阶段语义仍依赖D |
| D | 板卡优先/两列硬件/第三页生成选择；共享链路页末；修复临时顶层闪窗；独立阶段事务弹窗；v2退出边界 | 任意阶段/实例调度仍是桌面参考，固件生成明确拒绝；自定义MCU阶段事件生产/映射、按目标独立过期判定未完成；旧内联编辑器保留 |
| E | ssdecoder1.3六成员/对象校验/generation hash；1.2精确读取；显式包→精确缓存→有界目录搜索 | SSMS后半飞行配置section保持opaque；尚无完整对象可视化解码器；GUI搜索目录设置未完成 |
| F | 默认/生成宏为Airborne <4g；项目4与原生8映射保持；Host读回失败/不匹配测试 | 硬件实际读回未验证，缓存或ACK不等于板上读回 |
| G | Host/Qt/数据兼容检查；新生成F407/H743 ARM构建、分析及门禁 | C071新协议ARM未重跑；新栈依赖不在历史证明中，门禁保持失败；手工关键契约接受NOT PROVEN；无RF/板测/飞测 |

## 操作与迁移

1. SCG第一页选两端板卡和设备；未勾选本次生成时仍可编辑地面硬件。共享链路选择协议。新工程默认SS-TM-S 0.1；M0为明确的旧协议，不能混用wire。
2. 第二页既有系统生命周期可以生成。显式参考流程支持稳定阶段ID、顺序、条件及共享参数。点击参考阶段打开独立事务弹窗，确定统一提交，取消丢弃草稿。自定义调度尚未接入MCU，生成会报错，不能绕过检查。
3. 第三页选择目标并生成。飞控同时输出对应`.ssdecoder`；仅生成地面不制造飞控Descriptor。
4. FLP用`--auto-find`先找Descriptor对应精确缓存，再扫描任务目录及最多四个`--decoder-search-dir`。明确指定了存在但错误的包会报错，不偷偷改用缓存。
5. `mission_functions.schema_version=1`的进入结束边界保持原义；显式选择“阶段退出”时保存为v2：开始阶段进入至结束阶段退出，包含结束阶段，相同阶段可持续。这不赋予任意区间固件执行能力。

## Wire与调度

机器契约：`contracts/ss_tm_v0_1.json`，安装资源镜像为`silverstar_telemetry/data/ss_tm_v0_1.json`。
全部消息有版本/profile/序号/boot_session；多字节整数小端，逻辑帧≤61B，不额外添加应用CRC。

| 消息 | M0 B | SS-TM B |
|---|---:|---:|
| 主遥测 | 50 | 56 |
| 预飞 | 26 | 32 |
| 能力 | 9 | 24（含发布单调时间、编码与量程） |
| 预飞状态/传感器/保留导航消息 | 9 | 15 |
| 命令 | 9 | 15 |
| ACK | 9 | 16（关联序号u16） |
| 事件 | 9 | 32（event_id、原始时间、阶段/实例/事务） |
| POSITION/HEALTH | 无 | 28/16 |

START经原生命周期准入；先尝试最终ACK，确认实际完成或达到2s有界截止后切换S物理方向。本地任务不等地面确认。LOCAL/CONSOLE/AIR成功诊断产生开始事件，保留原始时间和事务关联；boot_session不随任务重置。nonce使用MCU硬件RNG，有界失败，不回退成固定值或系统tick；不充当认证或全球唯一身份。

事件最多16项，默认首次+2次广播、250ms重复间隔、30s过期。内容与event_id不因重发改变，发送帧序号改变。满/过期会诊断丢弃。非START ACK最多1Hz；周期包临发送构帧，跟踪TX_DONE。入队和真实发送失败区分，序号缺口不全部称为RF丢包。

PHY不变：SF10、BW标签800kHz/计算812500Hz、CR4/5、16符号前导、显式头、硬件CRC；频道、模块功率不自动改变。26项保留检查见`.work/tm_20261026/preservation.json`。

| 计划 | 默认消息Hz | FC TX占比 | 含RX grant/控制预留占比 |
|---|---|---:|---:|
| S飞行 | 56B×5/28B×1/16B×0.5 | 65.99% | 65.99% |
| H飞行 | 56B×2/28B×0.5/16B×0.5+ACK≤1Hz | 35.04% | 83.84% |
| S预飞（含ACK≤1Hz） | 32B×1/24B×0.5/15B×0.5/POSITION×1/HEALTH×0.5 | 30.83% | 85.73% |
| H预飞（含ACK≤1Hz） | 同上，POSITION×0.5 | 27.16% | 75.96% |
| S/H落地 | POSITION×1/HEALTH×0.2 | 8.56% | 8.56%/23.20% |

这是与SX128x整数模型一致的计算预算，含122ms RX grant；上行命令使用已有grant，不重复加空口时间。状态变化、传感器快照和事件使用剩余有限机会，突发可降速/过期，不保证每项送达。超预算PHY配置明确拒绝，不偷偷改PHY。未做RF测量。

## 数据和校准

ssdecoder1.3严格成员：manifest、record_catalog、object_catalog、project_semantics、checksums、README。对象目录绑定成员校验、manifest摘要与新generation hash。原1.2身份计算不变。
SSLOG容器、SSIC/SSOB/SSMS及磁校准包实际布局不变。新校准只更新设备结果和内容校验，历史任务及源日志只读。包内纯声明数据不加载Python/C代码。

## GNSS

目标Airborne <4g，SilverStar枚举4，u-blox原生8；25Hz/921600等无关设置不改。启动仍要求逐键读回比较及新PVT；Host覆盖丢ACK、错值和无效读回等路径。
依据：[u-blox M9 SPG4.04 Interface Description，Table25](https://content.u-blox.com/sites/default/files/u-blox-M9-SPG-4.04_InterfaceDescription_UBX-21022436.pdf)。原生4是Automotive，不能套到项目枚举4。**本轮硬件实际读回未验证。**

## 可复现验证

本次临时输出属于`.work/tm_20261026`，旧失败证据保留。使用仓库Python3.14、Host GCC16.1、Arm GNU14.3 rel1；工具版本以实际输出为准。

```powershell
$env:PYTHONPATH='apps/SCG/src;apps/FLP/src;apps/GSHC'
$env:QT_QPA_PLATFORM='offscreen'
# PATH加入Host GCC、ARM GCC和仓库.venv/Scripts
.venv/Scripts/python.exe -m pytest apps/SCG/tests/test_ss_tm_scheduler_host.py apps/SCG/tests/test_ss_tm_contract.py --basetemp=.work/tm_reproduce -q
.venv/Scripts/python.exe apps/SCG/tools/validation/h743_static_validate.py --cube-project .work/h7_20261025/cube --output .work/tm_reproduce_h743 --algorithms eskf20 --run --arm-gcc 'D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-gcc.exe' --make D:/msys64/ucrt64/bin/mingw32-make.exe --host-gcc D:/msys64/ucrt64/bin/gcc.exe --jobs 4
```

输出目录应是新的未存在目录。工具PASS只对应其范围，不等于原版Power of Ten合规或飞行资格。没有全仓回归、板端时间/栈高水位、定位精度、USB端到端或RF距离证明。

## 本次证据

| 检查 | 实际结果 | 保留记录（仓库根目录下） |
|---|---|---|
| S/H生成服务+实际SX1281驱动、codec、阶段事务、M9N adapter | 30通过 | `.work/tm_20261026/scheduler_verified.xml`及同名log |
| wire契约、资源镜像、产品版本 | 31通过 | `.work/tm_20261026/final_contract.xml` |
| GSHC定位/健康/会话/ACK/接收管线 | 50通过，3子测试通过 | `.work/tm_20261026/gshc_verified.xml` |
| FLP原1.2/新1.3/篡改/自动精确缓存及目录查找 | 56通过 | `.work/tm_20261026/flp_verified.xml` |
| GUI/旧调度/源选择器组合首次 | 66通过，1失败并有相关Qt异常；未称全套通过 | `.work/tm_20261026/final_gui.xml` |
| 修复退出边界草稿收集后相关GUI复测 | 5通过；包括跨阶段保存及整弹窗取消 | `.work/tm_20261026/gui_repair.xml` |
| F407 S/H新生成工程 | all/architecture/power10/static-analysis/artifact均exit0；stack-report均exit2 | `.work/tm_20261026/f407_verified_gates.json`及分项log |
| H743 ESKF20单BMI088新S工程 | 同上五项exit0；stack-report exit2 | `.work/tm_20261026/h743_verified/summary.json`及分项log |

F407 S/H分别使用`radio_handshake.ssproject`显式迁移协议后由当前生成器生成；H743使用原验证工具的25MHz HSE、480MHz、SWD静态配置，BMI088/NEO-M9N/BMP390/MMC5983MA/E28-2G4M27SX，测试初始化假设未变。构建命令完整记录于上述JSON，均为Release、实际Arm GNU14.3 rel1、严格警告及真实`-fanalyzer`编译，不是syntax-only。

F407 S主SRAM为102308B（原门禁102400B），CCM为64448B、余1088B。事件及ACK缓存迁到既有CPU专用区；radio入队同步复制，DMA不直接访问这些缓存。早先SRAM超限的失败log保留；没有提高预算。

栈失败原因：F407遇到变化后的`Generated/Inc/project_flight_config.h`编译依赖；H743构建声明不匹配冻结输入清单。保持原清单、哈希、门禁，没有把新代码添加进历史证明。`power10-check`也明确报告手工critical-contract review NOT PROVEN，不能称完成安全接受。当前已编译的三个新工程，其关键遥测源码与所属payload哈希一致，见`compiled_owner_sources_match.json`。

计数来自Host空口时间模型驱动的实际`TX_DONE`，不是仅入队次数，也不是硬件RF：

| 场景 | 主遥测/定位/健康完成数 | 其他结果 |
|---|---|---|
| S持续60s（首501ms起调度） | 297/60/30 | 387完成，0失败，队列≤1 |
| H持续60s（同上） | 119/30/30 | 179完成，0失败，队列≤1 |
| S突发12个事件、运行约9.5s | 47/10/5 | 32次事件广播；有限机会内未全部送出 |
| H同样突发 | 19/5/5 | 13次事件广播 |
| S预飞20s、持续命令反馈 | 预飞20/定位20/健康10 | CAP10、ACK20，保持半双工 |
| H同样预飞 | 预飞20/定位10/健康10 | CAP10、ACK20，保持半双工 |

另通过落地继续定位、LOCAL开始事件只生成一次且广播三次内容/原始时间一致、最终START ACK不产生TX_DONE时仍有界继续飞行等测试。具体旧失败和修复后的记录分别保留，不累加为未经执行的全仓通过数。

下一批优先完成D的实际固件阶段生产/消费及共享实例调度、按目标过期身份，再完成E的剩余对象section与G的C071/新栈输入闭包复核。没有通过栈门禁前不标记为已完成静态安全验收；没有硬件不标记板测或飞测。
