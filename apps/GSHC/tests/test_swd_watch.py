"""Compile real ARM ELF types; fake memory only, never open a probe."""
import json
import shutil
import struct
import subprocess
from dataclasses import replace

import pytest
from transport.swd_firmware import Firmware_Import, DiagnosticResult
from transport.swd_session import SwdSession, SwdResult as R
from test_swd_firmware import arm_elf, ImageMemory
from test_swd_session import PROBE, tick
from test_swd_ui import swd_panel, wait_for
from test_probe_ui import panel  # noqa: F401 -- dependency of the imported Qt fixture


@pytest.fixture(scope='module')
def watch_elf(arm_elf):
    root = arm_elf.parent
    source = root/'watch.c'
    source.write_text('''
typedef struct { float value; unsigned long long ticks; } Inner;
volatile struct { int count; Inner inner; _Bool ready; int *pointer; int array[2]; unsigned bits:3; } global_state = {7,{1.25f,42},1,0,{0},0};
static volatile double precision = 2.5;
static volatile int duplicate = 4;
volatile int global_scalar = -12;
enum Mode { Mode_Failed = -3, Mode_Ready = 2 };
volatile enum Mode mode = Mode_Failed;
__attribute__((used)) int Local(void) { volatile int stack_local=3; static volatile int local_static=5; (void)precision; return stack_local+local_static+duplicate; }
''',encoding='utf-8')
    (root/'other.c').write_text('static volatile int duplicate=8; __attribute__((used)) int Other(void) { return duplicate; }',encoding='utf-8')
    command=[shutil.which('arm-none-eabi-gcc'),'-mcpu=cortex-m4','-mthumb','-g','-gdwarf-4','-O0','-nostdlib',
             '-Wl,--build-id=none','-Tfixture.ld','watch.c','other.c','start.c','-o','watch.elf']
    completed=subprocess.run(command,cwd=root,capture_output=True,text=True,timeout=30)
    (root/'watch_compile.json').write_text(json.dumps(dict(command=command,exit=completed.returncode,stdout=completed.stdout,stderr=completed.stderr)),encoding='utf-8')
    assert completed.returncode==0,completed.stderr
    return root/'watch.elf'


def load_watch(path):
    imported=Firmware_Import([path],target='STM32F407VET6')
    assert imported.result==DiagnosticResult.Ok,imported.detail
    return imported.firmware


def connected(path):
    firmware=load_watch(path)
    backend=ImageMemory(firmware)
    session=SwdSession(firmware=firmware,_backend_factory=lambda _:backend)
    assert session.Swd_Attach(PROBE).result==R.Ok
    tick(session)
    assert session.Swd_VerifyFirmware().result==R.Ok
    tick(session)
    return session,backend


def test_catalog_global_static_nested_and_explicit_unsupported(watch_elf):
    firmware=load_watch(watch_elf)
    fields={item.id:item for item in firmware.watches}
    assert fields['watch.c::global_state.inner.value'].type_name=='float'
    assert fields['watch.c::global_state.inner.ticks'].size==8
    assert fields['watch.c::precision'].size==8
    assert fields['watch.c::global_scalar'].encoding==5
    assert fields['watch.c::mode'].encoding==5
    assert fields['watch.c::duplicate'].address!=fields['other.c::duplicate'].address
    assert not any('stack_local' in key or 'local_static' in key for key in fields)
    for key in ('pointer','array','bits'): assert fields['watch.c::global_state.'+key].unavailable


def test_watch_reads_only_selected_ram_no_mmio_and_decodes_types(watch_elf):
    session,backend=connected(watch_elf)
    ids=['watch.c::global_state.inner.value','watch.c::global_scalar','watch.c::precision','watch.c::global_state.ready']
    values=[struct.pack('<f',1.25),struct.pack('<i',-17),struct.pack('<d',2.5),b'\x01']
    catalog={item.id:item for item in backend.firmware.watches}
    for identifier,data in zip(ids,values):
        backend.memory.update({catalog[identifier].address+i:byte for i,byte in enumerate(data)})
    backend.reads.clear()
    try:
        reply=session.Swd_ReadWatches(ids)
        assert reply.result==R.Ok
        assert [row['value'] for row in reply.watches]==[1.25,-17,2.5,True]
        assert backend.reads==[(catalog[key].address,catalog[key].size) for key in ids]
        assert reply.firmware_sha256==backend.firmware.sha256
        assert reply.watch_identity['probe_identity']==PROBE.identity
        assert reply.watch_identity['firmware_status']=='matched'
        assert all(row['mcu_sample_age_ms'] is None and row['captured_utc'] and row['consistency']=='non_atomic_live_read' for row in reply.watches)
        assert 'not_read' in reply.core_observation
    finally: assert session.Swd_Detach().result==R.Ok
    assert session.Swd_ReadWatches(ids).result==R.FirmwareMismatch


