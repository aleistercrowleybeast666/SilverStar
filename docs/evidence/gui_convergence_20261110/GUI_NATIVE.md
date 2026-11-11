# 原生 GUI 验证范围

本轮使用 Windows 原生窗口和真实按钮/键盘操作；不是 offscreen 截图。基础桌面缩放为
125%，SCG 实测 Qt DPR=1.25；TreeDiagram 和 Underline 以 `QT_SCALE_FACTOR=1.2`
得到实测 DPR=1.5。此前设置 factor=1.25 的 TreeDiagram 操作实际 DPR=1.5625，
不计入 125% 或 150% 验收。

实际启动解释器查询：SilverStar与TreeDiagram使用PySide6/Qt **6.10.1**，Underline使用
**6.11.1**。SCG辅助启动脚本早期将Qt版本写死为6.11.1，该字段不是测量值，不采用；
实际DPR与窗口尺寸由Qt运行时查询，交互结果与保存文件核验不受该记录错误影响。

| 应用与身份 | 实际入口及结果 | 代表截图 |
| --- | --- | --- |
| SCG 中文浅色，980×700 Qt 逻辑尺寸；导入生命周期修复 a2d9ae9c，保存保护 02f36089 | 主导航共享实例→导入本轮 run 参数→真实 Preview/Cancel/Apply；默认未选控制研究。Apply 后模型与后端普通导入严格相等。取消关闭保留未保存标记；第二次关闭选择保存，实际规范输出 `native-scg/SilverStar.ssproject` 与后端参数逐值严格相等。原输入副本不覆盖。 | [参数预览](gui_native/scg-import-preview-125.png)、[未保存保护](gui_native/scg-unsaved-boundary-125.png) |
| TreeDiagram 0eb5140d，980×640，DPR=1.5 | 实际 Results→Export parameters→系统保存窗口，从选中历史 run 导出；结果 461.482 m、18 s，结束原因是配置时长到达。当前编辑器9.81未覆盖已完成run的9.78。导出字节与联调原包完全一致。 | [历史结果与导出范围](gui_native/treediagram-result-150.png) |
| Underline 英文深色，DPR=1.5，最大化；410测试批次便携包 | Open Project→Thrust；None→Linear Weight-Change草稿，旧225 N·s结果保持并标未应用。Export显示旧结果来源、区间2–4 s及返回重算入口；Return→顶部Apply and recalculate，一次完成处理与分析，旧草稿提示清除。关闭时Save/Discard/Cancel正确，本次丢弃测试修改。 | [便携版草稿导出](gui_native/underline-portable-draft-export-150.png) |
| Underline 最终 fit 便携包，英文深色，150%，未手动最大化 | 普通 EXE 首次启动，标题栏、工具栏、状态栏完整可见；真实 Open Project 载入本轮工程→Thrust，顶部 Update results 固定可见，225 N·s 结果与图可读，保持 Saved。正常关闭未改工程，stderr 为空；已退出 computer use。 | [首次启动](gui_native/underline-fit-first-show-150.png)、[结果区域](gui_native/underline-fit-result-150.png) |
| Underline 同一最终 fit EXE，中文浅色，125%，未手动最大化 | `--locale zh_CN --theme light`，OS125% 与 factor=1；普通首次启动的主导航、导入/保存/打开工具栏与状态栏完整可见，CU 采集1281×818。正常关闭并退出 computer use。 | [中文首次启动](gui_native/underline-fit-first-show-125.png) |

