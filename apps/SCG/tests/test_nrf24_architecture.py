"""Removed NRF generators cannot be reached through a native or Ground recipe."""
from pathlib import Path


def test_only_supported_ground_backend_owners_are_registered(builtin_catalog):
    core = builtin_catalog.Component_Get('silverstar.core.ground.0_1_0')
    assert set(core.metadata['ground_radio_backends']) == {'sx128x', 'sx127x'}
    root = Path(__file__).resolve().parents[1]
    assert not (root / 'plugins/builtin/silverstar_device_telemetry_nrf24l01p/plugin.json').exists()
    for name in ('nrf24_checkpoint.py', 'nrf24_validate.py'):
        assert not (root / 'tools' / name).exists()
