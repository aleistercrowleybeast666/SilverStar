# 私有原生 USB 路径：限定 EP0 修复与真实构建证据

> 后续状态：本页是 e7 阶段的精确候选记录。共享描述符修复后三板全部重新生成、普通/分析 ARM 构建及原样门禁的最终记录见 [descriptor-v2](descriptor-v2/README_ZH.md)。原阶段日志与源身份保留，不倒填为新版本通过。

本批修改 owning 生成器，没有修改导入的 CubeMX/ST 输入、用户工程、正式放行条件或
Power-of-Ten 例外。F103/F407 使用同一份 bounded EP0 policy；C071 mini 的独立实现
没有被替换。新增 provenance 类型的头文件闭包同时补到普通 Ground、原生 Ground
和 C071 recipe 三条生成路径。私有 backend 的陈旧“F407 未集成”提示改为已集成且
仅具有限定软件验证；formal generation 仍 BLOCKED，完整独立审查仍 NOT PROVEN。

## 实际缺陷、修复和相同回归

[pre-v4.log](pre-v4.log) 在 F103、F407 实际生成的 core/class/ioreq/policy 上，各执行
10 个独立进程，**20 个真实失败**。编译和原有每板 18 个正常 lifecycle 流程均成功，
失败不是缺工具或构建未完成。原始逐 case stderr、退出码、编译命令、生成源码 hash
及实际 harness 见 [pre-v4](pre-v4)。

- 空/错误设备句柄调用 Dispatch，原实现仍进入底层 Stall 操作。
- GET、SET 和 status 的 LL 失败没有撤销活动 EP0 状态，迟到回调仍可能继续旧阶段。
- 配置描述符多包 IN 的 continuation、其提前结束接收 arm、初始标准描述符发送，
  以及 OUT continuation helper 会吞掉 LL 失败。

`PcUsbControl_Dispatch` 先验证唯一设备 owner。共享 `PcUsbControl_Abort` 先清除
命令及 EP0 剩余长度并发布软件 STALL，再请求底层 stall；没有假设硬件 stall 成功。
六个 IO helper 保留 LL 返回值并在失败时撤销；core 对 continuation、status 和
提前结束接收检查结果，Setup 也检查撤销状态，避免标准请求内部 void helper 吞掉
初始传输失败。后续迟到回调可以返回“已处理/忽略”的 OK，但测试要求它不执行任何
LL 操作、不恢复活动状态、不重新应用旧命令；这不是控制 READY。下一条合法 SETUP
必须可以重新开始正常控制传输。

[post-v2.log](post-v2.log) 使用相同 harness 和安全预期：**20 个故障 case 全通过**，
每板原有 **18 个正常 lifecycle case** 也全部通过（2 个 pytest 包装测试，28.79 s）。
OUT continuation helper 属于直接 helper 返回值测试；当前合法 7 字节 SET 不会走
多包 OUT，未把该 helper 测试宣称为实际多包 SET 流程。

另外实际编译了两板的 `pc_usb_control.c`、`usbd_core.c`、`usbd_ioreq.c` 六个 TU，
`-std=c11 -O2 -Wall -Wextra -Werror -pedantic -fanalyzer` 全部 exit 0、无诊断。
见 [receipt-v1.json](receipt-v1.json) 和 [post-v2](post-v2)。旧 normal harness 的
F407 BOS 重复命令宏、F103 上游 unused parameter 警告完整留存。严格 TU 分析仅
去掉与实际 header 已有 `0U` 重复的 BOS 命令参数，未修改头、加 warning suppression
或把整个 vendor 栈宣称为 strict-warning clean。

## 新头文件闭包及三个实际 ARM 构型

[arm-v1.log](arm-v1.log) 保留两板真实 ARM 构建失败：`system_device_types.h` 引用了
新增 `system_navigation_provenance.h`，地面站生成白名单却没有带上它。修复各 owning
列表后，[headers-v1.log](headers-v1.log) 对普通 Ground 和 C071 实际生成的三个头
执行真实 GCC strict/analyzer 编译与运行，**2 passed / 33.69 s**。

