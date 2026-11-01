# SCG 硬件概览、事务编辑与生成准入

本次从 SilverStar `8b028f280ba01dce0efc697479ef99ec143f7456` 继续。普通 `MainWindow` 构造器使用实际 `ProjectDraft_Create`；初始复现没有替换成 ReferenceProject。原有 AGENTS、历史证据与根目录 work 清单没有被删除或夹带。

## 修复与交互

- 初始飞控/地面均为未导入的 custom 草稿。原飞控按钮只判断 mode，地面使用实际校验，造成一个亮、一个灭；现在两端通过只读 `TargetReadiness_Get` 聚合既有 Project/Ground/无线事务校验与导入快照存在性。它表示可请求生成，不是已生成、运行 READY 或硬件验证。
- 未配置双方均不可生成；合法单端允许；已经配置的无线对端冲突仍保留为阻断。请求入口在选择输出目录、保存工程前再次检查。解除忙碌与工具检测结束后，也重新显示同一准入结果。
- 原协议框定位使用 root layout 对嵌套 label 的 `indexOf`，返回 -1 后插入第一行。现在首页固定为硬件概览、共享通信摘要、设备与资源概览。协议归共享无线事务，主页不展示 provenance/hash。
- 硬件按钮按目标打开一个有“硬件与平台 / 设备与接口 / 资源与接线”页签的选项窗。主页保留当前选择和阻断事实；没有多层硬件配置弹窗。文件选择器仅选择来源路径。
- 私有 `HardwareDraftController` 是小型 QObject，持有深拷贝模型；不创建第二个 MainWindow，不接入设置、保存、构建、插件安装的写入入口。27 个既有编辑动作提取到 `HardwareEditingActions`，与基线 AST 逐项相同，见 [提取审计](shared-actions-extraction.json)。
- CubeMX 选择在弹窗中只记录待导入路径，并显示原有自定义硬件风险提示。按应用后才经主窗口后台工作执行导入；读取用户源，创建既有受控快照。导入失败不发布候选模型。取消/Esc/关闭不导入、不更新 live 模型或工程设置。弹窗打开或后台导入期间工程变化会拒绝过期候选。
- 私有窗的未选目标功率编辑器在首次刷新前获得明确父控件，防止取消后遗留无父窗口、使进程不能退出。
- 原“保存硬件”和旧工程迁移入口保持在主页，依原有模型/迁移条件显示与启用；没有藏进未显示的旧编辑器。平台选项保留检测事实，普通表单不展示来源 hash。资源摘要来自实际 requirement views，区分已映射数和待映射必需项。
- 原 TreeDiagram 参数预览新增默认不选中的“10 ms 控制研究任务”选项，调用拥有者的 `TuningBundle_ControlTaskAttach`。任务只在明确勾选并应用时加入；20 ms 旧束仍可作普通参数导入，但不能启用该任务。任务输出为有界内存研究结果，没有硬件执行器驱动或可部署资格声明。
- 参数预览期间若 live 工程变化，拒绝过期候选；不会用预览前的完整参数值覆盖期间的新编辑。

