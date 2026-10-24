from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QFont, QFontDatabase

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.project.model import (RAW_IMU_NOSE_AXIS_MAPS, RawImuAxisMap_Get,
    ProjectModel_Parse, ProjectModelError)
from silverstar_fccg.project.sensor_installation import SensorPosition, SensorInstallationConfiguration, SensorInstallationSnapshot_Get
from silverstar_fccg.ui.sensor_layout_view import SensorLayoutView
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.generator.render import _InstanceResourcesSource_Render

APP = Path(__file__).resolve().parents[1]


def test_all_24_discrete_mounts_are_proper_rotations_and_old_six_are_unchanged():
    matrices = set()
    for nose in RAW_IMU_NOSE_AXIS_MAPS:
        assert RawImuAxisMap_Get(nose) == RAW_IMU_NOSE_AXIS_MAPS[nose]
        for x_axis in RAW_IMU_NOSE_AXIS_MAPS:
            if x_axis[0] == nose[0]:
                with pytest.raises(ValueError, match='perpendicular'):
                    RawImuAxisMap_Get(nose, x_axis)
                continue
            mapping = RawImuAxisMap_Get(nose, x_axis)
            rotation = np.array([[int(abs(index) == column+1) * np.sign(index) for column in range(3)] for index in mapping])
            np.testing.assert_array_equal(rotation @ rotation.T, np.eye(3))
            assert np.linalg.det(rotation) == pytest.approx(1)
            np.testing.assert_array_equal(np.cross(rotation[0], rotation[1]), rotation[2])
            matrices.add(tuple(rotation.flat))
    assert len(matrices) == 24
    for invalid in (False, 0, [], {}):
        with pytest.raises(ValueError): RawImuAxisMap_Get('z_positive', invalid)


