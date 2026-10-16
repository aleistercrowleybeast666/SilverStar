"""Real KF6 forward-horizon C against independent full-P NumPy reference."""
import ctypes as ct
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
KERNEL = ROOT/'apps/SCG/plugins/builtin/silverstar_algorithm_estimator_kf6/payload/Algorithm/Estimator/KF6'
COMMON = ROOT/'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Common'
SYSTEM = ROOT/'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/System/Inc'
FIXTURES = Path(__file__).with_name('fixtures')
START = 1_000_000
NAMES = ('ok','queued','warmup','invalid','stale','late','capacity','duplicate','epoch_mismatch',
         'discontinuity','numeric_error','model_mismatch','not_ready','busy','empty')


class Core:
    def __init__(self, lib):
        self.lib = lib
        fp = ct.POINTER(ct.c_float)
        lib.Test_KfReset.argtypes = [ct.c_uint64]
        lib.Test_KfBody.argtypes = [ct.c_uint64,ct.c_float,fp,ct.c_uint32,ct.c_uint32]
        lib.Test_KfInsert.argtypes = [ct.c_uint64,ct.c_uint64,*([ct.c_uint32]*6),fp]
        lib.Test_KfSnapshot.argtypes = [fp,fp,fp,ct.POINTER(ct.c_uint64),ct.POINTER(ct.c_uint32)]
        lib.Test_KfPop.argtypes = [ct.POINTER(ct.c_uint32),fp]
        lib.Test_KfCorrupt.argtypes = [ct.c_uint32]
        lib.Test_KfTrack.argtypes = [ct.c_uint64,ct.c_uint32,ct.c_uint32,ct.c_uint32]
        lib.Test_KfResetInvalid.argtypes = [ct.c_uint32]

    def reset(self, lag=30_000): return NAMES[self.lib.Test_KfReset(lag)]
    def body(self, start, *, dt=.005, delta=(0,0,0), source=0, generation=1, end=None):
        end = start+round(dt*1e6) if end is None else end
        return NAMES[self.lib.Test_KfBody(end,dt,(ct.c_float*3)(*delta),source,generation)]
    def insert(self, source_us, receive_us, *, sequence=1, source=0, generation=1, group=0, valid=1,
               operation=1, observation=(.1,-.1), variance=(1,1)):
        return NAMES[self.lib.Test_KfInsert(source_us,receive_us,sequence,source,generation,group,valid,
            operation,(ct.c_float*4)(*observation,*variance))]
    def advance(self): return NAMES[self.lib.Test_KfAdvance()]
    def pop(self):
        ids, values = (ct.c_uint32*6)(), (ct.c_float*6)()
        result = NAMES[self.lib.Test_KfPop(ids,values)]
        return result, list(ids), list(values)
    def snapshot(self):
        primary,output,accel = (ct.c_float*42)(),(ct.c_float*42)(),(ct.c_float*3)()
        times,counts = (ct.c_uint64*3)(),(ct.c_uint32*9)()
        self.lib.Test_KfSnapshot(primary,output,accel,times,counts)
        return dict(primary=list(primary),output=list(output),accel=list(accel),times=list(times),counts=list(counts),
                    primary_bytes=bytes(primary),output_bytes=bytes(output))


@pytest.fixture(scope='module', params=['-O0','-O2'])
def core(request,tmp_path_factory):
    output = tmp_path_factory.mktemp('kf6_horizon'+request.param)
    # Only the source-count namespace boundary is stubbed; estimator math/config
    # uses the retained real numeric reference configuration and actual C files.
    (output/'project_device_instances.h').write_text('#define PROJECT_GNSS_INSTANCE_COUNT_MAX 4U\n')
    sources = [KERNEL/'Src/navigation_kf.c',KERNEL/'Src/navigation_kf_horizon.c',
               COMMON/'Src/silverstar_assert.c',FIXTURES/'kf6_horizon.c']
    compiler = shutil.which('gcc'); assert compiler, 'Actual GCC is required'
    target = output/'horizon.dll'
    command = [compiler,'-std=c11',request.param,'-Wall','-Wextra','-Werror','-Wpedantic','-Wconversion',
        '-Wsign-conversion','-Wshadow','-Wstrict-prototypes','-Wmissing-prototypes','-fno-fast-math','-ffp-contract=off',
        '-shared',*['-I'+str(p) for p in [KERNEL/'Inc',COMMON/'Inc',SYSTEM,FIXTURES/'navigation_perf_config',output]],
        *map(str,sources),'-lm','-o',str(target)]
    run = subprocess.run(command,capture_output=True,text=True,timeout=120)
    receipt = dict(command=command,exit_code=run.returncode,stdout=run.stdout,stderr=run.stderr,
        compiler=subprocess.check_output([compiler,'--version'],text=True),
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    (output/'compile.json').write_text(json.dumps(receipt,indent=2))
    assert run.returncode == 0,run.stdout+run.stderr
    result = Core(ct.CDLL(str(target)))
    receipt.update(library_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),host_context_bytes=result.lib.Test_KfSize())
    (output/'compile.json').write_text(json.dumps(receipt,indent=2))
    return result


