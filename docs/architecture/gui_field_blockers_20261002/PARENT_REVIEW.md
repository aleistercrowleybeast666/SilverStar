# 父线程审核补充

生产代码未在后续复测中改变：功能版本仍为 08a113d；后续修改只修复文档链接验证及补充证据。

最小生产 diff：新草稿 Ground 默认 custom 与 Flight 对齐，Auto 只在新草稿创建处设置；Ground 无资源原因及真实 USART 显示，失效 UART 禁选且绑定保留；唯一 Radio 模块选择与 Flight 对齐；FLP 从两行改为一行并让项目值可收缩。根三入口整理在 a97acbc，SCG 502e527 和 FLP 08a113d 可单独审核。

根文件完整迁移清单：

| 原根文件 | 新位置 | 兼容/引用同步 |
| --- | --- | --- |
| FCCG.py | apps/FCCG/FCCG.py | 调用同目录 main.Application_Main；公开根入口 SCG.py |
| silverstar_version.py | tools/silverstar_version.py | pyproject 动态版本改为 tools.silverstar_version.__version__；VERSION 查找 parents[1] |
| freeze_memory_final.py | tools/freeze_memory_final.py | 仓库根定位 parents[1]，既有证据输出位置不变 |

除此之外无根文件删除/迁移。根 Python 文件恰为 SCG.py、GSHC.py、FLP.py。旧项目导入方式、schema、内部 apps/FCCG 包名及配置路径保持；原根 FCCG.py 的外部快捷方式需指向 SCG.py 或新兼容启动器。

以下代码从实际文件逐字抽取，不是伪代码。

## 新草稿 Ground 默认及 Auto（不会在旧配置 Parse 中覆盖）

`apps/FCCG/src/silverstar_fccg/app/service.py:131`

```python
    def ProjectDraft_Create(self, name: str) -> ProjectModel:
        model = self.ReferenceProject_Create(name)
        model.board = ""
        provider = self.HardwareProviderForMcu_Get(model.mcu)
        model.hardware = (
            HardwareConfiguration(
                mode="custom",
                source_kind="manual_import",
                provider=provider,
            )
            if provider
            else HardwareConfiguration()
        )
        model.resource_assignments = {}
        model.build = replace(model.build, memory_layout="auto")
        model.ground_target = replace(
            model.ground_target,
            hardware=HardwareConfiguration(
                mode="custom", source_kind="manual_import", provider=provider,
            ) if provider else HardwareConfiguration(),
        )
        return self.ProjectConfiguration_Reconcile(model).model
```

## Radio 一致性与 UART 同值接口绑定保留分支

`apps/FCCG/src/silverstar_fccg/ui/main_window.py:1681`

```python
    def _GroundTarget_Change(self, field: str, value: object) -> None:
        if field == "board":
            self._GroundBoard_Change(str(value or ""))
            return
        def change(candidate: ProjectModel) -> None:
            ground = candidate.ground_target
            updates = {field: value}
            if field == "radio_plugin" and value != ground.radio_plugin:
                radio = self._service.catalog.Component_Get(str(value)) if value else None
                modules = radio.radio.modules if radio is not None and radio.radio is not None else {}
                # Flight also adopts the only declared module. Multiple choices
                # remain explicit; shared AIR settings and power are preserved.
                updates["module_variant"] = next(iter(modules)) if len(modules) == 1 else ""
                updates["resource_assignments"] = {}
            if field == "pc_interface" and value != ground.pc_interface:
                updates["pc_resource"] = ""
            candidate.ground_target = replace(ground, **updates)
        self._ProjectConfiguration_Change(change)
```

## 从已有板返回 custom 的实际分支

`apps/FCCG/src/silverstar_fccg/ui/main_window.py:1700`

```python
    def _GroundBoard_Change(self, board_id: str) -> None:
        if not board_id:
            self._ProjectConfiguration_Change(
                lambda candidate: setattr(
                    candidate, "ground_target", replace(
                        candidate.ground_target, board="", mcu="",
                        hardware=HardwareConfiguration(
                            mode="custom", source_kind="manual_import",
                            provider="silverstar.hardware_provider.stm32_cubemx",
                        ), resource_assignments={}, pc_resource="",
                    )
                )
            )
            return
```

## 实际 UART 清单、无库存原因、失效绑定禁选

`apps/FCCG/src/silverstar_fccg/ui/pages/targets.py:337`

