"""Interface/profile pairs must survive Qt object-identity comparisons."""
import pytest
from silverstar_fccg.project.folder_contract import ProjectRoot_Save
from test_gui_smoke import _Window_Create


@pytest.mark.parametrize("choice", range(4))
def test_bmi088_variant_survives_refresh_save_reopen_language(tmp_path, qapp, choice):
    window = _Window_Create(tmp_path, qapp)
    try:
        window._DeviceInstance_Change("imu0", "silverstar.device.imu.bmi088")
        qapp.processEvents()
        combo = window.devices_page.variant_combos["imu0"]
        assert combo.count() == 4
        pair = tuple(combo.itemData(choice))
        assert len(pair) == 2 and all(isinstance(value, str) for value in pair)
        # Also make the default variant an explicit selection, rather than the unchanged initial index.
        combo.setCurrentIndex((choice + 1) % combo.count())
        qapp.processEvents()
        window.devices_page.variant_combos["imu0"].setCurrentIndex(choice)
        qapp.processEvents()
        instance = window._model.DeviceInstance_Get("imu0")
        assert (instance.interface, instance.profile) == pair
        assert tuple(window.devices_page.variant_combos["imu0"].currentData()) == pair
        saved = window._model.Dictionary_Get()
        window._Project_Refresh()
        assert tuple(window.devices_page.variant_combos["imu0"].currentData()) == pair
        root = ProjectRoot_Save(window._model, tmp_path / "variant_project")
        window._Project_Open(root)
        qapp.processEvents()
        assert window._model.Dictionary_Get() == saved
        assert tuple(window.devices_page.variant_combos["imu0"].currentData()) == pair
        for language in ("en_US", "zh_CN"):
            window.Language_Apply(language)
            qapp.processEvents()
            assert window._model.Dictionary_Get() == saved
            assert tuple(window.devices_page.variant_combos["imu0"].currentData()) == pair
        assert sum(item.instance_id == "imu0" for item in window._model.device_instances) == 1
    finally:
        window.close()
        qapp.processEvents()
