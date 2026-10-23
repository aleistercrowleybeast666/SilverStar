import hashlib
import pytest
from silverstar_flp.decoder_profiles import DecoderProfileCache, DecoderPackageLimits
from silverstar_flp.decoder_profiles.package import DecoderProfilePackage
from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from silverstar_flp.log_open import LogOpenCoordinator,LogOpenRequest
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.core.replay_execution import Replay_Execute
from tests.sslog_synthetic import SyntheticSslogBuilder,START_TIMESTAMP_US
from tests.test_decoder_profiles import (_Package_Write,_PackageFiles_Build,_SemanticsDocument_Build,
    _CatalogDocument_Build,_DescriptorPayload_Build,_ImuPayload_Build,IMU_RECORD_TYPE,DESCRIPTOR_RECORD_TYPE)


def pair(tmp_path, *, descriptor=True, malformed=False):
    original,hashes=_Package_Write(tmp_path/'original.ssdecoder')
    semantics=_SemanticsDocument_Build();semantics['firmware_version']='user-edited-code'
    files,_=_PackageFiles_Build(semantics_document=semantics)
    edited,_=_Package_Write(tmp_path/'edited.ssdecoder',files=files)
    builder=SyntheticSslogBuilder()
    if descriptor:builder.Record_Add(DESCRIPTOR_RECORD_TYPE,_DescriptorPayload_Build(hashes),START_TIMESTAMP_US)
    builder.Record_Add(IMU_RECORD_TYPE,b'bad' if malformed else
        _ImuPayload_Build(1,0,START_TIMESTAMP_US+1,(1.,2.,3.)),START_TIMESTAMP_US+1)
    builder.Record_Add(0xEF,b'unknown user bytes',START_TIMESTAMP_US+2)
    return builder.File_Write(tmp_path/'raw.sslog'),edited


def test_explicit_mismatched_decoder_opens_unverified_without_source_writes(tmp_path):
    log,decoder=pair(tmp_path)
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (log,decoder)}
    coordinator=LogOpenCoordinator(builtin_registry(),cache=DecoderProfileCache(tmp_path/'cache'))
    with pytest.raises(RuntimeError,match='hash_mismatch'):
        coordinator.Open(LogOpenRequest(log,decoder))
    result=coordinator.Open(LogOpenRequest(log,decoder,allow_unverified_decoder=True))
    assert result.match_mode=='user_custom_unverified'
    assert result.cache_reference is None and not (tmp_path/'cache').exists()
    assert result.dataset.metadata['custom_decoder_unverified'] is True
    assert result.dataset.semantic_context is None
    assert result.dataset.Series_Get('IMU_NATIVE:1:0.accel_b_mps2') is not None
    assert result.dataset.Records_Get('UNKNOWN_0xEF_V0')[0].payload['raw_payload']==b'unknown user bytes'
    assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (log,decoder)}==before
    with pytest.raises(ValueError,match='replay_unverified'):
        Replay_Execute(None,result.dataset,None)


def test_missing_descriptor_and_length_mismatch_retains_bytes(tmp_path):
    log,decoder=pair(tmp_path,descriptor=False,malformed=True)
    result=LogOpenCoordinator(builtin_registry()).Open(LogOpenRequest(log,decoder,allow_unverified_decoder=True))
    record=result.dataset.Records_Get('IMU_NATIVE')[0]
    assert record.payload['raw_payload']==b'bad'
    assert result.dataset.diagnostics.decoder_failure_count==1
    assert result.dataset.metadata['parse_status']=='partial'


def test_custom_requires_explicit_pair_and_resource_limits(tmp_path):
    log,decoder=pair(tmp_path)
    with pytest.raises(ValueError,match='explicit_manual_pair'):
        LogOpenRequest(log,auto_find=True,allow_unverified_decoder=True)
    with pytest.raises(ValueError,match='explicit_manual_pair'):
        LogOpenRequest(log,allow_unverified_decoder=True)
    coordinator=LogOpenCoordinator(builtin_registry(),package_limits=DecoderPackageLimits(maximum_archive_bytes=1))
    with pytest.raises(DecoderProfileError,match='too_large'):
        coordinator.Open(LogOpenRequest(log,decoder,allow_unverified_decoder=True))


def test_custom_still_rejects_invalid_numeric_layout(tmp_path):
    catalog=_CatalogDocument_Build();catalog['records'][0]['fields'][0]['type']='python'
    files,_=_PackageFiles_Build(catalog_document=catalog)
    decoder,_=_Package_Write(tmp_path/'invalid.ssdecoder',files=files)
    log=SyntheticSslogBuilder().File_Write(tmp_path/'empty.sslog')
    with pytest.raises(DecoderProfileError):
        LogOpenCoordinator(builtin_registry()).Open(LogOpenRequest(log,decoder,allow_unverified_decoder=True))
