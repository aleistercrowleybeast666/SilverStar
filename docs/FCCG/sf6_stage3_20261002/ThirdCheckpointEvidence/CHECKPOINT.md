# 北京时间 06:50 附近的 SF6 软件检查点

这是一轮可审查进度检查点，不是完整验收、烧录候选或硬件恢复证明。

## 当前实现与提交

- cb696bea3778a8544f934e01fc3ea375b3e24f09：用有界时序重放替代有数学反例的 affine-forward 修正；同时修复 GUI 局部排列、真实参考有效位和严格 FLP 夹具。
- 41a3e9559cb48036c7329ea98b351e56dcdd5395：按父线程授权合入 9c28040f 的 JY 两轮探测。两处生产、五处 Host 的启动 Config 都先清零；新字段默认归一为一轮，GNSS deadline 不变。
- 7ee9cbc12aeb9dc6ab03d156d2bec781d356f128：在姿态使用及快照发布前校验真实存储的姿态/参考生命周期；附 Host 私有状态注入，未向目标固件引入测试 setter 或恢复机制。
- 03694fb：GUI 回归夹具的偏好文件改存应用工作区内；保持路径安全门禁。该提交不改变生成固件。

当前完整核心和后端源码见 CURRENT_REPLAY_IMPLEMENTATION.md；source_raw 保留原始字节。与 470383 的数学区别是重新执行所有已接受的后续观测，故历史修正自然经过各个后续观测的 (1-K) 衰减。重放依测量时间、相同时刻升序 group 排列（GNSS 位置 EN/U、速度 EN/U、气压计 U）。保存原始 dt/增量；先完整校验，再以单任务拥有的同一输入提交，数值失败不更新状态或接收元数据。观测仍对齐前一个已完成 IMU 边界，不声称分数时刻精确插值。

## 实际结果和资源

旧实现两个反例误差分别 +2.5 m、+0.125 m；修复后均 0，长期独立标量 oracle 也匹配。核心 3,745 检查/0 失败，包含容量 FULL/过期恢复、相同时刻顺序、跨组迟到、回绕、数值失败原子性。实际后端/INS/时间/队列/codec 正常 29,655 检查/0 失败。四个存储状态故障修复前均返回（exit 3），修复后均终止陷阱（3221225501）；完整命令和前后源码已保存。

上下文 sizeof 从 8,336 增为 18,592，即 +10,256 静态字节。当前 v7 ARM ELF 实际 s_context 0x48a0、位于主 SRAM；BIN 291,256 字节。主 SRAM section 占用 101,704/131,072，CCM 44,016/65,536。保守 200 Hz 预测、4*25 Hz GNSS、max(200 Hz IMU,200 Hz baro) 在闭 600 ms 窗口需 121 个节点/185 个事件，均低于 256；配置超限由所属后端静态门禁拒绝。外设违背声明速率时普通 FULL/STALE 仍可发生。这些不是 WCET、栈、导航精度或最省资源证明。

v7 四算法全新矩阵正在运行，已完成命令以 matrix_v7_checkpoint_results.json 为准。SF6/KF6 ARM、架构、原样生成 PoT、Host 均通过；SF6 Host 72 executables/4,394,684 checks/0 failures，KF6 72/4,396,683/0。KF6 的真实 GCC -fanalyzer 和资源门禁也通过。SF6 资源通过，但真实 GCC -fanalyzer 退出 2：Backend_GnssGroupApply 第 230 行 measurement.observation[axis] 报 CWE-121 / analyzer-out-of-bounds；这是当前明确失败，完整命令、诊断路径和失败日志已保留。该函数组号检查也位于 1U << group 之后，需要在下一切片把契约校验移到安全访问之前并明确两元素拷贝边界，不能抑制诊断。PureINS/ESKF15 后续仍在运行；不拼接为完整矩阵 PASS。旧 v6 的 23/24 与失败保持历史范围。

FCCG SF6/JY 11 tests 通过；首次 GUI 路径夹具失败完整保留。GSHC 62 tests +3 subtests 通过，中文/英文、浅/深四图和实际宽度完整保留；原三个监视卡及标签保留，只局部分行按钮，英文内容宽由 856 降为 viewport 638。FLP v3 含旧算法回归 43 tests 通过；最新 v5 原生记录和 v7 精确包通过正式 LogOpenCoordinator（1 targeted test）。v5 第一次默认 pytest 临时目录权限失败也保留，重跑仅使用先确认不存在的 .work 目录。没有 decoder 回退或覆盖不可变源记录。

## 尚未完成

实际 Baro descriptor/instance/source_epoch 和冻结高度参考 epoch 的接线等待独立任务授权提交。当前气压计来源显式 UNKNOWN，不能宣称已完成来源契约或冷备。SF6 GNSS 来源改变需任务重新初始化，不支持自动备份源。Delay10 的无执行器边界尚待明确；目前未冻结最终诊断候选。所有最终整合之后仍需要新的完整矩阵、最终候选配置/ELF/BIN/decoder/hash。

critical-contract 手工审查 NOT PROVEN，工具退出 0 不等于已完成接受；栈/WCET/硬件证据仍未证明。未执行串口、DAP/SWD、复位、烧录、解锁或其他硬件操作，未写 TEST_4、Frozen50cc、UART 候选，未 push/tag/Release/merge。

哈希对象分开保存：Git blob object ID、Git blob 内容 SHA256、归档原始文件 SHA256。旧 kernel 的 209 CRLF+38 LF 混合文件规范化后准确等于旧 Git 内容；保留原证据，不事后改写历史哈希。

快照已完成 18 个命令，其中 17 成功、1 失败；只代表保存时已实际执行的子集。
