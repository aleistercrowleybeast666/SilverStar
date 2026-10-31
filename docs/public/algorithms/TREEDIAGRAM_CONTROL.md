# TreeDiagram 数学 SDK 与控制研究接口

此接口保留原有 `silverstar.function-parameters/1` 严格标量格式和 128/96 项容量。
新文件 `*.sstuning.json` 使用独立的 `silverstar.tuning-bundle/1`，
其 schema 位于 `contracts/tuning_bundle_v1.schema.json`，语义校验位于
`apps/SCG/src/silverstar_fccg/project/tuning_bundle.py`。

SCG GUI 的参数导入沿用 Preview/Apply 事务：验证全部 profile 身份、单位、表示及共享参数一致性，
取消无写入，Apply 返回完整新草稿。匹配的 INS/KF6 输入按实际 owner 应用；
独立 PID/LQR 研究记录不会冒充已选的机载控制算法。

控制研究记录固定包含 PID 的七个标量，或 2 状态/1 输入 LQR 的 A/B/Q/R/K、dt、状态顺序、
输入顺序、存储顺序、工作点说明、Riccati 残差和 float32 K 的闭环半径。
Q 可半正定，R 必须正定；导出端执行 DARE/PBH/目标精度检查。
SCG 再验证形状、有限值、权重定义和实际 `A-BK` 谱半径，不能仅信任文件中的“稳定”标签。
`deployable` 必须为 false；没有目标执行器驱动、mission dispatcher 或飞行验证。

## 正常构建接口

两项真实 C 数学核心归属声明式插件：

- `silverstar.algorithm.control.pid`：测量微分、低通、积分/输出限幅、条件积分 anti-windup，
  Start/Stop 生命周期、严格采样周期、无动态分配。参数或内部数值失效不产生有效命令。
- `silverstar.algorithm.control.lqr`：固定两状态一输入 `u=-Kx` 与输出限幅；
  离线 Riccati 求解器不进入目标。

`TuningBundle_ControlCoreAttach` 是显式构建入口：把研究参数映射到对应插件的唯一参数 owner，
通过现有 `base_components` 和标准生成器构建，不增加运行时注册表、函数指针或任意脚本。
`ControlPid_ProjectConfigGet` / `ControlLqr_ProjectConfigGet` 从真正生成的
`project_algorithm_parameters.h` 读取实际 float32 值。
消费者返回明确 Result，完整验证后才发布配置。

这些函数是可调用且经过验证的构建接口，尚未接入飞控任务或电气驱动。
默认固件不会调用它们，链接器可能回收未引用的核心；不能把“完整固件编译链接成功”
写成“飞控已经运行闭环控制”。有意调用该接口的宿主验证会实际执行数学核并核验输出。

```powershell
# SilverStar 根目录，或先安装 apps/SCG 开发包
$env:PYTHONPATH = "apps/SCG/src"
python -m silverstar_fccg.project.tuning_bundle preview project.ssproject run.sstuning.json
python -m silverstar_fccg.project.tuning_bundle preview project.ssproject run.sstuning.json --include-control-core
python -m silverstar_fccg.project.tuning_bundle apply project.ssproject run.sstuning.json --output tuned.ssproject --include-control-core
```

不加 `--include-control-core` 时只应用原有已选 scalar owner。
该显式选项会额外显示将编译的控制核心及参数，仍不赋予任何硬件许可。
之后 `tuned.ssproject` 走普通 SCG 打开/检查/生成。

## 可重现验证

`apps/SCG/tools/validation/treediagram_control_validate.py --revision vN` 使用新的、唯一版本目录，
从固定 PID/LQR bundle 分别正常生成 F407 工程，并验证：

1. 真正生成的配置访问器与 C 内核一起以 GCC `-fanalyzer -Wall -Wextra -Werror` 编译并执行；
   PID kp 从默认 2 改成 3.25，实际输出与新值一致；LQR 用最终 float32 K。
2. 运行正常生成工程的 `all`、`architecture-check`、`power10-check`、`static-analysis`、
   `artifact-check` 和 `stack-report`，保留每项退出码、完整日志与生成物哈希清单。
3. `tests/test_tuning_bundle.py` 覆盖源身份、未知字段、重复键、坏摘要、布尔伪数值、
   多 owner 共享值冲突、失败无部分应用以及伪造 LQR 稳定性摘要。

输出归 `algorithm_sdk` 所有，验证目录为 `.work/0.1.3-treediagram-20261101/control-core-vN`；
正式命令和日志在 `docs/evidence/treediagram_algorithms_20261101/vN`。
每个 revision 只创建一次，不覆写历史验证输出，不清理用户工程。
文本门禁 PASS 仍保留 critical-contract NOT PROVEN；完整栈或硬件证据不可由数学测试替代。

## SDK 交付

```powershell
python apps/SCG/tools/export_algorithm_sdk.py <TreeDiagram>/src/treediagram/algorithms/sdk
```

导出是固定源文件清单，不复制整个仓库/MCU SDK。逐文件保留 SHA-256、原路径与 Apache-2.0 LICENSE。
当来源为脏工作区时，manifest 明确要求内容摘要，不以 HEAD 单独证明源身份。
TreeDiagram 的 host adapter 与原数学 C 源分开；宿主断言保持终止语义，不是 HAL 模拟或 MCU 恢复。
