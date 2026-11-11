# 原生 OpenGL 显示诊断：根因尚未证明

本批对应 SilverStar `45ba8701af5f4baf83692fb15b5fbac2d9dfcc21`，未改产品源码、
渲染默认值、依赖版本或系统图形设置。最终便携包的交互验收由主负责人另行记录。
诊断正常退出不等于 GUI 通过，`QWidget.grab()` 正常也不等于原生画面通过。

## 观察与被推翻的假设

11月11日默认 FLP 原生窗口采集为白色；只禁用首屏适配的一次对照正常。
11月12日重新运行该 no-fit 对照也白屏，因此**单次正常结果不能证明适配函数是根因**。
没有据此提交猜测性的启动修复。

| 对照 | 本批实际结果 |
| --- | --- |
| 只保留 QTimer(0) 的延后适配 | 原生采集仍白；外框在可用区内 |
| show 前适配 | 原生采集仍白；外框在可用区内 |
| 禁用 caption 的早期 winId，再于 show 前适配 | 原生采集仍白，并多出未扣除的原生边框，不构成首屏通过 |
| 分别只执行 resize / minimum / move | 原生采集均白 |
| 再次完全禁用适配 | 原生采集仍白，未复现前一天单次正例 |
| 诊断性不创建 GL 控件 | 原生采集正常；仅用于隔离，不能作为产品方案 |
| AA_ShareOpenGLContexts | 原生采集仍白 |
| QT_OPENGL=software | 首页正常；真实 replay_3d_widget 的 PyOpenGL 绘制报错，probe exit 90 |

默认 FLP 真实 3D 页两只 context 均有效，报告 Intel UHD Graphics、OpenGL 4.6、
驱动 `31.0.101.1999`。这只能证明所见 context 状态，不能唯一归因于驱动。
software 场景的原始 stderr 有 `glClearColor` 和 `glGetString` 的
`GL_INVALID_OPERATION (1282)`。安装的 PyOpenGL Win32 平台加载 `opengl32`，
Qt 的 software 选择另有自己的实现；本批未证明两者可共同支持现有 3D。
**禁止把 software 环境变量推荐为本产品修复或默认配置。**

## 不加载产品代码的对照

最小脚本仅创建 Qt 的 QMainWindow、QLabel、QOpenGLWidget，使用 Qt 自身
QOpenGLFunctions_2_0 清为蓝色，不导入 FLP、pyqtgraph 或 PyOpenGL。
Qt 6.10.1 下 context 4.6 有效、paint 执行三次，但 HWND 原生采集约99.995%白；
同一脚本的普通 QWidget raster 对照正常。
显式 alpha=8、SingleBuffer、swapInterval=0 均未恢复该 GL 原生采集。

进一步在**自己的前台窗口客户区完全位于单屏内**时，仅捕获该客户区对应的
`QScreen.grabWindow(0, screen-local rectangle)`，而非整个桌面；该采集发生于
`QWidget.grab()` 之前，也约99.995%白。随后 QWidget.grab 得到预期蓝色。
使用 Underline 已有解释器的 Qt 6.11.1、`-B`、相同最小脚本得到同样结果，
没有安装或替换任何依赖。

Qt 文档说明 QOpenGLWidget 会使整个顶层窗口通过 OpenGL 合成；
QScreen 文档也对 Windows 原生抓取的限制给出说明。
本批保留两种原生采集和 CPU 绘制回读的差异，**没有证明采集链路、Qt、驱动或
桌面合成器中的唯一根因，也不把这些结果称为最终原生 GUI 通过**。
参考：[QOpenGLWidget](https://doc.qt.io/qt-6/qopenglwidget.html)、
[QScreen::grabWindow](https://doc.qt.io/qt-6/qscreen.html#grabWindow)、
[Qt Windows graphics](https://doc.qt.io/qt-6/windows-graphics.html)。

## 可审计范围

`receipt.json` 索引19个对照的原始收据、stdout/stderr、代表图和 SHA-256。
全部来自自有窗口、私有设置、空的合成工程；未打开用户工程或设备。
原图读取回验不改写像素，白屏图也保留。脚本为本轮最终诊断版本；早期运行早于部分
新增的诊断开关，不冒称全部运行使用同一脚本字节。各 FLP 收据单独记录生产源码哈希。

正式目录只收录11张代表 PNG，不是完整截图全集。原始 case 收据中的66个 `file`
字段引用所对应的图像仍完整保留在 `.work/gui-convergence-20261110/flp/` 的各 case
目录中；已收录代表图的原始 `source` 与正式 `stored` 文件名对应关系见
`receipt.json` 的 `files`，不能直接把原始相对文件名当成正式目录中的同名文件。
生产源码 SHA-256 记录的是实际 Windows 运行工作树字节（CRLF），不是提交中
经过行尾规范化的 Git LF blob 哈希；两者语义不同，不将行尾差异误判为产品内容修改。

污染的初次 native 采集、非自有前台采集均排除；旧 default 的一次 visit-gl 实际
选中2D attitude，不算3D验证。暂停前未触发的 deferred probe 明确未测试。
这些限制均列在机器可读收据中，原始任务证据未删除。

后续须在可正常观察原生画面的环境中完成最终 EXE 的首屏、真实日志、3D与关闭验收；
不能用调低门禁、禁用3D、软件 OpenGL 的单页截图或修改既有失败结果代替。
