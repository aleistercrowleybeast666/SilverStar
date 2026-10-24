"""Operator workflow contracts with synthetic target memory only."""
import json
import os
from pathlib import Path
from threading import Event

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox
from test_probe_ui import panel as probe_panel_fixture
from test_swd_firmware import ImageMemory, load
from test_swd_firmware import arm_elf as diagnostic_elf_fixture
from test_swd_session import PROBE, FakeMemory
from test_swd_ui import swd_panel as swd_panel_fixture
from test_swd_ui import wait_for
from transport.swd_session import SwdResult as R
from transport.swd_session import SwdSession

arm_elf=diagnostic_elf_fixture
swd_panel=swd_panel_fixture
panel=probe_panel_fixture


def test_fourth_page_has_no_manual_mcu_selector_and_is_compact(swd_panel):
    window, _, create = swd_panel
    create(SwdSession)
    page = window.maintenance_page
    window.resize(1280,720)
    window.pages.setCurrentWidget(window.maintenance_scroll)
    QTest.qWait(80)
    visible_target_choices = [widget for widget in page.findChildren(QComboBox)
        if widget.isVisibleTo(page) and any(widget.itemText(i).startswith('STM32') for i in range(widget.count()))]
    assert not visible_target_choices, 'Main page still asks the operator to select a chip part'
    assert window.maintenance_scroll.verticalScrollBar().maximum()==0, 'Common fourth-page content requires a long page scroll'


def test_import_is_allowed_after_explicit_readonly_attachment(swd_panel,arm_elf,tmp_path):
    window, _, create = swd_panel
    backends = []
    def factory(**kwargs):
        backend = ImageMemory(kwargs['firmware']) if kwargs.get('firmware') else FakeMemory(kwargs['cancel'])
        backends.append(backend)
        return SwdSession(**kwargs,_backend_factory=lambda _:backend)
    manager = create(factory)
    assert manager.attach()
    wait_for(lambda: manager.snapshot is not None)
    descriptor = tmp_path/'fixture.ssdiag'
    descriptor.write_text(json.dumps(load(arm_elf).descriptor),encoding='utf-8')
    assert manager.import_files([descriptor,arm_elf]), 'Connected target cannot accept an offline firmware import'
    wait_for(lambda: manager.import_worker is None and manager.snapshot is not None and manager.snapshot.symbols=='matched')
    assert manager.firmware is not None and manager.worker is not None
    assert window.debug_port_combo.isEnabled(), 'Independent maintenance controls were tied to ELF matching'


def test_selected_f407_rejects_a_different_family_before_flash_reads(arm_elf):
    firmware = load(arm_elf)
    backend = ImageMemory(firmware)
    backend.words[0xE0042000] = 0x10070435
    session = SwdSession(firmware=firmware,_backend_factory=lambda _:backend)
    try:
        reply = session.Swd_Attach(PROBE)
        assert reply.result==R.TargetMismatch, 'Core-only match accepted a contradictory STM32 device family'
        assert not any(0x08000000<=address<0x08200000 for address,_ in backend.reads)
    finally:
        session.Swd_Detach()


def test_firmware_mismatch_keeps_identity_without_polling_ram(swd_panel,arm_elf):
    _, _, create = swd_panel
    firmware = load(arm_elf)
    backend = ImageMemory(firmware)
    backend.bad_flash = True
    verified = Event()
    class Session(SwdSession):
        def Swd_VerifyFirmware(self):
            reply = super().Swd_VerifyFirmware()
            verified.set()
            return reply
    manager = create(lambda **kwargs:Session(**kwargs,_backend_factory=lambda _:backend))
    manager.firmware = firmware
    assert manager.attach()
    wait_for(verified.is_set)
    wait_for(lambda: manager.status=='swd.firmware_mismatch')
    QTest.qWait(120)
    assert manager.worker is not None and backend.closed==0, 'A pure firmware mismatch discarded the connected identity'
    reads = list(backend.reads)
    QTest.qWait(1100)
    assert backend.reads==reads, 'Unmatched firmware continued diagnostic/RAM polling'


@pytest.mark.parametrize('language',['zh_CN','en_US'])
@pytest.mark.parametrize('theme',['light','dark'])
def test_fourth_page_preserves_3d_instance_and_compact_cards(swd_panel,language,theme):
    window, _, create=swd_panel
    create(SwdSession)
    window.i18n.set_language(language);window.retranslate_ui()
    window.theme_combo.setCurrentIndex(window.theme_combo.findData(theme))
    window.resize(1280,720)
    view=window.gl_view
    view.show()
    QTest.qWait(80)
    context=view.context() if QApplication.platformName()=='windows' else None
    if QApplication.platformName()=='windows': assert context is not None and context.isValid()
    page=window.maintenance_page
    evidence=os.environ.get('GSHC_STAGE1_QA_DIR')
    for width in (1280,1600,1024,1280):
        window.resize(width,720)
        QTest.qWait(60)
        sizes=window.content_splitter.sizes()
        left=window.attitude_panel.geometry()
        for index in (3,0,1,2,3)*2:
            window.pages.setCurrentIndex(index)
            QTest.qWait(20)
            assert window.gl_view is view
            assert window.attitude_panel.isVisible()
            assert window.content_splitter.sizes()==sizes
            assert window.attitude_panel.geometry()==left
            if context is not None: assert view.context() is context and context.isValid()
    assert window.maintenance_scroll.verticalScrollBar().maximum()==0
    viewport=QRect(window.maintenance_scroll.viewport().mapTo(window,QPoint()),window.maintenance_scroll.viewport().size())
    for box,value,age in page.summary_cards.values():
        assert not box.isEnabled() and 'UNKNOWN' in value.text()
        assert viewport.contains(QRect(box.mapTo(window,QPoint()),box.size()))
    assert not page.btn_swd_variables.isEnabled()
    if evidence:
        root=Path(evidence);root.mkdir(parents=True,exist_ok=True)
        assert window.grab().save(str(root/f'{language}_{theme}_runtime.png'))
        page.sections.setCurrentWidget(page.tf_section)
        assert window.grab().save(str(root/f'{language}_{theme}_tf.png'))