def test_layout_uses_true_positions_equal_scale_and_keeps_unknown_separate(qapp, tmp_path):
    for font in ('msyh.ttc', 'segoeui.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
    view = SensorLayoutView(Translator('zh_CN'))
    instances = [SimpleNamespace(instance_id=name, component_class='imu', position_body_m=position)
        for name, position in [('imu0', (0.02, -0.03, 0.1)), ('imu1', (0, 0, 0)), ('imu2', None)]]
    view.Configuration_Set(instances)
    assert set(view.positions) == {'imu0', 'imu1'} and view.missing == ('imu2',)
    box = QRectF(0, 0, 200, 200)
    origin = view.Point_Project((0, 0, 0), 0, 2, box)
    point = view.Point_Project((0.02, -0.03, 0.1), 0, 2, box)
    assert point.x() > origin.x() and point.y() < origin.y()
    assert (origin.y()-point.y()) / (point.x()-origin.x()) == pytest.approx(5)
    try:
        view.resize(1050, 320); view.show(); qapp.processEvents()
        assert view.grab().save(str(tmp_path/'layout.png'))
    finally:
        view.close()


def test_real_geometry_edit_navigation_point_not_primary_and_hatch_mapping(tmp_path, qapp):
    service = FccgService(APP); service.policy = WorkspacePolicy(APP.parents[1])
    window = MainWindow(SettingsStore(tmp_path/'settings.ini'), service=service)
    errors = []
    window._Error_Show = errors.append
    try:
        assert not hasattr(window.devices_page, 'installation_origin')
        assert 'magnetometer0' in window.devices_page.device_combos
        assert 'magnetometer' in window.devices_page.add_buttons
        window._SensorPosition_Change('imu0', (0.02, -0.03, 0.1))
        window._SensorPosition_Change('gnss0', (0.1, 0.2, 0.5))
        assert window._model.sensor_installation.Dictionary_Get()['origin_kind'] == 'fixed_navigation_reference_point'
        assert window._model.DeviceInstance_Get('imu0').position_body_m == SensorPosition(0.02,-0.03,0.1)
        snapshot = SensorInstallationSnapshot_Get(window._model, service.catalog)
        assert snapshot['runtime_applied'] is False and snapshot['axes']['handedness'] == 'right'
        import jsonschema
        contract = json.loads((APP.parents[1]/'contracts/sensor_installation_v2.schema.json').read_text(encoding='utf-8'))
        jsonschema.validate(snapshot, contract)
        assert window.devices_page.installation_map.positions['imu0'] == (0.02,-0.03,0.1)
        coordinates = [item.position_body_m for item in window._model.device_instances]
        window._model.sensor_installation = SensorInstallationConfiguration('legacy CAD datum')
        window._Project_Refresh()
        assert window.devices_page.installation_adopt_button.isVisibleTo(window.devices_page)
        window.devices_page.installation_adopt_button.click(); qapp.processEvents()
        assert window._model.sensor_installation.Dictionary_Get()['schema'].endswith('/2')
        assert [item.position_body_m for item in window._model.device_instances] == coordinates
        window.resize(1440, 960); window.show(); qapp.processEvents()
        editor = window.devices_page.position_editors['imu0']
        assert '<sub>imu0</sub>' in editor.vector_label.text() and '<sup>b</sup>' in editor.vector_label.text()
        for axis, spin in editor.coordinates.items():
            label = editor.axis_labels[axis]
            assert label.text() == axis
            assert spin.geometry().left() - label.geometry().right() <= 12
        window._DeviceInstance_Change('imu0', 'silverstar.device.imu.bmi088')
        window._RawImuXAxis_Change('imu0', 'y_positive'); qapp.processEvents()
        assert window._model.DeviceInstance_Get('imu0').mount_x_axis == 'y_positive'
        assert window.devices_page.mount_x_combos['imu0'].currentText()=='+y_s'
        assert RawImuAxisMap_Get('z_positive','y_positive') == (2,-1,3)
        data = window._model.Dictionary_Get()
        restored = ProjectModel_Parse(data)
        assert restored.Dictionary_Get() == data and data['format_version'] == 22
        # Resource rendering needs valid hardware. This metadata test never
        # invents I2C resources to claim the reference UART board supports BMI088.
        old = dict(data); old['format_version'] = 20
        with pytest.raises(ProjectModelError, match='format_version 22'):
            ProjectModel_Parse(old)
        assert not errors
    finally:
        window.close(); qapp.processEvents()


@pytest.mark.parametrize('font_size,width', [(9, 720), (14, 720), (9, 1280), (14, 1280)])
def test_collocated_labels_fit_actual_font_and_do_not_move_measurements(qapp, font_size, width):
    for font in ('msyh.ttc', 'segoeui.ttf'):
        font_path = Path('C:/Windows/Fonts') / font
        if font_path.is_file(): QFontDatabase.addApplicationFont(str(font_path))
    view = SensorLayoutView(Translator('zh_CN'))
    view.setFont(QFont('Microsoft YaHei', font_size))
    instances = [SimpleNamespace(instance_id=name, component_class=kind, position_body_m=position)
        for name, kind, position in [('imu0', 'imu', (0,0,0)), ('gnss0', 'gnss', (0,0.1,0))]]
    view.Configuration_Set(instances)
    try:
        view.resize(width, 320); view.show(); qapp.processEvents(); view.grab()
        assert len(view._label_boxes) == 6
        for panel in range(3):
            labels = [rect for index, _identity, rect in view._label_boxes if index == panel]
            assert len(labels) == 2 and not labels[0].intersects(labels[1])
            assert all(view._plot_boxes[panel].contains(rect) for rect in labels)
        assert view.positions == {'imu0':(0,0,0), 'gnss0':(0,0.1,0)}
        assert all(rect.height() >= view.fontMetrics().height() for _panel, _identity, rect in view._label_boxes)
    finally:
        view.close()


def test_explicit_hatch_axis_enters_real_generated_resource_initializer(builtin_catalog):
    from test_internal_platform_refactor import _CustomModel_Create
    from silverstar_fccg.project.model import DeviceInstance
    from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
    model = _CustomModel_Create(builtin_catalog, [DeviceInstance('imu0', 'silverstar.device.imu.bmi088', mount_x_axis='y_positive')])
    model.resource_assignments = {'imu0:data':'I2C1', 'imu0:gyro':'I2C1', 'imu0:time':'SYSTEM_TIME'}
    configured = ProjectConfiguration_Reconcile(model, builtin_catalog)
    assert configured.resource_resolution.valid
    source = _InstanceResourcesSource_Render(configured.model, builtin_catalog)
    assert '.axis_map = { 2, -1, 3 }' in source
