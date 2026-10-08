from dataclasses import replace

import pytest

from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.plugins.catalog import PluginCatalogError


def test_variant_view_reuses_only_exact_device_and_target_snapshot(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    first = builtin_catalog.ProjectView_Get(model)
    assert builtin_catalog.ProjectView_Get(model) is first
    model.device_instances.append(replace(model.device_instances[0], instance_id='imu_extra'))
    changed = builtin_catalog.ProjectView_Get(model)
    assert changed is not first
    assert changed.InstanceIdComponent_Get('imu_extra').component_id == model.device_instances[0].plugin
    model.device_instances[-1] = replace(model.device_instances[-1], interface='invalid')
    with pytest.raises(PluginCatalogError):
        builtin_catalog.ProjectView_Get(model)
    model.device_instances.pop()
    builtin_catalog.Scan()
    assert builtin_catalog.ProjectView_Get(model) is not first


def test_variant_manifest_change_invalidates_cached_view(builtin_catalog, monkeypatch, tmp_path):
    from silverstar_fccg.plugins import catalog as module
    model = ReferenceProject_Create(catalog=builtin_catalog)
    manifest = builtin_catalog.Component_Get(model.device_instances[0].plugin)
    assert manifest.device_variants
    copied = tmp_path / 'plugin.json'
    copied.write_bytes(manifest.manifest_path.read_bytes())
    monkeypatch.setitem(builtin_catalog._components, manifest.component_id,
                       replace(manifest, manifest_path=copied))
    original = module.PluginManifest_VariantResolve
    monkeypatch.setattr(module, 'PluginManifest_VariantResolve',
                        lambda item, variant: original(manifest if item.manifest_path == copied else item, variant))
    first = builtin_catalog.ProjectView_Get(model)
    assert builtin_catalog.ProjectView_Get(model) is first
    copied.write_bytes(copied.read_bytes() + b'\n')
    assert builtin_catalog.ProjectView_Get(model) is not first


def test_project_view_working_set_is_bounded(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    first = builtin_catalog.ProjectView_Get(model)
    initial = model.device_instances[0]
    for index in range(9):
        model.device_instances[0] = replace(initial, instance_id='imu_' + str(index))
        builtin_catalog.ProjectView_Get(model)
    assert len(builtin_catalog._project_views) == 8
    model.device_instances[0] = initial
    assert builtin_catalog.ProjectView_Get(model) is not first
