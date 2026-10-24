"""Tests execute the compiled C DLL. No Python capture state machine is used."""
import ctypes as c
import hashlib
import json
import math
import random
import struct

import pytest

from c_binding import Library,Sample,Snapshot,Status,snapshot
from services.installation_calibration_backend import (InstallationBinding_Parse,InstallationCapabilities,
    InstallationOutcome,InstallationResult)
from services.installation_calibration_contract import InstallationContract_Load
from services.installation_calibration_capture_contract import InfoSnapshot_Decode
from services.installation_calibration_protocol import PairAssembler,SamplePart_Decode


@pytest.fixture
def lib():
    library=Library();library.TestReset();yield library
    library.TestReset()  # host-only fixture reset; not a target recovery mechanism


def binding(lib,payload=None):
    caps=InstallationCapabilities(InstallationOutcome(InstallationResult.Ok,"C_FIXTURE"),3,3,4096,True)
    return InstallationBinding_Parse(payload or lib.info(),"B-"+bytes(lib.status().binding).hex()[:30],caps)


def test_c_default_is_disabled_and_abi_is_measured(lib):
    config=snapshot()
    assert c.sizeof(Sample)==88 and c.sizeof(Snapshot)==528
    assert lib.Configure(c.byref(config))==1
    assert lib.status().state_bytes==1960 and lib.status().state==0


@pytest.mark.parametrize("first,second",[(a,b) for a in range(1,11) for b in range(1,11)])
def test_actual_c_resource_gate_covers_every_ordered_entrant_pair(lib,first,second):
    lib.configure();token=c.c_uint32();other=c.c_uint32(0xAAAAAAAA)
    assert lib.ResourceClaim(first,c.byref(token))==0
    assert lib.ResourceClaim(second,c.byref(other))==3 and other.value==0xAAAAAAAA
    assert lib.ResourceRelease(first,token.value+1)==4
    assert lib.ResourceRelease(first,token.value)==0
    assert lib.ResourceClaim(second,c.byref(other))==0 and other.value!=token.value
    assert lib.ResourceRelease(first,token.value)==4


def test_actual_install_claim_cannot_be_released_around_live_capture(lib):
    lib.configure();lib.begin();lib.face();state=lib.status()
    assert state.resource_owner==1 and lib.ResourceRelease(1,state.resource_token)==3
    assert lib.Revoke()==10 and lib.SourcePush(0,c.byref(lib.sample(0,0,0)),300)==4
    assert lib.ProducerStopped()==12 and lib.Release()==0
    assert lib.status().state==0


def test_periodic_ticks_do_not_refresh_a_disconnected_c_session(lib):
    lib.configure();lib.begin()
    assert lib.RequestTouch(lib.sid,99,10000000)==4
    assert lib.Poll(29999999)==10 and lib.Poll(30000000)==10
    assert lib.status().state==6 and lib.status().reason==9
    assert lib.ProducerStopped()==12 and lib.Release()==0


def test_revoke_invalidates_an_idle_snapshot_without_preempting_another_owner(lib):
    lib.configure();token=c.c_uint32();assert lib.ResourceClaim(2,c.byref(token))==0
    assert lib.Revoke()==0 and lib.status().resource_owner==2
    assert lib.ResourceRelease(2,token.value)==0
    assert lib.Begin(lib.sid,1,(c.c_uint8*15).from_buffer_copy(bytes(lib.status().binding[:15])),0)==1


def test_rid_exhaustion_retains_a_cancel_slot(lib):
    lib.configure();wrong_limit=(c.c_uint8*15).from_buffer_copy(bytes(lib.status().binding[:15]))
    assert lib.Begin(lib.sid,2**32-2,wrong_limit,0)==2
    lib.begin();assert lib.face(rid=2**32-2)==2
    assert lib.Cancel(lib.sid,2**32-1,0)==10
    assert lib.ProducerStopped()==12


def test_late_poll_cannot_resurrect_an_expired_lease(lib):
    lib.configure();lib.begin()
    assert lib.RequestTouch(lib.sid,1,30000000)==9
    assert lib.status().state==6
    assert lib.ProducerStopped()==12 and lib.Release()==0
    assert lib.Cancel(lib.sid,3,30000000)==4


def test_a_cached_pre_face_sample_cannot_enter_a_new_c_window(lib):
    lib.configure();lib.begin();assert lib.face(now=100000)==10
    assert lib.SourcePush(0,c.byref(lib.sample(0,0,0)),100300)==8
    assert lib.status().train_count==0


def test_complete_c_info_is_canonical_bound_and_immutable(lib):
    payload=lib.configure();status=lib.status()
    data=InfoSnapshot_Decode(payload,InstallationContract_Load().Read()["info_snapshot"])
    declared=data.pop("binding_digest")
    assert hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()==declared
    assert declared==bytes(status.binding).hex() and hashlib.sha256(payload).digest()==bytes(status.info_sha256)
    assert len(payload)==status.info_bytes and binding(lib,payload).capture_qualification.reason=="DECLARED_ONLY_NOT_HARDWARE_VERIFIED"
    lib.config.accel_bias[0]=999.;lib.config.sources[0].epoch+=1
    assert lib.info()==payload
    assert lib.page(0)==lib.page(0)
    page=(c.c_uint8*48)(*([0xAB]*48));length=c.c_uint16(0x1234);next_cursor=c.c_uint16();end=c.c_uint8()
    assert lib.InfoRead(1,page,c.byref(length),c.byref(next_cursor),c.byref(end))==2
    assert bytes(page)==b"\xab"*48 and length.value==0x1234


