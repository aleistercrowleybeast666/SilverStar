from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.project.model import DeviceInstance
from silverstar_fccg.ui.device_initialization import (
    FIELDS,
    InitializationSection_Create,
)
from silverstar_fccg.ui.pages.components import DevicesPage
from silverstar_fccg.ui.theme import Theme_Apply


def test_fixed_device_initialization_is_visible_localized_and_read_only(
    workspace_root, qapp, tmp_path
):
    font_id = QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
    if font_id >= 0:
        qapp.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("InitializationView")
    model.device_instances = [
        DeviceInstance(i.instance_id, "silverstar.device.imu.bmi088")
        if i.instance_id == "imu0"
        else i
        for i in model.device_instances
    ]
    original = deepcopy(model.Dictionary_Get())
    views = service.DeviceInstanceViews_Get(model)
    imu = next(v for v in views if v.instance_id == "imu0")
    assert imu.initialization["output_rate_hz"] == 200
    assert imu.initialization["accelerometer_range_g"] == 24
    # Service copies mutable metadata: rendering may never change the catalog.
    isolated = service.DeviceInstanceViews_Get(model)[0]
    isolated.initialization["test_only"] = True
    assert "test_only" not in service.catalog.Component_Get(
        isolated.plugin_id
    ).metadata.get("initialization", {})
    page = DevicesPage(Translator("en_US"))
    page.resize(1100, 900)
    changes = []
    page.instanceChanged.connect(lambda *args: changes.append(args))
    page.Configuration_Set(service.ComponentViews_Get(), views)
    page.show()
    for theme in ("light", "dark"):
        Theme_Apply(qapp, theme)
        for language in ("en_US", "zh_CN"):
            page.Language_Apply(Translator(language))
            section = page.initialization_sections["imu0"]
            section.toggle_button.setChecked(True)
            qapp.processEvents()
            QTest.qWait(50)
            qapp.processEvents()
            assert section.body.isEnabled()
            rate = section.findChild(QLabel, "deviceInitialization_imu0_output_rate_hz")
            assert rate.text() == "200"
            hardware = section.findChild(
                QLabel, "deviceInitialization_imu0_hardware_status"
            )
            expected = imu.initialization.get("hardware_status")
            assert hardware.text() == (expected[language] if isinstance(expected, dict)
                                       else Translator(language).Text_Get("device.init.unverified"))
            assert "not hardware verified" in hardware.text().lower() or "未" in hardware.text()
            image = section.grab()
            assert image.width() > 200 and image.height() > 200
            assert image.save(str(tmp_path / f"initialization_{theme}_{language}.png"))
            for field in FIELDS:
                assert (
                    Translator(language).Text_Get("device.init." + field)
                    != "device.init." + field
                )
    assert model.Dictionary_Get() == original
    assert not changes
    # A plugin without readback evidence must not be shown as readback success.
    unknown = replace(imu, initialization={"output_rate_hz": 200}, runtime_defaults={})
    section = InitializationSection_Create(unknown, Translator("en_US"), expanded=True)
    assert (
        section.findChild(QLabel, "deviceInitialization_imu0_readback")
        .text()
        .startswith("Undeclared")
    )
    section.close()
    page.close()
