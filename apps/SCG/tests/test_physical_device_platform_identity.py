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
                                    'optional_platform', 'missing_platform', 'broad_rule', 'wildcard_part', 'empty_token'])
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
            match_rules=(replace(platform.match_rules[0], exact_part={
                'wildcard_part':'STM32F*', 'empty_token':' -- ', 'broad_rule':''}[change]),)))
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


@pytest.mark.parametrize('spelling', ['stm32f407vet6', 'STM32-F407VET6', 'STM32 F407VET6'])
def test_equivalent_matched_parts_collide_before_scan_publication(builtin_catalog, monkeypatch, spelling):
    import silverstar_fccg.plugins.catalog as module
    from silverstar_fccg.hardware.platform import DetectedMcuFacts, _RuleCandidate_Get
    components = dict(builtin_catalog._components)
    f4, f1 = (components[k] for k in (F407, F1))
    f4_platform = next(components[d.component_id] for d in f4.dependencies
                       if components[d.component_id].component_type == 'mcu')
    f1_platform = next(components[d.component_id] for d in f1.dependencies
                       if components[d.component_id].component_type == 'mcu_family')
    rule = f4_platform.platform.match_rules[0]
    variant_rule = replace(rule, exact_part=spelling)
    variant = replace(f1_platform, platform=replace(f1_platform.platform,
                      match_rules=(variant_rule,)))
    components[variant.component_id] = variant
    facts = DetectedMcuFacts(rule.vendor, 'STM32F407VET6', 'STM32F4', 'LQFP100',
                             'Cortex-M4', f4_platform.platform.provider)
    assert _RuleCandidate_Get(f4_platform, rule, facts) is not None
    assert _RuleCandidate_Get(variant, variant_rule, facts) is not None
    catalog = PluginCatalog(builtin_catalog.builtin_root, builtin_catalog.installed_root)
    catalog._components = components
    assert set(catalog.PhysicalDeviceIdentityKeys_Get(f4)) & set(catalog.PhysicalDeviceIdentityKeys_Get(f1))
    load = module.PluginManifest_Load
    monkeypatch.setattr(module, 'PluginManifest_Load', lambda path, **options:
                        components[load(path, **options).component_id])
    fresh = PluginCatalog(builtin_catalog.builtin_root, builtin_catalog.installed_root)
    with pytest.raises(PluginCatalogError, match='Duplicate physical device.*STM32F407VET6'):
        fresh.Scan()
    assert fresh._components == {}


def test_distinct_normalized_part_keeps_real_platform_variant_domain(builtin_catalog, monkeypatch):
    import silverstar_fccg.plugins.catalog as module
    from silverstar_fccg.hardware.platform import DetectedMcuFacts, _RuleCandidate_Get
    components = dict(builtin_catalog._components)
    f1 = components[F1]
    platform = next(components[d.component_id] for d in f1.dependencies
                    if components[d.component_id].component_type == 'mcu_family')
    original_rule = next(rule for rule in platform.platform.match_rules if rule.exact_part == 'STM32F103RET6')
    rule = replace(original_rule, exact_part='stm32 f103re-t6')
    variant = replace(platform, platform=replace(platform.platform, match_rules=(rule,)))
    components[variant.component_id] = variant
    facts = DetectedMcuFacts(rule.vendor, 'STM32F103RET6', 'STM32F1', 'LQFP64',
                             'Cortex-M3', platform.platform.provider)
    assert _RuleCandidate_Get(variant, rule, facts) is not None
    load = module.PluginManifest_Load
    monkeypatch.setattr(module, 'PluginManifest_Load', lambda path, **options:
                        components[load(path, **options).component_id])
    fresh = PluginCatalog(builtin_catalog.builtin_root, builtin_catalog.installed_root)
    fresh.Scan()
    assert {key[-1] for key in fresh.PhysicalDeviceIdentityKeys_Get(f1)} == {'STM32F103RET6'}
    assert set(fresh.PhysicalDeviceIdentityKeys_Get(f1)).isdisjoint(
        fresh.PhysicalDeviceIdentityKeys_Get(components[F407]))