@pytest.mark.parametrize("size",(0,3,55,56,63,64,65,511,8192))
def test_actual_c_sha_matches_hashlib(lib,size):
    payload=bytes(i%251 for i in range(size));source=(c.c_uint8*max(1,size)).from_buffer_copy(payload or b"\0");result=(c.c_uint8*32)()
    assert lib.Hash(source,size,result)==0 and bytes(result)==hashlib.sha256(payload).digest()


def test_ryu_wrapper_matches_python_json_for_binary64_vectors(lib):
    rng=random.Random(20261019)
    values=[0.,-0.,1.,-1.,1e-4,1e-5,1e15,1e16,1e20,1e-300,5e-324,1.7976931348623157e308]
    for _ in range(5000):
        value=struct.unpack('<d',rng.getrandbits(64).to_bytes(8,'little'))[0]
        if math.isfinite(value):values.append(value)
    for value in values:
        output=c.create_string_buffer(32);length=c.c_uint16()
        assert lib.Number(value,output,c.byref(length))==0
        assert output.raw[:length.value]==json.dumps(value,allow_nan=False).encode(),repr(value)
    for value in (float('nan'),float('inf'),float('-inf')):
        assert lib.Number(value,c.create_string_buffer(32),c.byref(c.c_uint16()))==2


def test_begin_binding_session_and_face_retry_are_real_c_transactions(lib):
    lib.configure();lib.begin()
    current=lib.status();wrong=(c.c_uint8*15)(*([0xAB]*15))
    assert lib.Begin(lib.sid,1,wrong,0)==5
    assert lib.status().next_pair==current.next_pair
    assert lib.face()==10 and lib.face()==10
    assert lib.Face(lib.sid,2,0,1,1,1,0)==5
    assert lib.Face(lib.sid,3,0,1,0,1,0)==3
    assert lib.status().train_count==0


def test_real_c_train_holdout_stream_matches_existing_format1_assembler(lib):
    info=lib.configure();b=binding(lib,info);lib.begin();assert lib.face()==10
    assembler=PairAssembler('1'*32,b.binding,b.boot,{s.role:s for s in b.sources},quality_policy=b.capture_policy)
    pairs=[]
    for index in range(6):
        assert lib.feed(index,index*200000)==(0,0)
        for line in lib.drain():
            result=assembler.Feed(line[:-2],index*1000+len(pairs)+1)
            if result:pairs.append(result)
    assert [pair.tag.split for pair in pairs]==['TRAIN']*3+['HOLDOUT']*3
    assert pairs[2].imu.sequence<pairs[3].imu.sequence and pairs[2].imu.sample_us<pairs[3].imu.sample_us
    assert all(pair.tag.pose=='P00000002' for pair in pairs)
    assert lib.status().state==5 and lib.status().train_count==lib.status().holdout_count==3
    assert lib.face()==11  # retry returns the completed result without recapture


def test_second_part_rejection_retries_exact_c_bytes_without_duplicate_first_part(lib):
    lib.configure();lib.begin();lib.face();assert lib.feed(0,0)==(0,0)
    result,first=lib.peek();assert result==0 and b' IMU ' in first and lib.EventCommit(1)==0
    result,second=lib.peek();assert result==0 and b' MAG ' in second and lib.EventCommit(0)==0
    result,retry=lib.peek();assert result==0 and retry==second
    assert lib.EventCommit(1)==0 and lib.peek()[0]==10


def test_third_pair_fails_the_actual_two_slot_queue(lib):
    lib.configure();lib.begin();lib.face()
    assert lib.feed(0,0)==(0,0) and lib.feed(1,200000)==(0,0)
    assert lib.feed(2,400000)==(0,6)
    assert lib.status().state==8 and lib.peek()[0]!=0


def test_native_gap_on_an_unselected_frame_is_not_hidden(lib):
    lib.configure(snapshot(stride=40));lib.begin();lib.face()
    assert lib.feed(0,0)==(0,0);lib.drain()
    assert lib.feed(1,5000)==(0,0)
    assert lib.SourcePush(0,c.byref(lib.sample(0,3,15000)),15300)==7
    assert lib.status().state==8


def test_fixed_native_stride_is_value_independent_and_survives_u32_wrap(lib):
    selected=[]
    for physical in ((9.,1.,2.,3.,4.,5.),(-999.,999.,0.,0.,0.,0.)):
        lib.configure(snapshot(stride=40,phase=7));lib.begin();lib.face();ids=[]
        for index in range(120):
            for role in range(2):
                item=lib.sample(role,(2**32-50+index)%2**32,index*5000)
                if role==0:item.physical[:]=physical
                assert lib.SourcePush(role,c.byref(item),index*5000+300)==0
            for line in lib.drain():
                if b' IMU ' in line:
                    body=bytes.fromhex(dict(word.split(b'=',1) for word in line.split()[3:])[b'data'].decode())
                    ids.append(struct.unpack_from('<I',body)[0])
        selected.append(ids)
    assert selected[0]==selected[1]==[(2**32-50+i)%2**32 for i in (7,47,87)]


