from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView

from silverstar_flp.core.i18n import Translator
from silverstar_flp.decoder_profiles.mission_snapshot import MissionSnapshot_Read
from silverstar_flp.ui.mission_snapshot import MissionSnapshotDialog
from tests.test_mission_snapshot_view import _Objects_Write
from silverstar_data_contracts.objects import ObjectCatalog_DefaultGet


def test_verified_actual_object_decoder_shows_structured_readonly_tabs(qtbot, tmp_path):
    identity = _Objects_Write(tmp_path, schema=3)
    snapshot = MissionSnapshot_Read(tmp_path, identity, object_catalog=ObjectCatalog_DefaultGet())
    dialog = MissionSnapshotDialog(snapshot, Translator('zh_CN'))
    qtbot.addWidget(dialog)
    assert dialog.tabs.count() == 8
    radio = dialog.tabs.widget(1)
    assert radio.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    texts = [radio.item(row, 1).text() for row in range(radio.rowCount())]
    assert 'sx127x' in texts and 'E32-400M20S' in texts
    assert '不使用当前工程默认值' in dialog.status.text()
    assert radio.horizontalHeaderItem(0).text() == '记录字段'


def test_missing_or_invalid_object_never_displays_default_parameters(qtbot):
    for snapshot in (None, {'status': 'invalid', 'reason': 'CRC mismatch', 'radio': {'frequency_hz': 434000000}}):
        dialog = MissionSnapshotDialog(snapshot, Translator('en_US'))
        qtbot.addWidget(dialog)
        assert dialog.tabs.count() == 0
        assert 'unavailable' in dialog.status.text()


def test_active_installation_presents_recorded_matrices_and_archive_identity(qtbot,tmp_path):
    identity=_Objects_Write(tmp_path,4,True)
    snapshot=MissionSnapshot_Read(tmp_path,identity,object_catalog=ObjectCatalog_DefaultGet())
    dialog=MissionSnapshotDialog(snapshot,Translator('zh_CN'));qtbot.addWidget(dialog)
    table=dialog.tabs.widget(6)
    rows=[(table.item(row,0).text(),table.item(row,1).text()) for row in range(table.rowCount())]
    assert any(name=='实际校正来源' and value=='recorded_active_installation' for name,value in rows)
    assert any('原始归档 SHA-256' in name and len(value)==64 for name,value in rows)
    assert len([name for name,_ in rows if 'M → A 安装旋转' in name])==9
    assert any('硬件验证' in name and value=='否' for name,value in rows)
