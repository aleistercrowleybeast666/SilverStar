"""Real catalog hardware identity and mutually exclusive platform ownership."""
from dataclasses import replace
import pytest
from silverstar_fccg.plugins.catalog import PluginCatalog, PluginCatalogError


F407 = 'silverstar.device.storage.sd_sdio_fatfs'
F1 = 'silverstar.device.storage.sd_sdio_fatfs_f1'


def test_real_platform_variants_keep_physical_facts_and_distinct_exact_parts(builtin_catalog):
    f4, f1 = (builtin_catalog.Component_Get(k) for k in (F407, F1))
    assert f4.physical_device == f1.physical_device
    f4_keys = builtin_catalog.PhysicalDeviceIdentityKeys_Get(f4)
    f1_keys = builtin_catalog.PhysicalDeviceIdentityKeys_Get(f1)
    assert {key[-1] for key in f4_keys} == {'STM32F407VET6'}
    assert {key[-1] for key in f1_keys} == {'STM32F103RET6', 'STM32F103RFT6'}
    assert set(f4_keys).isdisjoint(f1_keys)
    assert not PluginCatalog._PhysicalDeviceErrors_Get(builtin_catalog._components)


@pytest.mark.parametrize('change', ['same_platform', 'overlapping_other_platform',
                                    'optional_platform', 'missing_platform', 'broad_rule', 'wildcard_part'])
def test_duplicate_hardware_requires_proven_disjoint_domains(builtin_catalog, change):
    components = dict(builtin_catalog._components)
    f4, f1 = (components[k] for k in (F407, F1))
    family = next(d.component_id for d in f1.dependencies if components[d.component_id].component_type == 'mcu_family')
    if change == 'same_platform':
        components[F1] = replace(f1, dependencies=f4.dependencies)
    elif change == 'overlapping_other_platform':
        platform = components[family].platform
        rule = replace(platform.match_rules[0], exact_part='STM32F407VET6')
        components[family] = replace(components[family], platform=replace(platform, match_rules=(rule,)))
    elif change == 'optional_platform':
        components[F1] = replace(f1, dependencies=tuple(replace(d, optional=True) if d.component_id == family else d for d in f1.dependencies))
    elif change == 'missing_platform':
        components[F1] = replace(f1, dependencies=tuple(d for d in f1.dependencies if d.component_id != family))
    else:
        platform = components[family].platform
        components[family] = replace(components[family], platform=replace(platform,
            match_rules=(replace(platform.match_rules[0], exact_part='STM32F*' if change == 'wildcard_part' else ''),)))
    errors = PluginCatalog._PhysicalDeviceErrors_Get(components)
    assert errors, change
    assert any('Physical device' in e or 'Duplicate physical device' in e for e in errors)
    # Production Scan runs this guard before publishing its new catalog.
    catalog = PluginCatalog(builtin_catalog.builtin_root, builtin_catalog.installed_root)
    catalog._components = components
    if change in {'same_platform','overlapping_other_platform'}:
        keys = catalog.PhysicalDeviceIdentityKeys_Get(components[F1])
        assert ('Generic','SD/TF Card','STM32 SDIO','STM32F407VET6') in keys


def test_scan_refuses_overlap_before_publishing_catalog(builtin_catalog, monkeypatch):
    import silverstar_fccg.plugins.catalog as module
    load = module.PluginManifest_Load
    dependencies = builtin_catalog.Component_Get(F407).dependencies
    def overlapping_load(path, **options):
        manifest = load(path, **options)
        return replace(manifest, dependencies=dependencies) if manifest.component_id == F1 else manifest
    monkeypatch.setattr(module, 'PluginManifest_Load', overlapping_load)
    catalog = PluginCatalog(builtin_catalog.builtin_root, builtin_catalog.installed_root)
    with pytest.raises(PluginCatalogError, match='Duplicate physical device.*STM32F407VET6'):
        catalog.Scan()
    assert catalog._components == {}