```python
        uart_selected = ground.enabled and ground.pc_interface == "uart"
        self.pc_resource.setEnabled(uart_selected)
        self.baudrate.setEnabled(uart_selected)
        self.pc_resource.clear()
        self.pc_resource.addItem("—", "")
        uarts = tuple(resource for resource in ground.hardware.resources if resource.kind == "uart")
        for resource in uarts:
            physical = resource.metadata.get("physical_resource", resource.resource_id)
            self.pc_resource.addItem(f"{physical} · {resource.resource_id}", resource.resource_id)
        missing = bool(ground.pc_resource) and self.pc_resource.findData(ground.pc_resource) < 0
        if missing:
            self.pc_resource.addItem(
                self._translator.Text_Get("ground.uart_unavailable", resource=ground.pc_resource),
                ground.pc_resource,
            )
            self.pc_resource.model().item(self.pc_resource.count() - 1).setEnabled(False)
        self.pc_resource.setCurrentIndex(max(0, self.pc_resource.findData(ground.pc_resource)))
        reason = ("ground.uart_select_hardware" if not ground.hardware.inventory else
                  "ground.uart_none" if not uarts else
                  "ground.uart_missing_binding" if missing else "")
        self.pc_resource_notice.setVisible(ground.pc_interface == "uart" and bool(reason))
        self.pc_resource_notice.setText(self._translator.Text_Get(reason) if reason else "")
        self.pc_resource.setToolTip(self.pc_resource_notice.text())
        self.pc_resource.setEnabled(uart_selected and bool(uarts))
        self.baudrate.CommittedValue_Set(ground.baudrate)
```

## 生成与硬件保存可用性

`apps/FCCG/src/silverstar_fccg/ui/pages/targets.py:392`

```python
        self.generate_button.setEnabled(ground.enabled and ground.hardware.mode != "unselected")
        self.save_instance.setEnabled(
            ground.hardware.mode == "custom" and bool(ground.hardware.snapshot_id)
            and bool(ground.hardware.build_sources)
        )
```

## BuildOptions 保持 legacy 默认（旧配置语义）

`apps/FCCG/src/silverstar_fccg/project/model.py:103`

```python
class BuildOptions:
    target_profile: str = ""
    make_command: str = "mingw32-make"
    toolchain_prefix: str = "arm-none-eabi-"
    gcc_path: str = ""
    flash_command: str = ""
    eide_mode: str = "native"
    tool_paths: dict[str, str] = field(default_factory=dict)
    memory_layout: str = "legacy"
```

## 旧缺字段迁移保持 legacy；显式策略原样解析

`apps/FCCG/src/silverstar_fccg/project/model.py:1500`

```python
    memory_layout = data.get("memory_layout", "legacy")
    if memory_layout not in ("legacy", "eskf_window_sram", "auto"):
        raise ProjectModelError("build.memory_layout is invalid")
```

## FLP 一行顶栏全部布局原文

`apps/FLP/src/silverstar_flp/ui/main_window.py:165`

```python
        header = QFrame()
        header.setObjectName("headerBar")
        header.setMinimumHeight(54)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 6, 14, 6)
        header_layout.setSpacing(8)
        self.title_label = QLabel()
        self.title_label.setObjectName("headerTitle")
        self.title_label.setStyleSheet("font-size: 16px;")
        self.version_label = QLabel(f"v{__version__}")
        self.version_label.setObjectName("headerVersion")
        self.credit_label = QLabel()
        self.credit_label.setObjectName("headerCredit")
        self.project_caption_label = QLabel()
        self.project_caption_label.setObjectName("headerControlLabel")
        self.project_name_label = ProjectHeaderLabel()
        self.project_name_label.setObjectName("headerProject")
        self.language_label = QLabel()
        self.language_label.setObjectName("headerControlLabel")
        self.language_combo = StandardComboBox()
        self.language_combo.setObjectName("headerLanguageCombo")
        self.language_combo.view().setObjectName("headerComboPopup")
        self.language_combo.addItem("简体中文", "zh_CN")
        self.language_combo.addItem("English", "en_US")
        self.language_combo.currentIndexChanged.connect(self._Language_Selected)
        self.theme_label = QLabel()
        self.theme_label.setObjectName("headerControlLabel")
        self.theme_combo = StandardComboBox()
        self.theme_combo.setObjectName("headerThemeCombo")
        self.theme_combo.view().setObjectName("headerComboPopup")
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        self.theme_combo.currentIndexChanged.connect(self._Theme_Selected)
        identity_row = header_layout
        identity_row.addWidget(self.title_label)
        identity_row.addWidget(self.version_label)
        identity_row.addWidget(self.credit_label)
        identity_row.addWidget(self.project_caption_label)
        identity_row.addWidget(self.project_name_label, 1)
        identity_row.addWidget(self.language_label)
        identity_row.addWidget(self.language_combo)
        identity_row.addWidget(self.theme_label)
        identity_row.addWidget(self.theme_combo)
        root_layout.addWidget(header)
```

## 项目名省略与 dirty 标记实际控件

`apps/FLP/src/silverstar_flp/ui/widgets.py:60`