def test_member_bounds_reject_malformed_dwarf(watch_elf):
    from silverstar_diagnostics.elf import ElfReader
    from silverstar_diagnostics.targets import Target_Get
    from silverstar_diagnostics.watch import Catalog_Build
    reader=ElfReader(watch_elf,Target_Get('STM32F407VET6'))
    dtype=reader._Type(reader.variables['global_state'][0])
    member=next(d for d in dtype.iter_children() if d.attributes.get('DW_AT_name').value==b'inner')
    location=member.attributes['DW_AT_data_member_location']
    member.attributes['DW_AT_data_member_location']=location._replace(value=65535)
    catalog={field.id:field for field in Catalog_Build(reader)}
    assert catalog['watch.c::global_state.inner'].unavailable
    assert not any(key.startswith('watch.c::global_state.inner.') for key in catalog)


@pytest.mark.parametrize('address,size',[(0x40000000,4),(0x2001ffff,4),(0x20000000,16)])
def test_runtime_rechecks_catalog_memory_bounds(watch_elf,address,size):
    session,backend=connected(watch_elf)
    field=next(f for f in backend.firmware.watches if f.id=='watch.c::global_scalar')
    session._firmware=replace(backend.firmware,watches=(replace(field,address=address,size=size),))
    backend.reads.clear()
    assert session.Swd_ReadWatches([field.id]).result==R.InvalidRequest
    assert backend.reads==[] and backend.closed==1


def test_one_second_watch_limit_reset_invalidation_and_short_read(watch_elf):
    session,backend=connected(watch_elf)
    key='watch.c::global_scalar'
    assert session.Swd_ReadWatches([key]).result==R.Ok
    session._last_sample-=.3
    backend.reads.clear()
    assert session.Swd_ReadWatches([key]).result==R.RateLimited and not backend.reads
    tick(session)
    backend.words[0xE000EDF0]=1<<25
    assert session.Swd_Inspect([key]).result==R.FirmwareMismatch
    assert all(address>=0xE0000000 for address,_ in backend.reads)
    backend.reads.clear()
    assert session.Swd_ReadWatches([key]).result==R.FirmwareMismatch and not backend.reads
    session.Swd_Detach()
    session,backend=connected(watch_elf)
    backend.read=lambda *_:b''
    assert session.Swd_ReadWatches([key]).result==R.TransportError and backend.closed==1


def test_summary_unknowns_and_watch_cli_json_identity(watch_elf,monkeypatch,capsys):
    from services.swd_summary import Summary_Build
    from swd_cli import SwdCli_Run
    from transport.probe_inventory import ProbeInventory, ProbeInventoryResult
    assert all(row['state']=='UNKNOWN' and not row['values'] and row['mcu_sample_age_ms'] is None
               for row in Summary_Build((),False))
    sessions=[]
    def factory(**kwargs):
        firmware=kwargs['firmware']
        session=SwdSession(**kwargs,_backend_factory=lambda _:ImageMemory(firmware))
        sessions.append(session)
        return session
    monkeypatch.setattr('swd_cli.time.sleep',lambda _:tick(sessions[0]))
    result=SwdCli_Run(['watch','--probe',PROBE.identity,'--elf',str(watch_elf),
        '--target','STM32F407VET6','--watch','watch.c::global_scalar'],
        _inventory=lambda _:ProbeInventory(ProbeInventoryResult.Ready,(PROBE,)),_session=factory)
    value=json.loads(capsys.readouterr().out)
    assert result==0 and value['format']=='silverstar.swd-snapshot'
    assert value['watch_identity']['probe_identity']==PROBE.identity and value['release']['result']=='ok'
    assert value['watches'][0]['raw_hex'] and value['watches'][0]['mcu_sample_age_ms'] is None
    assert value['snapshot'] is None and 'not_read' in value['core_observation']


def test_summary_labels_stale_and_never_implies_mcu_age():
    import time
    from services.swd_summary import Summary_Build
    rows=[dict(id='task.preparation',state='OBSERVED',fields=dict(ready=1),
          received_ns=time.monotonic_ns()-4_000_000_000,reason='ram_observation_not_readiness',
          consistency='non_atomic_live_read')]
    value=Summary_Build(rows,True)[0]
    assert value['state']=='STALE' and value['values']==dict(ready=1)
    assert value['host_age_ms']>=4000 and value['mcu_sample_age_ms'] is None
    assert not Summary_Build(rows,False)[0]['values']