Underline 上述便携包 EXE SHA-256：
`c524f271a643dd29e4f561881a1b3fc58fec1c7678848fde5d9c4be713ffc9c8`。
原生测试发现默认1280×820在150%可用逻辑1280×680屏幕上溢出；这是实际缺陷，不能以最大化
后的截图冒充首次启动通过。修复04ac660e按availableGeometry和窗口边框收敛首次显示；
最终 fit 包实际原生首次显示已复验，未手动移动、缩放或最大化；CU 采集窗口范围为
1536×818，包含完整底部状态栏。该采集尺寸不冒充 Qt 逻辑尺寸；Qt 几何数值由对应的
生产窗口回归另行记录。最终 EXE SHA-256：
`87e4d65154db99cad5f07587a8c7bd6af35351d2cb83637ff99dae46474b3840`。
旧包截图只证明其计算/草稿/导出流程，不作为最终产物身份。

原生导出参数包 SHA-256：
`ab27c43327d51c0c26988c26c3a2d5699c10ce7872592276d24750c95f6580b8`。
源试验为明确标注的合成软件输入，不是实测发动机或硬件验收。

真实测试还暴露并修复 SCG QMessageBox 关闭后读取已销毁checkbox的异常；修复前日志保留，
不将该次Apply记为成功。后续正常Apply/保存复验无此异常。操作结束后关闭自有测试窗口，
退出computer use。Windows显示器接口诊断仍有系统warning，但没有隐藏Python异常或将其作GUI通过依据。

## 默认首次显示的补充修复（2026-11-11）

上面的 SCG 980×700 场景经过辅助脚本缩窗，只证明该尺寸下的操作；不能证明普通首次启动。
随后以私有设置、生产 MainWindow、原生 Windows Qt 6.10.1、不手动缩放/移动/最大化独立测量，
发现 SCG、FLP、GSHC 默认外框都越过屏幕可用区。系统自动限制到屏幕总尺寸仍未扣除任务栏。

| 应用 | 125% 修复前溢出（逻辑 px） | 150% 修复前溢出 | 修复后的首次外框（125% / 150%） |
| --- | --- | --- | --- |
| SCG | 底部58 | 右侧9、底部48 | 1460×816 / 1280×680 |
| FLP | 底部58 | 右侧9、底部48 | 1480×816 / 1280×680 |
| GSHC | 右侧10、底部58 | 右侧9、底部48 | 1536×816 / 1280×680 |

修复只在三个生产 `application.main` 的 `show()` 后，根据 `availableGeometry` 和实际边框
限制首屏尺寸/位置；对超出可用客户区的最低尺寸作相同限制。随后仅排队一次带窗口 receiver
的校正，窗口销毁会取消该回调。已有合法位置、最大化状态、后续主题/语言/页面操作不持续重排。
没有修改业务配置、运行计时器或用 offscreen 特例绕过适屏。

最终探针直接执行三个生产 `application.main`，观察其实际适屏调用；六个原生缩放场景全部
退出0、外框完整在可用区内，SCG/FLP 状态栏可达。每个场景另验证合法位置和最大化保留、
主题/语言/页面切换后外框不变且首屏适配次数不增加。三个快速关闭场景也退出0；FLP 实际
`WA_DeleteOnClose` 销毁后继续事件循环，排队校正被取消。九次 stderr 均为空。
GSHC 使用真实 Controller，但主机探针/端口库存注入为空且硬件打开边界拒绝调用；没有连接设备。

相关回归分别为 SCG **4 passed / 21.42 s**、FLP 两完整文件 **11 passed / 39.90 s**、
GSHC 两完整文件 **8 passed / 39.73 s**，各自为独立批次。FLP 先前完整套件属于其修复前封印身份，
不把这些小批次拼成新全套；本节是源码原生 Qt 脚本验证，便携 EXE 验证另行记录。

命令、精确源码散列、前后几何和日志见[首屏修复收据](gui_native/initial_frame/receipt.json)、
[实际生产入口结果](gui_native/initial_frame/after.json)、
[可复用启动探针](../../../tools/validation/gui_initial_frame_probe.py)。
最初 FLP 探针误用了原生 QSettings，写入 `zh_CN/light` 偏好；原值未知，未猜测恢复。
该次已从私有设置验收中排除并用显式 INI 重测，全程未打开用户工程。