交互参考官方 [OpenRocket 基础设计界面](https://openrocket.readthedocs.io/en/latest/user_guide/basic_rocket_design.html) 的对象概览与配置窗，以及 [Keil 对象选项对话框](https://www.keil.com/support/man/docs/uv4cl/uv4cl_ca_ovwconfigdialogs.htm) 的目标相关选项。没有复制这些产品的实现。

## 使用方法

在 `D:\python_software\SilverStar` 运行：

```powershell
.venv\Scripts\python.exe apps\SCG\main.py --lang zh_CN --theme light
```

首页点相应目标的“硬件选项…”选择已有 PCB，或选择完整 CubeMX 工程并应用。设备、接口、资源都在同一对象窗口的页签内。数值编辑器维持既有 Enter 确认语义；Cancel/Esc 放弃整个窗口草稿。完成所需配置后，到第三页请求对应目标生成。工具链存在不会自动解除配置阻断。

TreeDiagram 束继续由任务流程中的算法参数导入入口读取 `.sstuning.json`。预览中普通参数与研究任务选项分开；取消不写入。没有勾选研究任务时，不会自动增加控制任务。

## 证据与边界

- [普通启动复现](before-ordinary.json)：初始 Flight enabled=true、Ground=false；协议 root index=0、嵌套 summary root index=-1。两张初始离屏图缺字体，不能用作最终视觉验收。
- `pytest-v1.log`：6 通过、3 失败；三个失败来自新测试误写不存在的 PCB ID，已改为真实 ReferenceProject 的板卡身份。
- `pytest-v2.log`：32 通过，160.95 s；硬件/主页/无线/单端作用域中间回归。
- `pytest-v3.log`：12 通过，82.53 s；主窗口应用、取消、导入失败中间回归。
- `pytest-v4.log`：17 通过，135.44 s；含研究任务默认不选、明确启用、取消及 20 ms 拒绝。之后原生测试又发现下面两项，所以这不代表最终完整验收。
- `verification-v5` 在原生工具检测覆盖状态原因问题发现后主动中断；`verification-v6` 在孤儿窗问题确认后主动中断。各自保留日志、源身份和 `interrupted.json`，均不称完整通过。
- [原生孤儿窗](native-orphan-windows-before.json) 与 [Qt 独立复现](qt-orphan-before.json) 记录真实修复前失败。只在保存进程命令行、核实 PID 5272 属于本任务 `launch_native_review.py` 后终止该遗留进程；未处理其他用户进程。父 launcher 随后退出；首次原生运行没有最终模型相等凭据。
- [修复后真实事件循环](lifecycle-after.json)：两端各取消与应用后，未出现额外窗口，关闭 MainWindow 触发 lastWindowClosed/aboutToQuit，进程 exit 0，无超时。
- `verification-v7`：54 passed / 414.11 s；源码 epoch 稳定。随后 `control-boundary-before.log` 实际复现预览期间 telemetry 改动被旧候选覆盖；修复后 `verification-v8` 为 55 passed / 438.01 s，源码 epoch 稳定。这些是各自中间版本的完整选组，不拼接。
- `overview-actions-before.log`：两个新增真实 GUI 边界均失败，原迁移入口与硬件导出入口不可见；修复后 `overview-actions-after.log` 两项通过。`message-localization.log` 的原有弹窗中文按钮回归通过。
- GUI 功能冻结版 `verification-v9`：**59 passed / 591.31 s**，runner exit 0，源码前后 hash 无变化（`source_changed=[]`）。包含旧工程迁移的完整选组、命令和稳定源身份见该目录 `result.json`、`identity.json`、`source-before.json` 与 `pytest.log`。它不运行 ARM 构建或证明硬件状态。
- 最后控制单位、provenance 和封存栈 owner 提交 `e7c42b7c4971fddb02c6d5c60864b50dffaa3f1a` 后，完整复跑同一 11 文件选择：`verification-v10` **59 passed / 910.54 s**，exit 0，源码前后 hash 完全一致。该版本随后只有独立 Host ABI fixture 与 USB owning 路径维护，GUI 编辑/准入源码没有改变；各自新验证单独记账。
- `v4-125`（中文/浅色）与 `v4-150`（英文/深色）为当前 Qt offscreen 截图：普通三页、两端三个选项页、地面私有变化、共享无线和窄窗口，各 12 个场景通过。`capture.json` 包含比例、尺寸、按钮可见性、模型不变断言、源 hash。已经目视检查普通首页和窄窗口；旧 v1/v2/v3 捕获保留其原始含义。
- `control-preview-v3` 是当前实际参数预览弹窗，明确使用命名 ReferenceProject 与真实 fixture，不冒充初始空工程。默认未选、选中显示和取消后模型不变均核对。
- [最终原生观察](native-final-observation.json)：普通构造器、真实工具检测结束且空闲后，两个生成按钮均禁用且配置阻断标签保留；Ground 实际下拉选择 SSGS0.5 后 Esc，主窗 Alt+F4 正常退出。`aboutToQuit` 写出的最终模型与初始模型字节完全相同，SHA-256 都为 `dc5dea0755012d8597fd384a190eff489824bc090cf85e653836f73dab0d6b16`。未强制终止此最终进程；Computer Use 随即 reset 退出。该次手动范围不包含 Apply、Flight 与全部异步边界，后者由独立自动测试记录。

原报告 §14 USB 软件/硬件未完成项的只读追溯见 [USB_READONLY_AUDIT.md](USB_READONLY_AUDIT.md)。b66 无通过结果与中止原因未知分别记录，没有重新执行被中止动作。

临时设置、pytest 输出和生命周期输出都在 `.work/0.1.3-software-completion-20261101/gui`，用途与归属见其 `INVENTORY.md`。没有执行硬件、串口控制、烧录或旧工作目录清理。
