"""Safe raw-channel collision and bounded template regression tests."""
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from silverstar_flp.decoder_profiles import DecoderProfilePackage, DecoderProfileError
from silverstar_flp.decoder_profiles.semantics import _ChannelId_Format, _TemplateFields_Get
from silverstar_flp.core.analysis_source import ReplayResultStore
from silverstar_flp.ui.pages import data_explorer
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.registry import builtin_registry
from tests.test_decoder_profiles import (_CatalogDocument_Build, _SemanticsDocument_Build,
    _PackageFiles_Build, _Package_Write, _ImuPayload_Build, IMU_RECORD_TYPE, START_TIMESTAMP_US)
from tests.sslog_synthetic import SyntheticSslogBuilder


def test_legal_custom_recorded_names_never_resolve_recorded(tmp_path,monkeypatch):
    catalog=_CatalogDocument_Build()
    catalog['records'].append({'id':'0xEF','version':0,'name':'GNSS_RECOVERY','payload_size':1,
                               'fields':[{'name':'user_value','type':'u8'}]})
    semantics=_SemanticsDocument_Build()
    catalog['records'][0]['fields'][4]['name']='position_enu'
    semantics['record_views'][0]['partition_by']=['instance_id']
    semantics['record_views'][0]['columns']=['position_enu']
    semantics['record_views'][0]['validity']['masks']={'position_enu':1}
    semantics['raw_channel_id_templates']={'default':'{record}','IMU_NATIVE':'kf{instance_id}.recorded.navigation','partition_by':['instance_id']}
    files,_=_PackageFiles_Build(catalog_document=catalog,semantics_document=semantics)
    decoder,_=_Package_Write(tmp_path/'custom.ssdecoder',files=files)
    builder=SyntheticSslogBuilder()
    builder.Record_Add(IMU_RECORD_TYPE,_ImuPayload_Build(99,6,START_TIMESTAMP_US,(3.,4.,8.)),START_TIMESTAMP_US)
    builder.Record_Add(0xEF,b'\x01',START_TIMESTAMP_US+1)
    log=builder.File_Write(tmp_path/'custom.sslog')
    result=LogOpenCoordinator(builtin_registry()).Open(LogOpenRequest(log,decoder,allow_unverified_decoder=True))
    assert result.dataset.semantic_context is None
    assert 'kf6.recorded.navigation.position_enu' in result.dataset.series
    resolver=Mock(side_effect=AssertionError('unverified must never prime Recorded'))
    monkeypatch.setattr(data_explorer,'ChannelResolver',resolver)
    channels=data_explorer.ExplorerChannels_Prepare(result.dataset,ReplayResultStore())
    assert channels == dict(result.dataset.series)
    resolver.assert_not_called()


def test_exact_explorer_still_uses_resolver(monkeypatch):
    resolver=Mock(return_value=NS(ExplorerChannels_Get=lambda:{'exact':1}))
    monkeypatch.setattr(data_explorer,'ChannelResolver',resolver)
    dataset=NS(metadata={});store=ReplayResultStore()
    assert data_explorer.ExplorerChannels_Prepare(dataset,store)=={'exact':1}
    resolver.assert_called_once_with(dataset,store)


@pytest.mark.parametrize('width',[65,65536,2147483647])
def test_excessive_format_width_rejected_when_package_loaded(tmp_path,width):
    document=_SemanticsDocument_Build()
    document['raw_channel_id_templates']['default']='{record}:{source_descriptor_id:0'+str(width)+'d}:{instance_id}'
    files,_=_PackageFiles_Build(semantics_document=document)
    package,_=_Package_Write(tmp_path/'width.ssdecoder',files=files)
    # Never format an oversized template; rejection must happen on package load.
    with pytest.raises(DecoderProfileError,match='width'):
        DecoderProfilePackage.Load(package)


class NoFormat(str):
    def format_map(self,values):
        raise AssertionError('oversized expansion reached formatting')


@pytest.mark.parametrize('template,values',[
    ('{value:02147483647d}',{'value':1}),
    ('x'*1025,{}),
    ('{value:064d}'*17,{'value':1}),
    ('{value}',{'value':'x'*1025}),
    ('{}',{}),
])
def test_oversized_or_invalid_expansion_rejected_before_format(template,values):
    with pytest.raises(DecoderProfileError): _ChannelId_Format(NoFormat(template),values)


def test_boundary_width_and_id_lengths_are_usable():
    assert _ChannelId_Format('{value:064d}',{'value':1}) == '0'*63+'1'
    assert _ChannelId_Format('{value}',{'value':'x'*1024}) == 'x'*1024
    assert _TemplateFields_Get('{value:064X}') == {'value'}


def test_oversized_canonical_id_rejected(tmp_path):
    document=_SemanticsDocument_Build()
    # Generated semantic channel definitions are explicit and declarative.
    files,_=_PackageFiles_Build(semantics_document=document)
    package,_=_Package_Write(tmp_path/'base.ssdecoder',files=files)
    channel=DecoderProfilePackage.Load(package).semantics.records['IMU_NATIVE'].channels[0]
    from silverstar_flp.decoder_profiles.semantics import SemanticChannel
    definition={'id_template':'raw','value_field':channel.value_field,'canonical_id':'x'*1025}
    with pytest.raises(DecoderProfileError,match='canonical'):
        SemanticChannel.FromDocument(definition,record_name='IMU_NATIVE',partition_by=())