def test_paused_worker_performs_no_samples_and_expires(monkeypatch):
    from ui.swd_connection import SwdWorker
    from transport.swd_session import SwdReply
    calls=[]
    class Backend:
        def __init__(self,**kwargs): pass
        def Swd_Attach(self,_): calls.append('attach');return SwdReply(R.Ok)
        def Swd_Snapshot(self): raise AssertionError('Paused worker sampled target')
        def Swd_Detach(self): calls.append('detach');return SwdReply(R.Ok)
    class Wakeup:
        def wait(self,_): return False
    clock=iter([0,1,601])
    monkeypatch.setattr('ui.swd_connection.time.monotonic',lambda:next(clock))
    worker=SwdWorker(PROBE,Backend)
    worker.cancel=Wakeup()
    worker.set_selection((),1,True,1)
    replies=[];worker.update.connect(replies.append)
    worker.run()
    assert calls==['attach','detach'] and replies[-1].result==R.BudgetExceeded


@pytest.mark.parametrize('ids',[['0x40000000'],['watch.c::global_state.pointer'],['watch.c::global_scalar']*17,['watch.c::global_scalar']*2,[True]])
def test_invalid_selection_no_target_access(watch_elf,ids):
    session,backend=connected(watch_elf)
    backend.reads.clear()
    try:
        assert session.Swd_ReadWatches(ids).result==R.InvalidRequest
        assert backend.reads==[]
    finally: session.Swd_Detach()


def test_unknown_match_budget_rate_nonfinite_and_cancel(watch_elf):
    firmware=load_watch(watch_elf)
    assert SwdSession(firmware=firmware).Swd_ReadWatches(['watch.c::global_scalar']).result==R.FirmwareMismatch
    session,backend=connected(watch_elf)
    key='watch.c::global_state.inner.value'
    field=next(f for f in firmware.watches if f.id==key)
    backend.memory.update({field.address+i:value for i,value in enumerate(struct.pack('<f',float('nan')))})
    reply=session.Swd_ReadWatches([key])
    assert reply.watches[0]['state']=='NONFINITE' and reply.watches[0]['value']=='nan'
    json.dumps(reply.watches,allow_nan=False)
    assert session.Swd_ReadWatches([key]).result==R.RateLimited
    tick(session);session._bytes=session.MAX_BYTES-1
    assert session.Swd_ReadWatches([key]).result==R.BudgetExceeded and backend.closed==1
    session,backend=connected(watch_elf)
    session.cancel.set()
    assert session.Swd_ReadWatches([key]).result==R.Cancelled and backend.closed==1


def test_catalog_without_dwarf_and_cli_offline(watch_elf,tmp_path,capsys):
    from swd_cli import SwdCli_Run
    def forbidden(*args): raise AssertionError('Offline catalog must not enumerate/attach')
    assert SwdCli_Run(['catalog','--elf',str(watch_elf),'--target','STM32F407VET6'],_inventory=forbidden)==0
    document=json.loads(capsys.readouterr().out)
    assert document['firmware_status']=='unmatched' and document['entries']
    target=tmp_path/'stripped.elf'
    completed=subprocess.run([shutil.which('arm-none-eabi-objcopy'),'--strip-debug',str(watch_elf),str(target)],capture_output=True)
    assert completed.returncode==0
    assert not load_watch(target).watches


def test_gui_add_read_remove_pause_disconnect(watch_elf,swd_panel):
    window,probes,create=swd_panel
    backends=[]
    def factory(**kwargs):
        backend=ImageMemory(kwargs['firmware']);backends.append(backend)
        return SwdSession(**kwargs,_backend_factory=lambda _:backend)
    manager=create(factory)
    window.maintenance_page.swd_target.setCurrentText('STM32F407VETx')
    assert manager.import_files([watch_elf])
    wait_for(lambda:manager.import_worker is None)
    panel=window.maintenance_page.swd_watch
    from PySide6.QtWidgets import QScroller
    assert all(QScroller.hasScroller(view.viewport()) for view in
               (panel.table,panel.catalog.view(),panel.interval.view()))
    panel.search.setText('global_scalar')
    assert panel.catalog.count()==1 and panel.add.isEnabled()
    panel.add.click()
    assert panel.selected==['watch.c::global_scalar'] and not panel.add.isEnabled()
    assert manager.attach()
    wait_for(lambda:bool(manager.watch_rows))
    assert panel.table.topLevelItemCount()==1
    panel.pause.setChecked(True)
    assert not panel.rows
    panel.table.topLevelItem(0).setSelected(True)
    panel.remove.click()
    assert not panel.selected and not panel.rows
    manager.detach();wait_for(lambda:manager.worker is None)
    assert not manager.watch_rows and backends[0].closed==1
