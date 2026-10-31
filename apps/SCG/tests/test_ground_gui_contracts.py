"""Current GUI availability versus immutable stored/legacy target state."""
from dataclasses import replace
import json

from test_scg_ui_metadata_hotfix import window
from test_f103_ground_reference import _GroundF103Model_Get
from silverstar_fccg.project.air_link import GroundTargetIssues_Get


def test_removed_enable_request_does_not_change_configuration_or_lifecycle(window):
    window._model = _GroundF103Model_Get(window._service.catalog)
    window._Project_Refresh()
    before = json.dumps(window._model.Dictionary_Get(), sort_keys=True)
    state = window._project_state
    window._GroundTarget_Change('enabled', False)
    assert json.dumps(window._model.Dictionary_Get(), sort_keys=True) == before
    assert window._project_state == state
    assert not hasattr(window.ground_target_page, 'enabled')
    assert 'enabled' not in window._model.Dictionary_Get()['ground_target']
    assert window.ground_target_page.generate_button.isEnabled()


def test_refresh_preserves_unconfigured_target_and_reports_missing_configuration(window):
    window._model = window._service.ReferenceProject_Create('StoredDisabled')
    window._model.ground_target = replace(window._model.ground_target)
    before = json.dumps(window._model.Dictionary_Get(), sort_keys=True)
    window._Project_Refresh()
    window._GroundTarget_Change('enabled', False)
    window.Language_Apply('en_US')
    assert json.dumps(window._model.Dictionary_Get(), sort_keys=True) == before
    assert not hasattr(window.ground_target_page, 'enabled')
    assert not window.ground_target_page.generate_button.isEnabled()
    assert window.ground_target_page.generate_button.toolTip() == window._translator.Text_Get('status.ground_configuration_required')


def test_localized_status_retains_stable_polarity_diagnostics_across_languages(window):
    window._model = _GroundF103Model_Get(window._service.catalog)
    window._model.ground_target = replace(window._model.ground_target, activity_led_enabled=True,
        tx_led_resource='PLATFORM_GPIO_6', rx_led_resource='PLATFORM_GPIO_6',
        tx_led_active_high=True, rx_led_active_high=False)
    for language in ('zh_CN', 'en_US'):
        window.Language_Apply(language)
        window._Project_Refresh()
        issues = GroundTargetIssues_Get(window._model, window._service.catalog)
        assert {issue.code for issue in issues} == {'GROUND_LED_POLARITY_CONFLICT'}
        status = window.ground_target_page.status
        assert status.text() == window._translator.Text_Get('ground.issue.summary', count=1)
        assert 'GROUND_' not in status.text() and 'READY' not in status.text()
        assert all(f'{issue.code}: {issue.message}' in status.toolTip() for issue in issues)