def cycles(core,count,first=START,delta=(0,0,0)):
    for i in range(count):
        assert core.body(first+i*5000,delta=delta) == 'ok'
        assert core.advance() in ('ok','warmup')


@pytest.mark.parametrize('lag,expected',[(0,'invalid'),(9999,'invalid'),(10000,'ok'),(550000,'ok'),(550001,'invalid')])
def test_explicit_bounds(core,lag,expected): assert core.reset(lag)==expected


def test_delayed_primary_independent_output_full_covariance_and_acceleration(core):
    assert core.reset()=='ok'
    for i in range(10):
        assert core.body(START+i*5000,delta=(.005,0,0))=='ok'
        assert core.advance()==('warmup' if i<5 else 'ok')
        actual=core.snapshot();elapsed=(i+1)*.005;delayed=max(0,elapsed-.03)
        assert actual['times']==[START+max(0,(i+1)*5000-30000),START+(i+1)*5000,START+(i+1)*5000]
        assert actual['primary'][0]==pytest.approx(.5*delayed**2,abs=2e-8)
        assert actual['output'][0]==pytest.approx(.5*elapsed**2,abs=2e-8)
        assert actual['accel']==pytest.approx([1,0,0],abs=1e-6)
        for name in ('primary','output'):
            p=np.array(actual[name][6:]).reshape(6,6)
            np.testing.assert_array_equal(p,p.T); np.linalg.cholesky(p)


def test_output_is_never_feedback(core):
    assert core.reset()=='ok';cycles(core,8);before=core.snapshot()
    core.lib.Test_KfCorrupt(7)
    assert core.advance()=='ok';after=core.snapshot()
    assert after['primary_bytes']==before['primary_bytes'] and after['output_bytes']==before['output_bytes']


def test_mid_interval_completion_and_backpressure(core):
    assert core.reset()=='ok';assert core.body(START)=='ok'
    for group in (1,0): assert core.insert(START+2500,START+5000,group=group,operation=30+group)=='queued'
    assert core.advance()=='warmup';cycles(core,6,first=START+5000)
    assert core.snapshot()['counts'][2]==2
    assert core.advance()=='busy' and core.body(START+35000)=='busy'
    assert core.insert(START+10000,START+35000,sequence=2)=='busy'
    first=core.pop();assert first[0]=='ok' and first[1][:3]==[30,1,0]
    assert core.body(START+35000)=='busy'
    second=core.pop();assert second[0]=='ok' and second[1][2]==1
    assert core.pop()[0]=='empty';assert core.body(START+35000)=='ok'


def test_nis_reject_is_not_an_effective_fusion(core):
    assert core.reset()=='ok';cycles(core,7);before=core.snapshot()
    assert core.reset()=='ok';assert core.body(START)=='ok'
    assert core.insert(START+5000,START+5000,observation=(100,-100),variance=(.01,.01))=='queued'
    assert core.advance()=='warmup';cycles(core,6,first=START+5000)
    after=core.snapshot();outcome=core.pop()
    assert after['primary_bytes']==before['primary_bytes'] and after['output_bytes']==before['output_bytes']
    assert outcome[0]=='ok' and outcome[1][4:]==[2,0] and outcome[2][0]>13.816


def test_fusion_velocity_correction_does_not_create_acceleration(core):
    assert core.reset(10000)=='ok';assert core.body(START)=='ok'
    assert core.insert(START+5000,START+5000,group=2,observation=(1,0),variance=(.1,.1))=='queued'
    assert core.advance()=='warmup';cycles(core,2,first=START+5000)
    snap=core.snapshot();assert snap['output'][3]>.4 and snap['accel']==[0,0,0]
    assert core.pop()[0]=='ok'


def test_source_group_watermarks_order_and_wrap(core):
    assert core.reset()=='ok';assert core.body(START)=='ok'
    for group in (3,1,2,0):assert core.insert(START+1000,START+5000,sequence=0xffffffff,group=group,operation=group)=='queued'
    assert core.insert(START+1000,START+5000,sequence=0xffffffff)=='duplicate'
    assert core.insert(START+2000,START+5000,sequence=0,source=1)=='queued'
    assert core.insert(START+2000,START+5000,sequence=0)=='queued'
    assert core.insert(START+2000,START+5000,sequence=0xffffffff)=='discontinuity'
    assert core.advance()=='warmup';cycles(core,6,first=START+5000)
    assert [core.pop()[1][2] for _ in range(4)]==[0,1,2,3]
    assert [core.pop()[1][3] for _ in range(2)]==[1,0]


