"""Real generated decoder fixtures are explicit; all SSLOG records are synthetic."""
import hashlib
import os
from pathlib import Path
import numpy as np
import pytest
from tests.generated_decoder_pair import GeneratedPair_Build
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.plugins.api.algorithm import ReplayRequest, ReplayMode


def decoder_root(name):
    value=os.environ.get('SILVERSTAR_GENERATED_DECODER_'+name.upper())
    if value is None:
        pytest.skip('Explicit real generated decoder fixture required; no substitute package')
    return next(Path(value).rglob('*.ssdecoder'))


@pytest.mark.parametrize('name,algorithm',(
    ('existing','silverstar.algorithm.kf6'),('imported','silverstar.algorithm.kf6'),
    ('pure','silverstar.algorithm.pure_ins'),('eskf','silverstar.algorithm.estimator.eskf15')))
def test_real_generated_package_production_open_cache_roundtrip_and_replay(tmp_path,name,algorithm):
    decoder=decoder_root(name)
    log,package=GeneratedPair_Build(decoder,tmp_path)
    before={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in (log,decoder)}
    registry=builtin_registry()
    coordinator=LogOpenCoordinator(registry,cache=DecoderProfileCache(tmp_path/'cache'))
    opened=coordinator.Open(LogOpenRequest(log_path=log,decoder_package_path=decoder))
    reopened=coordinator.Open(LogOpenRequest(log_path=log,cache_reference=opened.cache_reference))
    assert reopened.descriptor==opened.descriptor
    assert reopened.package.generation_profile_hash_128==package.generation_profile_hash_128
    plugin=next(p for p in registry.algorithms if p.metadata.plugin_id==algorithm)
    result=plugin.run(opened.dataset,ReplayRequest(mode=ReplayMode.RECORDED_CONFIGURATION,input_source='corrected_imu'))
    assert result.channels
    assert all(np.all(np.isfinite(series.values)) for series in result.channels.values())
    assert all(hashlib.sha256(path.read_bytes()).hexdigest()==digest for path,digest in before.items())
    if algorithm=='silverstar.algorithm.pure_ins':
        assert result.diagnostics['firmware_build_parameters']=={'mechanization_aggregation':2}


@pytest.mark.parametrize('fault',('identity','recorded_aggregation'))
def test_real_generated_package_rejects_wrong_identity_and_recorded_configuration(tmp_path,fault):
    decoder=decoder_root('existing')
    log,_=GeneratedPair_Build(decoder,tmp_path,aggregation=1 if fault=='recorded_aggregation' else 2,wrong_identity=fault=='identity')
    coordinator=LogOpenCoordinator(builtin_registry(),cache=DecoderProfileCache(tmp_path/'cache'))
    expected='decoder_profile_hash_mismatch' if fault=='identity' else 'firmware_mechanization_configuration_mismatch'
    with pytest.raises(DecoderProfileError,match=expected):
        coordinator.Open(LogOpenRequest(log_path=log,decoder_package_path=decoder))
