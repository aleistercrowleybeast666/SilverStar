# 93fd895 GUI QA 修复记录

基线：`93fd895e490a20fa08cd94d6b8e72645fdb16b12`。输入证据为用户提供的 `SilverStar_93fd895_GUI_QA_and_RepairPrompt.zip`；解压、测试输出及生成工程保存在 Git 忽略的 `.work/`。本次仅修复 FCCG、GSHC、FLP 的界面及相关配置校验，不修改固件数学、AIR/SSLOG 格式或外场准入结论。

## FCCG

- 原有策略下拉在 `currentIndexChanged` 内同步刷新表单，`removeRow` 会删除仍在原生 popup 事件栈中的下拉控件。非对准策略改为下一轮 Qt 事件循环合并提交；新建或打开工程时清除未执行的旧策略事件。对准策略切换只更新保持存活的本地草稿编辑器，不触发页面重建。
- 初始对准策略、2–6 条约束、权重和外部姿态源设置作为一份草稿。确认时从当前编辑框读取最新文本、检查有限数值和范围、结构及来源资格，然后一次提交到 ProjectModel；取消恢复上次提交快照。未确认草稿不进入保存结果，保存后明确提示“上次已确认配置”；生成和目标构建要求先确认。添加、移除和类型切换延后执行，避免删除正在发出信号的控件。
- 导航页移除与内层控件重复的分组边框；估计算法按“纯惯导、KF6算法、ESKF15算法”显示，保留原有 `None`、KF6、ESKF15 身份。
- Ground 无线候选保留不兼容及旧工程失效选择并显示原因。界面和生成校验共用 AIR Link 物理兼容判断；Flight-only 项目同样检查 Flight radio。资源、时钟和生成所有权仍由后端校验。
- 生成任务活动期间禁用生成按钮并幂等忽略重复请求。FCCG 根入口仍在构造、设置语言和主题后首次调用 `show()`。
- 用户在后台任务期间确认关闭时，窗口先请求取消并等待 worker 的完成信号，再关闭窗口；完成回调不会在关闭途中开启第二阶段任务。这避免 Qt signal 对象先于仍在运行的 worker 被销毁。

## GSHC 与 FLP

- GSHC 将连接状态放在独立的顶栏行；按当前字体宽度对长状态文本换行，tooltip 保留原文。串口配置及连接所用端口字符串没有变动。
- FLP 两种主题显式设置工程名的高对比文字色。顶栏拆为身份/设置和工程名两行，长名称省略显示并通过 tooltip 保留完整路径。`.ssdecoder` 精确匹配、原始日志和 Recorded/Offline 边界没有变动。
- GUI 测试改为按测试文件定位源码，并仅在 Windows 字体实际存在时加载；不再假定当前工作目录或 Linux 上有 Windows 字体。

## 验证边界

- Windows 原生 Qt popup 已执行五轮矢量与外部姿态源往返；非对准策略 popup、首个 Show/Paint 时的七页、主题和几何状态也有独立进程回归。另通过实际根启动器 `FCCG.py` 验证首次 Show/Paint 前已有七页、主题和正数几何尺寸。原始崩溃证据来自 Linux Qt 6.11.2；本机为 Windows PySide6 6.10.1，因此 Linux 原生回归仍需在相同桌面环境复测。
- 本轮没有烧写硬件、打包程序或进行新的外场验证。离屏测试不能验证 OpenGL 3D 可见桌面效果；启动瞬时闪屏如需确认仍应进行人工可见桌面观察。
- F407 Flight 与 F103 Ground 的真实 GUI 生成测试通过（`test_gui_generates_f407_and_f103`，817 秒）：`Flight_Controller/Makefile`、`Ground_Station/Makefile` 和各自 VS Code 工作区均生成；Ground 生成后 Flight 目录中的用户自有 `user-notes.txt` 字节未变。已有 `test_round2_targets.py` 还验证修改后的生成文件会被所有权门禁拒绝覆盖。
- FCCG GUI、对准、无线和目标相关回归 45 项通过；耗时的真实 GUI 生成另有 1 项通过。GSHC 相关 GUI 套件 68 项通过，覆盖 COM 状态布局和 100%/150%/200% 缩放。FLP GUI、工程根目录和导出相关套件 69 项通过。未确认草稿保存的新增断言单独通过。
- Python `compileall`、改动文件 Ruff `F` 规则和 `git diff --check` 通过。Git 仅提示工作区 LF/CRLF 转换，没有空白字符错误。
