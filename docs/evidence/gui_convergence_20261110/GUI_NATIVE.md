# 原生 GUI 验证范围

本轮使用 Windows 原生窗口和真实按钮/键盘操作；不是 offscreen 截图。基础桌面缩放为
125%，SCG 实测 Qt DPR=1.25；TreeDiagram 和 Underline 以 `QT_SCALE_FACTOR=1.2`
得到实测 DPR=1.5。此前设置 factor=1.25 的 TreeDiagram 操作实际 DPR=1.5625，
不计入 125% 或 150% 验收。

| 应用与身份 | 实际入口及结果 | 代表截图 |
| --- | --- | --- |
| SCG 中文浅色，980×700 Qt 逻辑尺寸；导入生命周期修复 a2d9ae9c，保存保护 02f36089 | 主导航共享实例→导入本轮 run 参数→真实 Preview/Cancel/Apply；默认未选控制研究。Apply 后模型与后端普通导入严格相等。取消关闭保留未保存标记；第二次关闭选择保存，实际规范输出 `native-scg/SilverStar.ssproject` 与后端参数逐值严格相等。原输入副本不覆盖。 | [参数预览](gui_native/scg-import-preview-125.png)、[未保存保护](gui_native/scg-unsaved-boundary-125.png) |
| TreeDiagram 0eb5140d，980×640，DPR=1.5 | 实际 Results→Export parameters→系统保存窗口，从选中历史 run 导出；结果 461.482 m、18 s，结束原因是配置时长到达。当前编辑器9.81未覆盖已完成run的9.78。导出字节与联调原包完全一致。 | [历史结果与导出范围](gui_native/treediagram-result-150.png) |
| Underline 英文深色，DPR=1.5，最大化；410测试批次便携包 | Open Project→Thrust；None→Linear Weight-Change草稿，旧225 N·s结果保持并标未应用。Export显示旧结果来源、区间2–4 s及返回重算入口；Return→顶部Apply and recalculate，一次完成处理与分析，旧草稿提示清除。关闭时Save/Discard/Cancel正确，本次丢弃测试修改。 | [便携版草稿导出](gui_native/underline-portable-draft-export-150.png) |

Underline 上述便携包 EXE SHA-256：
`c524f271a643dd29e4f561881a1b3fc58fec1c7678848fde5d9c4be713ffc9c8`。
原生测试发现默认1280×820在150%可用逻辑1280×680屏幕上溢出；这是实际缺陷，不能以最大化
后的截图冒充首次启动通过。修复04ac660e按availableGeometry和窗口边框收敛首次显示；
新包及其原生首次显示复验另记最终交付报告。本截图只证明其计算/草稿/导出流程。

原生导出参数包 SHA-256：
`ab27c43327d51c0c26988c26c3a2d5699c10ce7872592276d24750c95f6580b8`。
源试验为明确标注的合成软件输入，不是实测发动机或硬件验收。

真实测试还暴露并修复 SCG QMessageBox 关闭后读取已销毁checkbox的异常；修复前日志保留，
不将该次Apply记为成功。后续正常Apply/保存复验无此异常。操作结束后关闭自有测试窗口，
退出computer use。Windows显示器接口诊断仍有系统warning，但没有隐藏Python异常或将其作GUI通过依据。
