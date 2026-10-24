# GUI Style Guide

> SilverStar Python/PySide6 工具的精简规范。完整设计原则以仓库 `AGENTS.md` 和实现测试为准。

## 1. 目标
- 工程信息清晰优先于装饰。
- 简体中文 / English 全量运行时切换；内部 ID 永远稳定且语言无关。
- Light/Dark 必须同时覆盖 Qt、2D Plot、OpenGL/3D、Matplotlib/GIF 导出。
- GUI 不包含协议二进制解析、导航数学或控制算法。
- 长任务后台执行，UI 线程只渲染状态。

## 2. 主窗口
推荐：菜单栏 → 深蓝品牌栏 → 左侧导航/主工作区 → 底部状态/进度。产品名和版本稳定显示，打开文件不改变 OS 窗口标题。

## 3. 交互
- 危险操作需要明确确认；普通信息使用非模态状态。
- ComboBox、CheckBox、Table、Dialog 的浅/深色都必须可读。
- 页面重建时阻塞信号，避免在控件自身 signal stack 中销毁父控件。
- 进度必须反映真实已完成工作；失败/取消不能强行显示 100%。

## 4. 数据与绘图
- 实时显示使用有界缓冲；持久化与 GUI 显示生命周期分离。
- 一次数据更新尽量只触发一次绘制 revision。
- 3D 世界坐标、机体坐标、相机和标签含义稳定；主题切换不重建数据模型。

## 5. i18n
- 所有用户可见字符串使用 translation key。
- IMU/GNSS/INS/KF/ENU/CRC/WXYZ 等技术缩写可保留。
- JSON、协议字段、项目 schema、日志 enum 使用规范英文 ID，不随 UI 语言变化。

## 6. 测试
至少覆盖：浅/深主题、中文/英文、窗口尺寸、对话框、长任务进度、取消、异常恢复、图表与 3D smoke test，以及 signal/rebuild 回归。

## Algorithm Parameters page

The seven-page order is Flight Devices → Flight Configuration → Navigation Configuration → Telemetry Configuration → Flight Hardware → Ground Station Hardware → Build & Validation. Algorithm parameter widgets are generated from strict plugin declarations; use actual values/units, localized descriptions, basic/advanced CollapsibleSection and per-algorithm reset.


## 任务阶段胶囊

胶囊表示有序任务阶段，可选择插入位置并调整顺序；编号表达顺序，稳定 ID 不依赖位置或显示名。名称、数值条件阈值可内联编辑，详情弹窗编辑条件、持续确认和动作引用。应用提交、取消不改工程；未编辑数值不因显示精度被重写。模板提供 START/实际起飞分开或显式合并的选择，不把 START 隐式解释为物理起飞。

设备实体、输出能力和通道归设备/硬件配置；阶段引用稳定设备 ID。当前自定义阶段为桌面参考，不能用动画、参考 trace 或配置声明冒充真实板端过程。阶段规则与连续估计/采样/记录分开；页面重建在当前信号返回后执行。

安装位置输入不再要求自然语言原点说明；固定导航点和轴定义通过明确的合同及图例表达。无下标 xyz（兼容旧 XYZ）均表示箭体系，设备原生轴使用 s_i 下标，导航系标 E/N/U。位置标题 r_i^b 的设备下标标识测点，三个输入分量仍为箭体系 x/y/z。轴标签与输入成组排布，三视图用同一米制比例；未知位置不按零位置绘制。原始 IMU 的两个安装轴必须互相垂直并构成右手旋转；旧映射和旧记录不因新界面自动改写。

## Touch scrolling

Ordinary scrolling content opts into the repository-local `TouchScroll_Enable` helper.
It registers Qt `QScroller.TouchGesture` on the viewport of a page, item view, or text
view. It does not convert touch into mouse drags, change wheel handlers, or change existing
ScrollPerPixel settings. Table headers are excluded; combo popups opt in separately.
Buttons, spinboxes, sliders, 2D plots and OpenGL views are not scrolling targets. Keep
plots, 3D views and time sliders outside page-scroll ancestors so their own drag semantics
remain authoritative. New ordinary scroll areas should opt in at construction.

Before field use, check finger swipes and taps on a CF-33: page scroll, nested table/list
scroll and selection, popup selection, button taps, spinboxes, mouse wheel/scrollbars,
stylus, plot pan/zoom, camera lock/rotation and replay time slider. Automated synthetic
Qt touch tests do not certify the physical Windows touch driver.

## Default Project Root

File → Default Project Root stores an existing selected directory in repository-local
`.fccg/path_preferences.json` (schema_version 1), separate from project state and UI INI settings.
New Project derives `<root>/<name>` until the first user edit or Browse selection freezes the
output path. Name changes then leave the custom path intact. Automatic Browse starts at the root;
custom Browse starts at the nearest existing output ancestor. New/Open/Save As share the effective
root: a valid configured directory, then existing Documents, Home, or cwd. Save As uses a directory
dialog rooted there with the current project name prefilled; it does not create that directory
until the user explicitly does so. Ordinary Save keeps its current project destination.
Missing/corrupt preferences safely fall back without creating a root or rewriting preferences.
Plugin/toolchain/IOC/source-package dialogs and the five-page flow keep their existing semantics.
