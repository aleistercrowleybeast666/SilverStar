# 本次任务输出归属

基线与保留项见 `BASELINE.json`。所有目录均属于 2026-11-01 软件收尾；下面列的是
生成、测试与分析空间，不授予删除权限。本次未执行旧 `.work` 清理，未删除用户输入、
日志、解码包、源码 fixture、档案或历史证据。

| 位置 | owner / 用途 | 保留证据 |
|---|---|---|
| SilverStar `.work/0.1.3-software-completion-20261101/critical` | root：mission 状态/错误传播与 GPIO 容量的真实 C 前后回归 | 本目录 `critical/`，编译命令、失败日志、源对象与 hash |
| 同级 `control` | controller owner：调度、历史来源、原子发布、参数单位；fresh full-host-c 两套完整 Host | `control/`，v7b 与完整 Host 结果、C/B生产闭包相等收据 |
| 同级 `gui` | GUI owner / root 原生复核：普通主页、配置事务、生成准入 | `gui/`，最终 v10、缩放截图与 native-final |
| 同级 `stack` | stack owner：隔离正常生成、A/B 独立 ARM 构建、严格软件栈审查 | `stack/`，各版本完整失败/通过、closure 与工具身份 |
| 同级 `usb` | root：独立通用 CDC kit 的原始输入只读导出、Host / ARM / analyzer | `usb/`；与普通 Ground 私有候选不是同一源图 |
| `.work/sc-261101-usb` | controller owner：精确 F103/F407 普通私有 Ground 候选 | `usb-exact/`；为现有 Windows 路径上限缩短名称，没有放宽路径校验 |
| `.work/sc-261101-usb/d2` | stack/USB 验证 owner：描述符修复后三板再次正常生成与 ARM/analyzer | `usb-exact/descriptor-v2/`，实际归档与哈希 |
| 同级 `usb/owners-v2` | USB owner：heap/FIFO/descriptor与严格元数据准入 | `usb/owners-v2/`，148项整组与后续27/8项、4 ARM、仍失败门禁 |
| 同级 `delivery` | root：实际参数 Preview/Apply、生成工程、C 消费者 | `delivery/`，原命令、实际模型、decoder、compiled inputs、hash |
| TreeDiagram `.qa/software-completion-20261101` | root：15 示例与 3 个新的 10 ms CLI 运行 | TreeDiagram `docs/evidence/software_completion_20261101`；设计/摘要/参数与运行 hash |
| TreeDiagram `.test-tmp/software-completion-20261101` | root：pytest 与实际 C SDK 的独立缓存 | 同上测试日志与源码 identity；缓存不是科学记录 |
| Underline `.work/0.1.0-software-completion-20261101` | GUI owner：普通完整 suite、Qt 生命周期负例和原生 heap 诊断 | Underline `docs/evidence/software_completion_20261101`；详细 owner 与源码 diff 各自记录 |

外部 CubeMX 输入 `D:/Codex_Work/2026-10-08/task/usb-validation` 只读使用。
工具链、SDK、虚拟环境不复制进任务目录。精确输入 bytes / hashes 由各组 receipt
分别记录；重放必须选新输出路径，不覆盖已有证据或用户候选工程。

Git 提交排除 `AGENTS.md`、原 astra/cleanup 证据及根目录三个既有 work 清单，也排除
Underline 的原 `docs/Repository_Showcase_Review_20261016.md`。保留项仍在原工作区。
