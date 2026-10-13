# SWD 软件拒绝 / 清理保护证据

基线 `659ec97445a86af4e18a3f2e36cf4f8e50cc0572`。
[实现范围、技术阻塞及已收到的台架条件](../../../../../docs/public/GSHC/SWD_SOFTWARE_GUARDS_20261013.md)。

修复前 `pre_fix01`：**4 failed / 2 passed**。复现部分 attach 的 Busy/InvalidRequest
没有释放、读 Busy 没有使会话失效、stdin BrokenPipe 跳过其余清理。失败与原断言保留。
最终同一次 `regression05`：**81 passed，21.08 秒，退出码 0**，无测试警告。
范围：SWD guard/API/CLI/管道与异步 GUI；没有冒称本轮执行全套 141 tests。

修改包括失败后的事务清理、关闭返回值检查、同 Python 进程的 API 所有者协调、
init-complete 屏障、已知 claim 日志终止错误及错误标记/报文提交同步、有界自有子进程回收。
模拟双进程用例明确验证进程内协调不提供跨进程独占。没有取得 Horco 的物理独占句柄，
stderr 观察不能阻止外部 EXE 已执行的初始化指令，不能称为底层 claim fail-stop。
实际 gate 集合保持为空，未增加绕过参数。

已有 OpenOCD 的标记验证：首命令 noinit，全部端口 disabled，echo / shutdown，
**没有 adapter 配置或目标 init**；退出 0，标记出现在 stderr。仅证明本地输出约定。
所有调试子进程为本任务启动的 Python 模拟器，不是实物调试器。

任务进行中台架条件确认已收到，随后只做获准的元数据预检。
`2026-10-13T17:12:44Z`：指定 Horco `FAED:4870 / 132765403520`，PnP OK，
MI_00=WINUSB、MI_01=HidUsb；列出的常见调试器进程为空，未杀任何用户进程。
这个快照不覆盖任意客户端或设备句柄占用，不能证明探针未被占用。
**真实目标身份、running/halted、RAM 响应及探针释放均未验证**：没有打开 USB/HID/串口，
没有发送 SWD 指令。不是等待重复接线确认，而是后端技术阻塞仍未消除。

`evidence_final.zip` 保存完整命令、版本/源哈希、失败和通过日志、主机元数据预检、
标记解析日志、复现脚本及最终源快照。`manifest_final.json` 提供归档和条目 SHA256。
早先 `evidence.zip` / `manifest.json` 保留 80 项阶段快照，未改写或删除；最终结果还覆盖
关闭审查发现的 terminate 后 wait 错误分支，不把阶段通过拼接成最终执行。
任务目录 `.work/dev013_swd_guard01` 保留合成输入和完整清单，无清理授权。
原有用户文件、冻结 v0.1.2、现有 OpenOCD 安装均未改动；没有驱动/依赖安装、
外部源码大构建、固件构建、发布、推送或执行器动作。
