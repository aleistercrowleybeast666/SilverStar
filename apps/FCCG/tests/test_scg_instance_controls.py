"""Real Qt instance controls; saving writes project descriptions only."""
from dataclasses import replace
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QGroupBox

from silverstar_fccg.project.folder_contract import ProjectRoot_Save
from silverstar_fccg.ui.widgets import StandardComboBox
from test_f103_ground_reference import _GroundF103Model_Get
from test_scg_ui_metadata_hotfix import window


def _Wait(qapp, predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        QTest.qWait(5)
    assert predicate()


def _Show(window, qapp, page):
    window.resize(1280, 900)
    window.show()
    window.pages.setCurrentWidget(page)
    qapp.processEvents()


def _Instances(window, component_class):
    return [item for item in window._model.device_instances
            if window._service.Plugin_Get(item.plugin).component_class == component_class]


def _Reopen(window, qapp, directory):
    saved = window._model.Dictionary_Get()
    ProjectRoot_Save(window._model, directory)
    window._Project_Open(directory)
    qapp.processEvents()
    assert window._model.Dictionary_Get() == saved
    assert not list(directory.rglob('*.ssdecoder'))
    assert not list(directory.rglob('*.bin'))


def test_other_sensors_and_empty_barometer_add_are_visible(window, qapp):
    page = window.devices_page
    _Show(window, qapp, page)
    assert isinstance(page.other_group, QGroupBox)
    assert page.other_group.isVisible()
    assert not _Instances(window, 'barometer')
    assert page.add_buttons['barometer'].isVisible()
    assert page.add_buttons['barometer'].isEnabled()
    QTest.mouseClick(page.add_buttons['barometer'], Qt.MouseButton.LeftButton)
    _Wait(qapp, lambda: len(_Instances(window, 'barometer')) == 1
          and page.remove_buttons['barometer0'].isVisible())
    assert page.remove_buttons['barometer0'].isVisible()


@pytest.mark.parametrize('component_class', ['barometer', 'imu', 'gnss', 'telemetry'])
def test_device_quick_add_middle_delete_identity_and_reopen(window, qapp, tmp_path, component_class):
    window._model = window._service.ReferenceProject_Create('GuiInstanceControls')
    window._Project_Refresh()
    page = window.devices_page
    _Show(window, qapp, window.air_link_page if component_class == 'telemetry' else page)
    while len(_Instances(window, component_class)) < 3:
        page.add_buttons[component_class].click()
    qapp.processEvents()
    ids = [item.instance_id for item in _Instances(window, component_class)]
    assert ids == [component_class + str(index) for index in range(3)]
    window._model.resource_assignments[ids[1] + ':data'] = 'TEST_BINDING_MIDDLE'
    window._model.resource_assignments[ids[2] + ':time'] = 'PLATFORM_TIME_1'
    page.remove_buttons[ids[1]].click()
    qapp.processEvents()
    assert [item.instance_id for item in _Instances(window, component_class)] == [ids[0], ids[2]]
    assert ids[1] + ':data' not in window._model.resource_assignments
    assert window._model.resource_assignments[ids[2] + ':time'] == 'PLATFORM_TIME_1'
    form = page.telemetry_form if component_class == 'telemetry' else page.primary_form if component_class in {'imu', 'gnss'} else page.other_form
    assert form.labelForField(page.device_combos[ids[2]]).text() == window._translator.Text_Get('device.instance.' + component_class, index=2)
    page.add_buttons[component_class].click()
    qapp.processEvents()
    assert {item.instance_id for item in _Instances(window, component_class)} == set(ids)
    _Reopen(window, qapp, tmp_path / ('reopen_' + component_class))
    for language in ('en_US', 'zh_CN'):
        before = window._model.Dictionary_Get()
        window.Language_Apply(language)
        assert window._model.Dictionary_Get() == before
    while _Instances(window, component_class):
        identity = _Instances(window, component_class)[0].instance_id
        page.remove_buttons[identity].click()
    assert page.add_buttons[component_class].isEnabled()
    page.add_buttons[component_class].click()
    assert _Instances(window, component_class)[0].instance_id == ids[0]


def test_ground_legacy_single_has_matching_row_controls_without_migration(window, qapp):
    window._model = _GroundF103Model_Get(window._service.catalog)
    before = window._model.Dictionary_Get()
    window._Project_Refresh()
    _Show(window, qapp, window.air_link_page)
    page = window.ground_target_page
    assert page.radio_selection_group.isAncestorOf(page.enabled)
    row = page.radio_instances_editor.rows['radio0']
    assert isinstance(row['plugin'], StandardComboBox)
    assert row['plugin'].itemData(0) == ''
    assert row['remove'].isVisible() and row['remove'].isEnabled()
    assert row['plugin'].currentData() == window._model.ground_target.radio_plugin
    for language in ('en_US', 'zh_CN'):
        window.Language_Apply(language)
        assert window._model.Dictionary_Get() == before
    assert before['format_version'] == 14


def test_ground_rapid_add_middle_delete_reuse_and_saved_order(window, qapp, tmp_path):
    window._model = _GroundF103Model_Get(window._service.catalog)
    window._Project_Refresh()
    _Show(window, qapp, window.air_link_page)
    editor = window.ground_target_page.radio_instances_editor
    editor.add_button.click()
    editor.add_button.click()
    _Wait(qapp, lambda: len(window._model.ground_target.radio_instances) == 3)
    editor.rows['radio1']['remove'].click()
    _Wait(qapp, lambda: len(window._model.ground_target.radio_instances) == 2)
    assert [r.instance_id for r in window._model.ground_target.radio_instances] == ['radio0', 'radio2']
    assert editor.rows['radio2']['title'].text() == window._translator.Text_Get('ground.radio_title', id=2)
    editor.add_button.click()
    _Wait(qapp, lambda: len(window._model.ground_target.radio_instances) == 3)
    assert [r.instance_id for r in window._model.ground_target.radio_instances] == ['radio0', 'radio2', 'radio1']
    editor.initial_instance.setCurrentIndex(editor.initial_instance.findData('radio2'))
    _Wait(qapp, lambda: window._model.ground_target.active_radio_instance == 'radio2')
    _Reopen(window, qapp, tmp_path / 'ground_reopen')
    assert window._model.ground_target.active_radio_instance == 'radio2'


def test_ground_last_remove_clears_only_radio_and_add_restores_legacy_selection(window, qapp):
    window._model = window._service.ProjectConfiguration_Reconcile(
        _GroundF103Model_Get(window._service.catalog)).model
    previous = window._model.ground_target
    window._model.ground_target = replace(previous, resource_assignments={**previous.resource_assignments, 'other:keep': 'KEEP'})
    window._Project_Refresh()
    editor = window.ground_target_page.radio_instances_editor
    editor.rows['radio0']['remove'].click()
    _Wait(qapp, lambda: not window._model.ground_target.radio_plugin)
    ground = window._model.ground_target
    assert not ground.radio_instances
    assert ground.enabled == previous.enabled and ground.board == previous.board
    assert ground.hardware == previous.hardware and ground.pc_resource == previous.pc_resource
    assert ground.resource_assignments == {'other:keep': 'KEEP'}
    assert not editor.rows['radio0']['remove'].isEnabled()
    editor.add_button.click()
    _Wait(qapp, lambda: bool(window._model.ground_target.radio_plugin))
    assert not window._model.ground_target.radio_instances
    assert window._model.ground_target.module_variant


def test_estimator_display_order_and_legacy_ids_survive_refresh_reopen(window, qapp, tmp_path):
    expected = [None, 'silverstar.algorithm.estimator.sf6', 'silverstar.algorithm.estimator.kf6', 'silverstar.algorithm.estimator.eskf15']
    combo = window.flight_configuration_page.strategy_combos['estimator']
    assert [combo.itemData(i) for i in range(combo.count())] == expected
    for identity in expected:
        window._Strategy_Change('estimator', identity)
        qapp.processEvents()
        combo = window.flight_configuration_page.strategy_combos['estimator']
        assert combo.currentData() == identity
        _Reopen(window, qapp, tmp_path / ('algorithm_' + str(expected.index(identity))))
        assert window._model.strategies['estimator'] == identity


@pytest.mark.parametrize('case', ['legacy', 'first', 'middle', 'only'])
def test_ground_none_selection_uses_the_same_removal_boundary(window, qapp, case):
    window._model = window._service.ProjectConfiguration_Reconcile(
        _GroundF103Model_Get(window._service.catalog)).model
    window._Project_Refresh()
    editor = window.ground_target_page.radio_instances_editor
    if case != 'legacy':
        editor.add_button.click()
        _Wait(qapp, lambda: len(window._model.ground_target.radio_instances) == 2)
    if case in {'first', 'middle'}:
        editor.add_button.click()
        _Wait(qapp, lambda: len(window._model.ground_target.radio_instances) == 3)
    if case == 'only':
        editor.rows['radio0']['remove'].click()
        _Wait(qapp, lambda: len(window._model.ground_target.radio_instances) == 1)
    identity = 'radio1' if case in {'middle', 'only'} else 'radio0'
    editor.rows[identity]['plugin'].setCurrentIndex(0)
    _Wait(qapp, lambda: identity not in {
        radio.instance_id for radio in window._model.ground_target.radio_instances})
    if case in {'legacy', 'only'}:
        _Wait(qapp, lambda: not window._model.ground_target.radio_plugin)
        assert not window._model.ground_target.module_variant
    else:
        assert len(window._model.ground_target.radio_instances) == 2
        assert window._model.ground_target.active_radio_instance in {
            radio.instance_id for radio in window._model.ground_target.radio_instances}
    assert not any(key.startswith(identity + ':') for key in window._model.ground_target.resource_assignments)


def test_ground_reconcile_keeps_legacy_board_default_bindings(window):
    model = _GroundF103Model_Get(window._service.catalog)
    before = dict(model.ground_target.resource_assignments)
    reconciled = window._service.ProjectConfiguration_Reconcile(model).model
    assert not reconciled.ground_target.radio_instances
    assert reconciled.ground_target.resource_assignments == before


def test_ground_reconcile_does_not_restore_removed_primary_keys(window):
    from silverstar_fccg.project.ground_radios import GroundRadiosConfiguration_Apply
    from silverstar_fccg.project.model import GroundRadioConfigurations_Get
    model = _GroundF103Model_Get(window._service.catalog)
    radio = GroundRadioConfigurations_Get(model.ground_target)[0]
    model.ground_target = GroundRadiosConfiguration_Apply(model.ground_target,
        (replace(radio, instance_id='radio2'),), 'radio2')
    reconciled = window._service.ProjectConfiguration_Reconcile(model).model
    assert reconciled.ground_target.active_radio_instance == 'radio2'
    assert not any(key.startswith('radio0:') for key in reconciled.ground_target.resource_assignments)
    assert not any(key.startswith('radio2:') for key in reconciled.ground_target.resource_assignments)