```python
class ProjectHeaderLabel(QLabel):
    """Elide against the final widget geometry without changing layout hints."""

    def __init__(self) -> None:
        super().__init__()
        self._full_name = ""
        self._dirty = False
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def ProjectName_Set(self, name: str, dirty: bool) -> None:
        self._full_name = name
        self._dirty = dirty
        self._Text_Refresh()

    def _Text_Refresh(self) -> None:
        suffix = " *" if self._dirty else ""
        metrics = self.fontMetrics()
        width = max(0, self.contentsRect().width() - metrics.horizontalAdvance(suffix))
        self.setText(metrics.elidedText(self._full_name, Qt.TextElideMode.ElideRight, width) + suffix)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._Text_Refresh()
```

## FLP 名称/路径提示刷新

`apps/FLP/src/silverstar_flp/ui/main_window.py:1159`

```python
    def _ProjectHeader_Refresh(self) -> None:
        path = self._project.project_path
        full_name = path.stem if path is not None else self._translator.Text_Get("project.unsaved")
        if self._silverstar_project_root is not None:
            session = path.stem if path is not None else self._translator.Text_Get("project.analysis_unsaved")
            full_name = self._silverstar_project_root.name + " / " + session
        self.project_name_label.ProjectName_Set(full_name, self._project_dirty)
        if self._project_dirty:
            full_name += " *"
        if self._silverstar_project_root is not None:
            tooltip = "\n".join(value for value in (
                full_name, str(self._silverstar_project_root),
                str(path.resolve()) if path is not None else "") if value)
        else:
            tooltip = str(path.resolve()) if path is not None else ""
        self.project_name_label.setToolTip(tooltip)
```

## 入口与版本兼容原文：SCG.py

`SCG.py:1`

```python
"""Public SCG entry point; FCCG.py remains a compatible legacy launcher."""
from tools.launch import Application_Start

if __name__ == "__main__":
    raise SystemExit(Application_Start("SCG"))
```

## 入口与版本兼容原文：apps/FCCG/FCCG.py

`apps/FCCG/FCCG.py:1`

```python
"""Compatible FCCG launcher; the public root entry is SCG.py."""
from main import Application_Main

if __name__ == "__main__":
    raise SystemExit(Application_Main())
```

## 入口与版本兼容原文：tools/launch.py

`tools/launch.py:1`

```python
"""Locate a migrated application without changing the user's working directory."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def Application_Start(name: str) -> int:
    implementation = "FCCG" if name == "SCG" else name
    application_root = Path(__file__).resolve().parents[1] / "apps" / implementation
    sys.path.insert(0, str(application_root))
    try:
        runpy.run_path(str(application_root / "main.py"), run_name="__main__")
    except SystemExit as result:
        return int(result.code or 0)
    return 0
```

## 入口与版本兼容原文：tools/silverstar_version.py

`tools/silverstar_version.py:1`

```python
"""Root release identity for packaging and suite tooling."""

from pathlib import Path

__version__ = (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="ascii").strip()
```

## 原失败及已完成修复

测试名为 `tests/integration/test_monorepo_baseline.py::test_current_document_links_resolve`。
首次失败：`docs/FCCG/evidence_flight_safety_batch1_20261001/AGENTS_SNAPSHOT.md` → `docs/FCCG/ARCHITECTURE.md`，被误解析为快照目录下的 `docs/FCCG/ARCHITECTURE.md`。

只读枚举共 9 条：AGENTS 快照内 7 条仓库根相对链接（FCCG 架构/运行时安全/编码规范，GSHC AIR/架构，FLP 架构/decoder）；REPORT 快照内 `evidence_flight_safety_batch1_20261001/INDEX.json` 和 `REMAINING_RULE5.json` 两条，应从原 docs/FCCG 目录解析。

没有修改冻结快照或 INDEX。验证器改为按 INDEX 的原始 source 目录解析，并先核验快照 SHA-256；所有目标仍逐条检查存在。新增回归证明真正不存在的目标和被修改的快照仍失败。完整重跑先前扩展集合（含最终入口测试及新验证器回归）：**41 passed**，见 extended_tests_r2.log。

## 父已查看原图后的对照

本人此前没有查看原附件。父线程已经通过官方云端 Library 材料化并查看，反馈原图 1920×1020 的项目标签/值分散在第二行。补拍同像素窗口后，“当前工程”和“未保存工程”与标题、版本、语言/主题在同一顶栏中，位于导航上方；长名/dirty 也不跨到第二行。实际 PNG 为 1920×1020 与窄窗 1250×875；逻辑尺寸分别 1536×816 和 1000×700，DPR 1.25，见 parent_comparison/geometry.json。

本机 Library 返回 `workspace_path=null`，文件名 `image(20261002-063455).png`；指定目的路径 `C:\Users\chdxm\Documents\Codex\2026-10-02\task-2\input\image(20261002-063455).png` 不存在，input 目录没有可读残留图像字节。不是许可拒绝；官方助手在 xattrs 阶段遇到 Windows os.setxattr 缺失。没有修改助手，没有再次下载，也不声称已看原附件。