@pytest.mark.parametrize("fault",('epoch','reverse_time','uncertainty','quality'))
def test_real_c_source_fault_paths(lib,fault):
    lib.configure();lib.begin();lib.face();lib.feed(0,1000);lib.drain()
    item=lib.sample(0,1,201000)
    if fault=='epoch':item.epoch+=1
    elif fault=='reverse_time':item.sample_us=0
    elif fault=='uncertainty':item.uncertainty_us=0
    else:item.flags|=1
    assert lib.SourcePush(0,c.byref(item),201300)==8
    assert lib.status().state==8


def test_missing_first_native_frame_and_selected_cadence_are_bounded(lib):
    lib.configure();lib.begin();lib.face();assert lib.Poll(250000)==9
    lib.configure(snapshot(stride=100));lib.begin();lib.face()
    for index in range(43):
        assert lib.feed(index,index*5000)==(0,0)
        lib.drain()
    assert lib.SourcePush(0,c.byref(lib.sample(0,43,215000)),215300)==13
    assert lib.status().reason==9


@pytest.mark.parametrize("part",(0,1))
def test_actual_cancel_waits_for_the_held_consumer_and_producer_ack(lib,part):
    lib.configure();lib.begin();lib.face();lib.feed(0,0)
    if part:lib.peek();assert lib.EventCommit(1)==0
    assert lib.peek()[0]==0
    assert lib.Cancel(lib.sid,3,300)==10
    assert lib.ProducerStopped()==10 and lib.status().cleanup_complete==0
    assert lib.SourcePush(0,c.byref(lib.sample(0,1,5000)),5300)==4
    assert lib.peek()[0]==10 and lib.Release()==3
    assert lib.EventCommit(1)==0
    assert lib.status().cleanup_complete==1 and lib.Cancel(lib.sid,3,300)==12
    assert lib.face()==4
    assert lib.Release()==0
    assert lib.Begin(lib.sid,1,(c.c_uint8*15).from_buffer_copy(bytes(lib.status().binding[:15])),1000)==4


def test_jy_c_snapshot_never_invents_measurement_time_epoch_or_precision(lib):
    info=lib.configure(snapshot(jy=True));data=json.loads(info)
    for role in ('IMU','MAG'):
        truth=data['capture_provenance']['sources'][role]
        assert truth['sample_time_basis']=='TARGET_RECEIVE_DECODE_PROXY'
        assert truth['measurement_uncertainty_bound_us'] is None and truth['epoch_provenance']=='UNKNOWN'
        assert data['sources'][role]['epoch']==0
    caps=InstallationCapabilities(InstallationOutcome(InstallationResult.Ok,'DECLARED'),3,3,4096,False)
    with pytest.raises(ValueError):InstallationBinding_Parse(info,'B-'+bytes(lib.status().binding).hex()[:30],caps)
    bad=snapshot(jy=True);bad.sources[1].time_basis=2;bad.sources[1].uncertainty_us=0;bad.sources[1].proof_flags=7
    assert lib.Configure(c.byref(bad))==2
    lib.begin();lib.face();assert lib.feed(0,0)==(0,0)
    line=lib.drain()[0];body=bytes.fromhex(dict(x.split(b'=',1) for x in line.split()[3:])[b'data'].decode())
    assert struct.unpack_from('<I',body,32)[0]==2**32-1


def test_missing_real_parent_intrinsics_are_null_not_default_recorded_identity(lib):
    config=snapshot(jy=True)
    for role in range(2):config.sources[role].intrinsic_generation=0;config.intrinsic_id[role].value=b'UNKNOWN'
    config.accel_bias[:]=config.mag_bias[:]=(0.,0.,0.)
    config.accel_matrix[:]=config.mag_matrix[:]=(0.,)*9
    payload=lib.configure(config);data=json.loads(payload)
    assert data['accel']['bias'] is None and data['mag']['matrix'] is None
    assert data['sources']['MAG']['intrinsic_generation']==0
    with pytest.raises(ValueError):binding(lib,payload)


def test_reentrant_guard_is_nonblocking_and_internal_corruption_revokes_output(lib):
    lib.configure();assert lib.TestGuard(1)==0
    status=Status();status.state=0xAAAAAAAA
    try:assert lib.Status(c.byref(status))==3 and status.state==0xAAAAAAAA
    finally:assert lib.TestGuard(0)==0
    lib.TestCorruptQueue();state=lib.status()
    assert state.state==8 and state.reason==13 and state.consumer_active==0
    page=(c.c_uint8*48)();length=c.c_uint16();next_cursor=c.c_uint16();end=c.c_uint8()
    assert lib.InfoRead(0,page,c.byref(length),c.byref(next_cursor),c.byref(end))==1