def test_receive_evidence_once_per_producer_without_fusion(core):
    assert core.reset()=='ok';assert core.body(START)=='ok';before=core.snapshot()
    track=core.lib.Test_KfTrack
    assert NAMES[track(START+5000,0xffffffff,0,15)]=='ok'
    assert NAMES[track(START+5000,0xffffffff,0,15)] in ('duplicate','invalid')
    assert NAMES[track(START+5000,1,1,15)]=='ok'
    assert core.snapshot()['primary_bytes']==before['primary_bytes']
    assert core.advance()=='warmup';assert core.body(START+5000)=='ok'
    assert NAMES[track(START+10000,0,0,15)]=='ok'
    assert NAMES[track(START+10000,0xffffffff,0,15)] in ('invalid','discontinuity')


def test_receipt_identity_distinguishes_duplicates_old_sequence_and_bad_clock(core):
    assert core.reset()=='ok';assert core.body(START)=='ok'
    track=core.lib.Test_KfTrack
    assert NAMES[track(START+5000,1,0,15)]=='ok'
    assert NAMES[track(START+5000,1,0,15)]=='duplicate'
    assert NAMES[track(START+5000,0,0,15)]=='discontinuity'
    assert NAMES[track(START+5000,2,0,15)]=='invalid'


@pytest.mark.parametrize('kind',[0,1])
def test_reset_rejects_invalid_noise_and_gate_configuration(core,kind):
    assert NAMES[core.lib.Test_KfResetInvalid(kind)]=='invalid'


def test_changed_output_model_is_not_silently_overwritten(core):
    assert core.reset()=='ok';assert core.body(START)=='ok';before=core.snapshot()
    core.lib.Test_KfCorrupt(10)
    assert core.advance()=='epoch_mismatch'
    after=core.snapshot()
    assert after['primary_bytes']==before['primary_bytes'] and after['counts'][3]==1


def test_corrupt_receive_tracker_cannot_create_a_receipt_certificate(core):
    assert core.reset()=='ok';assert core.body(START)=='ok'
    core.lib.Test_KfCorrupt(11)
    assert NAMES[core.lib.Test_KfTrack(START+5000,1,1,15)]=='numeric_error'
    assert core.advance()=='not_ready'


def test_late_rejection_exact_boundary_and_capacity(core):
    assert core.reset()=='ok';cycles(core,12)
    assert core.insert(START+25000,START+60000)=='late'
    assert core.insert(START+30000,START+60000,sequence=2)=='queued'
    assert core.advance()=='ok' and core.pop()[0]=='ok'
    assert core.reset()=='ok';assert core.body(START)=='ok'
    for i in range(64):assert core.insert(START+i+1,START+5000,sequence=i+1,operation=i+1,observation=(0,0),variance=(1000,1000))=='queued'
    assert core.insert(START+1000,START+5000,sequence=65)=='capacity'
    assert core.insert(START+1000,START+5000,sequence=65)=='duplicate'
    assert core.advance()=='warmup';cycles(core,6,first=START+5000)
    assert [core.pop()[1][0] for _ in range(64)]==list(range(1,65))


def test_body_capacity_latches(core):
    assert core.reset(550000)=='ok';before=core.snapshot()
    for i in range(160):assert core.body(START+i*1000,dt=.001)=='ok'
    assert core.body(START+160000,dt=.001)=='capacity'
    assert core.snapshot()['primary_bytes']==before['primary_bytes'] and core.advance()=='not_ready'


@pytest.mark.parametrize('kind', [1,2,3,4,5,6,8,9])
def test_internal_corruption_latches_without_partial_commit(core,kind):
    assert core.reset(10000)=='ok';assert core.body(START)=='ok'
    assert core.insert(START+5000,START+5000)=='queued';assert core.advance()=='warmup'
    assert core.body(START+5000)=='ok';assert core.advance()=='ok';assert core.body(START+10000)=='ok'
    core.lib.Test_KfCorrupt(kind);before=core.snapshot()
    assert core.advance() in ('numeric_error','discontinuity')
    after=core.snapshot()
    assert after['primary_bytes']==before['primary_bytes'] and after['output_bytes']==before['output_bytes']
    assert after['counts'][3]==1 and core.advance()=='not_ready' and core.pop()[0]=='not_ready'


@pytest.mark.parametrize('kwargs,expected',[({'source':1},'epoch_mismatch'),({'generation':2},'epoch_mismatch'),
    ({'dt':math.nan,'end':START+5000},'discontinuity'),({'delta':(math.nan,0,0)},'discontinuity')])