| 实际私有构型 | Fresh normal + analyzer ARM | 原样 emitted 四门禁 |
| --- | --- | --- |
| STM32F103C8T6 / SX1281 E28 | CompiledCandidate；ABI/region 通过，warning_diagnostics=[] | architecture、Host、power10、artifact 全 exit 0 |
| STM32F407VET6 / SX1281 E28 | CompiledCandidate；ABI/region 通过，warning_diagnostics=[] | architecture、Host、power10、artifact 全 exit 0 |
| STM32C071FBP6 mini / SX1281 E28 | CompiledCandidate；实际 Cortex-M0+ / 48 MHz，warning_diagnostics=[] | architecture、Host、power10、artifact 全 exit 0 |

两板完整测试 [arm-v2.log](arm-v2.log)：**2 passed / 393.36 s**；C071 独立实际构建
[c071-arm-v1.log](c071-arm-v1.log)：**1 passed / 191.72 s**。C071 没有借用 F103/F407
的链接结果，也没有把其模拟 endpoint Host 服务冒充真实 EP0/硬件测试。

四门禁由 [run_private_checks.py](run_private_checks.py) 逐个调用生成的 Makefile，
最多 `-j2`，没有改规则；`artifact-check` 还执行生成 Make 的实际 ARM 编译/链接及
memory audit。完整日志和命令见 [buildchecks-v1](buildchecks-v1)。每板 emitted Host
实际执行 5 个生成源码 executable，HAL/radio 是 Host ports。P10 文本检查分别为：
F103 549 checks / 20 first-party C / 193 functions，F407 553 / 20 / 195，
C071 630 / 23 / 223；三者都明确 **critical-contract review NOT PROVEN**。

[arm-final-receipt.json](arm-final-receipt.json) 包含所有前后 ARM/门禁结果、当前 7 个
owning 文件 hash 和归档 hash。五个 `*-artifacts.zip` 原字节保存失败/成功的实际
source-snapshot、完整 commands.log、compiler/backend receipt、配置和图；成功批次
另外保存 ELF/map、memory/artifact 报告。源快照是可审计 dirty epoch，不冒称执行时
工作区干净；root 统一进行最终源码与证据提交。

## 运行入口和保留范围

从 SilverStar 根目录使用 TreeDiagram 的 Python venv，设置 `PYTHONPATH=apps/SCG/src`，
PATH 中保留 `D:/msys64/ucrt64/bin` 和已安装的 Arm GNU Toolchain 14.3：

```text
python -m pytest apps/SCG/tests/test_native_control_faults.py -q --basetemp=<新短目录>
python -m pytest apps/SCG/tests/test_native_ground_backend.py -k real_backend_bound_build_receipt -q --basetemp=<新短目录>
python -m pytest apps/SCG/tests/test_usb_ground_backend.py -k real_c071_unified_build -q --basetemp=<新短目录>
python docs/evidence/software_completion_20261101/usb-exact/run_private_checks.py <已成功私有构建目录> <板型>
```

环境需显式绑定实际 native/独立 IRQ header/mini companion 输入及 ARM 开关；本批
精确配置、路径和所有编译参数保存在日志、index JSONL 与压缩的源快照。临时构建
使用 `.work/sc-261101-usb`，它是长任务目录
`.work/0.1.3-software-completion-20261101/usb-exact` 的已记录短路径，保留了原来的
Windows 路径长度拒绝规则。没有移走或改写原始输入。

`pre-v1/v2/v3` 分别为临时父目录、fixture 模型配置、Windows 路径长度 setup 错误；
它们不是运行期缺陷证据。`post-v1` 为 F103 通过、F407 indexed `return ret` 形态的
生成保护拒绝，随后按实际已固定 profile 修正；这些失败日志均保留。

## 准确未证明项

上述证据只覆盖指定软件边界和实际链接产物，不建立完整 EP0/所有异步交错、全程序
critical contracts、运行栈裕量、MCU WCET、物理时钟/USB/radio/飞行资格。C071 的
此次新验证是 header 闭包、真实 ARM 和既有 bridge/transport Host，未把 F103/F407
的 20 个 fault case 归给 C071。generic 原生路径由 root 另外验证，结果不与本批混用。
所有正式/硬件准入门禁保留；没有连接 USB 设备、烧写、发射或执行运动操作。P10 的
文本 PASS 不等于原始十条规则全合规、完整人工安全接受或 NASA 认证。
