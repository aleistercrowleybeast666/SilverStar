"""Slot/call-site proof logic. Real Debug/Release Arm runs are separate evidence."""
import pytest
from test_stack_budget import stacks


def SitesFixture_Create(config):
    callers = ('SystemDeviceStartup_ProbeTick','SystemDeviceStartup_ReadTick',
               'SystemDeviceStartup_ApplyTick','SystemDeviceStartup_Tick')
    shape = ([],[],[],[4,0,8,12,16,20,24]) if config == 'Release' else ([0,4],[8],[12],[16,20,24])
    instructions = {f'Op{i}':[('bx','lr')] for i in range(7)}
    edges = {caller:set() for caller in callers}
    indirect = set()
    for caller, slots in zip(callers,shape):
        instructions[caller] = []
        for slot in slots:
            instructions[caller] += [('ldr',f'r3, [r2, #{slot}]'),('blx','r3')]
        if slots:
            indirect.add(caller)
    return instructions,edges,indirect,[('immutable-fixture',[f'Op{i}' for i in range(7)])]


@pytest.mark.parametrize('config',['Debug','Release'])
def test_seven_sites_resolve_only_their_real_operation_slot(config):
    args = SitesFixture_Create(config)
    result = stacks.StartupCallbackSites_Resolve(*args,config)
    assert len(result) == 7
    assert sorted(row['slot_offset'] for row in result) == list(range(0,28,4))
    assert not args[2]
    if config == 'Debug':
        assert args[1]['SystemDeviceStartup_ReadTick'] == {'Op2'}


@pytest.mark.parametrize('config',['Debug','Release'])
@pytest.mark.parametrize('mutation',['extra_site','wrong_slot','missing_target','unknown_caller','missing_marker'])
def test_startup_compiler_shape_changes_reject(config,mutation):
    args = SitesFixture_Create(config)
    instructions,_,indirect,_ = args
    caller = 'SystemDeviceStartup_Tick'
    if mutation == 'extra_site':
        instructions[caller] += [('ldr','r3, [r2, #4]'),('blx','r3')]
    elif mutation == 'wrong_slot':
        instructions[caller][0] = ('ldr','r3, [r2, #24]')
    elif mutation == 'missing_target':
        del instructions['Op6']
    elif mutation == 'unknown_caller':
        indirect.add('SystemDeviceStartup_Unknown')
    else:
        indirect.remove(caller)
    with pytest.raises(ValueError):
        stacks.StartupCallbackSites_Resolve(*args,config)