def test_bad_body_latches(core,kwargs,expected):
    assert core.reset()=='ok';before=core.snapshot();assert core.body(START,**kwargs)==expected
    assert core.snapshot()['primary_bytes']==before['primary_bytes'] and core.advance()=='not_ready'


@pytest.mark.parametrize('kwargs,expected',[({'group':5},'invalid'),({'source':4},'invalid'),
    ({'group':4,'source':0},'invalid'),({'generation':2},'epoch_mismatch'),({'valid':0},'invalid'),
    ({'variance':(math.nan,1)},'invalid'),({'variance':(0,1)},'invalid'),({'observation':(math.inf,0)},'invalid')])
def test_external_measurement_ordinary_error(core,kwargs,expected):
    assert core.reset()=='ok';assert core.body(START)=='ok';before=core.snapshot()
    assert core.insert(START+1000,START+5000,**kwargs)==expected
    assert core.snapshot()['primary_bytes']==before['primary_bytes'] and core.advance()=='warmup'


def predict(x,p,body,start,end):
    # F64 matrix oracle preserves each ORIGINAL increment's noise density.
    lo,hi,dv=body; original=.005; dt=(end-start)*1e-6;delta=np.array(dv)*(end-start)/(hi-lo)
    x=x.copy();x[:3]+=x[3:]*dt+.5*delta*dt;x[3:]+=delta
    f=np.eye(6);f[:3,3:]=np.eye(3)*dt;q=np.zeros((6,6))
    for axis,sigma in enumerate((1.5,1.5,2.)):
        density=sigma*sigma*original
        q[axis,axis]=density*dt**3/3;q[axis,axis+3]=q[axis+3,axis]=density*dt*dt/2;q[axis+3,axis+3]=density*dt
    return x,f@p@f.T+q


def propagate(x,p,time,target,bodies):
    for body in bodies:
        if body[1]<=time:continue
        if time==target:break
        end=min(body[1],target);x,p=predict(x,p,body,time,end);time=end
    assert time==target
    return x,p


@pytest.mark.parametrize('lag',[10000,30000,32500])
def test_independent_full_state_covariance_measurement_sequence(core,lag):
    assert core.reset(lag)=='ok';snap=core.snapshot();x=np.array(snap['primary'][:6]);p=np.array(snap['primary'][6:]).reshape(6,6)
    now=START;primary_us=START;bodies=[];events=[];number=0;completed=0
    for step in range(180):
        dv=tuple(float(np.float32(v)) for v in (.003*math.sin(step*.04),.002*math.cos(step*.03),.0001))
        bodies.append((now,now+5000,dv));assert core.body(now,delta=dv)=='ok';now+=5000
        if step%4==3:
            for group in range(5):
                number+=1;source=now-(1000 if group%2 else 2500)
                observation=(.02*math.sin(step*.1),.01*math.cos(step*.2));variance=(4.,4.)
                assert core.insert(source,now,sequence=step+1,source=1 if group==4 else 0,
                    group=group,operation=number,observation=observation,variance=variance)=='queued'
                events.append((source,group,number,observation))
        target=max(START,now-lag);ready=sorted((e for e in events if e[0]<=target),key=lambda e:e[:2])
        expected=[]
        for source,group,operation,observation in ready:
            x,p=propagate(x,p,primary_us,source,bodies);primary_us=source
            indices=([0,1],[2],[3,4],[5],[2])[group];h=np.eye(6)[indices];z=np.array(observation[:len(indices)])
            r=z-h@x;variance=np.eye(len(indices))*4;s=h@p@h.T+variance;inv=np.linalg.inv(s);nis=float(r@inv@r)
            # This scenario stays below the gate; dedicated tests exercise NIS rejection.
            assert nis<6.635
            k=p@h.T@inv;x=x+k@r;a=np.eye(6)-k@h;p=a@p@a.T+k@variance@k.T;p=(p+p.T)*.5
            expected.append((operation,nis))
        events=[e for e in events if e[0]>target]
        x,p=propagate(x,p,primary_us,target,bodies);primary_us=target
        out_x,out_p=propagate(x.copy(),p.copy(),target,now,bodies)
        assert core.advance() in ('ok','warmup');actual=core.snapshot()
        np.testing.assert_allclose(actual['primary'],np.r_[x,p.ravel()],rtol=2e-6,atol=3e-6)
        np.testing.assert_allclose(actual['output'],np.r_[out_x,out_p.ravel()],rtol=2e-6,atol=3e-6)
        for operation,nis in expected:
            status,ids,values=core.pop();assert status=='ok' and ids[0]==operation and ids[5]==1
            assert values[0]==pytest.approx(nis,rel=3e-5,abs=1e-8);completed+=1
        assert core.pop()[0]=='empty'
        bodies=[b for b in bodies if b[1]>target]
    assert completed>=210
