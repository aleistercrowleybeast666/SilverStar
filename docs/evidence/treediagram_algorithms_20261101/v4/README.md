# 最终运行参数回导 v4（2026-11-01）

本次执行退出码 **0**：underline-pid 49、PID 49、LQR 45，共 **143/143** 个标量一致。
输入来自 TreeDiagram `final-examples-v2`，对应执行机构边界修复后的代码提交
`440db630ac12c5e3ad128623870ef00771c49e25`。旧 v1/v2/v3 证据没有覆盖或重写。

本次接收端固定为 SilverStar **`09c057a67acfc10e3ff387a4a8821c8ee0e83b0c`**，
包含旧工程迁移与最终 H743/生成门槛修复。SDK 来源仍独立固定为
`4f701b4a7822302dc0f4ac858549f7cc7fa4ba0e`；不能把 SDK commit 当成接收端 commit。
运行前后 `apps/SCG` 和 `contracts` 相对接收端提交的差异检查均为干净，model/tuning/generator/
service 五个关键文件的运行字节保持不变。Git 与运行文件的 CRLF/LF 差异单独记录，并验证
仅换行正规化后完全相同；没有省略或改写接收端代码。

[接收端冻结结果](matched-runtime/receiver-freeze-check.json)与
[精确接收端文件摘要](matched-runtime/provenance.json)已保留。接收端负责人独立确认 cap6
同提交回归 38 passed / 261.53s；该组不是本脚本执行，也不与 v4 的 143 项标量检查拼接计数。

实际命令（SilverStar 仓库 cwd）：

```powershell
D:/python_software/TreeDiagram/.venv/Scripts/python.exe -u docs/evidence/treediagram_algorithms_20261101/v4/validate_actual_runs.py
```

脚本的 EVIDENCE/WORK 使用 `exist_ok=False`：再次复现必须选择新的版本目录，不能覆盖正式证据。
运行前要求 TreeDiagram 的 `examples-actuator-final.exit.txt=0` 及完整 matrix 存在。

每个参数包的 run_id、model_id 都与 `.qa/20261101/final-runs-v2/` 下实际保存的 tdrun
核对；同时从运行内 design 快照重新计算 input_digest。正式摘要保留运行文件原始 SHA-256、
行数、终止摘要，不只依赖参数包自行声明的 ID。

实际链路为：读取参数包 → 事务预览/采用 → 保存并重开 SCG 工程 → 新目录生成 →
校验精确 ssdecoder 与 project_semantics → Host 编译并执行新生成的 C 消费者。
143 个标量对比覆盖包、目标解析值、decoder 值及编译后 C 宏值；PID/LQR 还实际执行
ProjectConfigGet/Start/Step，将配置结构与输出逐项对照相同 SDK。
原始工程未被改变。C 使用 GCC 16.1.0、`-std=c11 -Wall -Wextra -Werror -O2 -fanalyzer`；
三个编译和三个执行均为 0。SDK 实现身份未改变。

| 场景 | 标量 | run ID | 模型摘要 | 实际生成 C 输出 |
|---|---:|---|---|---:|
| underline-pid | 49 | `ea1ae4e4-f827-4347-9cfd-c4af1463f058` | `7aa0b00e983ff8e5f981a8f43ec01bb8946e9c0af4dc744cf7de76a8983075f3` | 0.015029999427497387 |
| pid | 49 | `27e46815-7944-4c74-9372-482ad09820ff` | `05c8f05c12696efd5cfc695fc386e663157b6f972400363ee246b5979150a553` | 0.015029999427497387 |
| lqr | 45 | `77b67819-afb8-4c88-80fd-0389d73e052c` | `d9dd9c9dd120edc94100f5610a1b29fcb43b489be23dedf6f7e9908285f797e6` | -0.049142077565193176 |

证据入口：

- [运行原始输出](run.log)、[退出码](exit.txt)、[命令及各次退出码](matched-runtime/commands.json)。
- [逐场景结果](matched-runtime/outcomes.json)、[实际运行身份与文件摘要](matched-runtime/inputs/run-identities.json)。
- `matched-runtime/*-values.json` 保存全部标量输入/目标/decoder/compiled-C 对照。
- `matched-runtime/*-consumer-compile.log` 与 `*-consumer-execute.log` 保留完整编译、执行输出。
- [来源与代码摘要](matched-runtime/provenance.json)、[固定 SDK 清单](matched-runtime/final-sdk-manifest.json)。
- [生成文件 inventory](matched-runtime/inventory.json)：仅本次 `.work/0.1.3-treediagram-20261101/control-core-v4`，
  owner 为 actual_run_parameter_adoption_v4；保存用途、大小与 SHA-256，没有清理旧任务输出。

范围是 **Host 参数采用、代码生成、静态分析编译和实际 C 消费检查**。本次没有重跑 ARM、
没有检查新参数的 MCU 阶段调度，也没有硬件操作；`deployment_ready=false` 保留原义。
v1 的 ARM 结果保留其原始构型与参数范围，不能当作 v4 参数已在 ARM/硬件运行的证据。
Underline 示例的 18 秒结果尚未落地，既有气动适用域与硬件未验证诊断没有抹去。

离开原工作区重新复现时，先在 TreeDiagram 用 `tools/verify_examples.py <新结果目录> --runs <新运行目录>`
生成新的配对 matrix、bundle 和 tdrun，再为验证脚本指定新的 SOURCE/RUNS/EVIDENCE/WORK。
新的 run ID 正常不同，应核对新配对数据，不能覆盖已提交 v1/v2/v3/v4 证据或把新 UUID 说成旧运行。
