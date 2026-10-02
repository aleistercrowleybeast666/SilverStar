import copy
from types import SimpleNamespace
import pytest
from silverstar_flp.decoder_profiles.algorithm_parameters import FirmwareParameters_CheckPlugins, FirmwareMechanizationRecords_Validate
from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from silverstar_flp.plugins.algorithms.pure_ins.plugin import PureInsAlgorithmPlugin
from silverstar_flp.plugins.algorithms.pure_ins.mechanization import Mechanization_ConfigurationGet
from tests.parameter_fixtures import FirmwareSets_Build


def group(value=2):
    result = copy.deepcopy(next(g for g in FirmwareSets_Build() if g['component']=='silverstar.algorithm.ins.coning2_sculling2'))
    result['parameters'].append({'id':'mechanization_aggregation','value':value,'unit':'samples','representation':'value','storage_type':'int32','description':'Real IMU intervals per propagation'})
    return result


@pytest.mark.parametrize('value',(1,2))
def test_trusted_firmware_aggregation_is_not_a_replay_override(value):
    g=group(value)
    FirmwareParameters_CheckPlugins([g])
    plugin=PureInsAlgorithmPlugin()
    context=SimpleNamespace(FirmwareParameters_Get=lambda _: {p['id']:p for p in g['parameters']},FirmwareAlgorithm_IsMember=lambda _: True)
    dataset=SimpleNamespace(semantic_context=context,Records_Get=lambda _: (),header={})
    gravity=next(p['value'] for p in g['parameters'] if p['id']=='gravity_mps2')
    assert plugin.recorded_parameters(dataset)=={'gravity_mps2':gravity}
    assert plugin.FirmwareBuildParameters_Get(dataset)=={'mechanization_aggregation':value}
    assert Mechanization_ConfigurationGet(dataset)['subsample_count']==value
    with pytest.raises(ValueError,match='parameter_unknown'):
        plugin.metadata.Parameters_Validate({'mechanization_aggregation':value},complete=False)


@pytest.mark.parametrize('value',(0,3,-1,2.0,True))
def test_invalid_aggregation_rejected_by_trusted_contract(value):
    with pytest.raises(DecoderProfileError,match='firmware_parameter_contract_invalid'):
        FirmwareParameters_CheckPlugins([group(value)])


@pytest.mark.parametrize('field,value',(('id','unknown_aggregation'),('unit','Hz'),('representation','variance'),('storage_type','float32')))
def test_aggregation_metadata_does_not_bypass_unknown_or_type_contract(field,value):
    g=group();g['parameters'][-1][field]=value
    with pytest.raises(DecoderProfileError,match='firmware_parameter_contract_invalid'):
        FirmwareParameters_CheckPlugins([g])


def test_legacy_parameter_group_is_not_mutated_or_defaulted():
    g=group();g['parameters'].pop();before=copy.deepcopy(g)
    FirmwareParameters_CheckPlugins([g])
    assert g==before


def test_single_sample_corrected_imu_does_not_get_replayed_as_two_samples():
    from silverstar_flp.plugins.algorithms.eskf15.plugin import Eskf15AlgorithmPlugin
    from silverstar_flp.plugins.algorithms.eskf15.inputs import BodySteps_Build
    g=group(1)
    context=SimpleNamespace(FirmwareParameters_Get=lambda _: {p['id']:p for p in g['parameters']},FirmwareAlgorithm_IsMember=lambda _:False,FirmwareVersion_Get=lambda:'0.0.12')
    dataset=SimpleNamespace(semantic_context=context,Records_Get=lambda name: (SimpleNamespace(),) if name in ('IMU_CORRECTED','INITIAL_STATE') else (),header={})
    pure=PureInsAlgorithmPlugin().availability(dataset)
    assert not pure.available and 'mechanization_subsample_count=2' in pure.missing_inputs
    eskf=Eskf15AlgorithmPlugin().availability(dataset)
    assert not eskf.available and 'mechanization_subsample_count=2' in eskf.missing_inputs
    steps,failure,exact=BodySteps_Build(dataset,SimpleNamespace(start_timestamp_us=100))
    assert not steps and not exact and failure['reason']=='unsupported_mechanization_aggregation'


@pytest.mark.parametrize('name,field',(('SYSTEM_CONFIG','mechanization_subsample_count'),('INERTIAL_INCREMENT','subsample_count')))
def test_recorded_aggregation_cannot_disagree_with_exact_decoder(name,field):
    g=group(2)
    context=SimpleNamespace(FirmwareParameters_Get=lambda _: {p['id']:p for p in g['parameters']})
    dataset=SimpleNamespace(semantic_context=context,Records_Get=lambda record: (SimpleNamespace(payload={field:1}),) if record==name else ())
    with pytest.raises(DecoderProfileError,match='firmware_mechanization_configuration_mismatch'):
        FirmwareMechanizationRecords_Validate(dataset)


def test_header_aggregation_cannot_disagree_with_exact_decoder():
    g=group(2)
    context=SimpleNamespace(FirmwareParameters_Get=lambda _: {p['id']:p for p in g['parameters']})
    dataset=SimpleNamespace(semantic_context=context,header={'mechanization_subsample_count':1},Records_Get=lambda _: ())
    with pytest.raises(DecoderProfileError,match='firmware_mechanization_configuration_mismatch'):
        FirmwareMechanizationRecords_Validate(dataset)
