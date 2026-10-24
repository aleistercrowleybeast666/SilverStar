# Retained independent checks authored for SilverStar, 2026-10-22.
# Imported into repository tests on 2026-10-24. Original SHA-256:
# 1103a28b509ee497be93fe072acd09cfec46f8933ebe2f8cffe60d53d8a89c44
# Adaptation: caller-specified library/reference/output; no historical DLL or
# machine path is used. Checks and numerical tolerances are unchanged.
"""Independent analytic checks plus explicitly separate reference parity.
Never modifies or byte-compiles the read-only source repository.
"""
import ctypes as C
import argparse
import hashlib
import json
import pathlib
import sys
import numpy as np
from scipy.linalg import expm, logm
from scipy.spatial.transform import Rotation

sys.dont_write_bytecode = True
parser = argparse.ArgumentParser()
parser.add_argument('--library', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--reference', required=True)
parser.add_argument('--label', choices=['O0', 'O2'], required=True)
options = parser.parse_args()
ROOT = pathlib.Path(options.output).resolve()
REF = pathlib.Path(options.reference).resolve()
sys.path.insert(0, str(REF))
import eskf20_reference as es
import inekf15_reference as i15
import inekf20_reference as i20

A3, A9, A20, A60, A400 = (C.c_double * n for n in (3,9,20,60,400))
class State(C.Structure):
    _fields_=[('model',C.c_int),('rotation',A9),('position',A3),('velocity',A3),
              ('gyro_bias',A3),('accel_bias',A3),('installation',A9),
              ('inclination',C.c_double),('declination',C.c_double),('time_s',C.c_double),('covariance',A400)]
class Work(C.Structure):
    _fields_=[('candidate',State),('matrix',A400*8),('observation',A60),('gain',A60),
              ('correction',A20),('residual',A3),('noise',A9),('innovation',A9),('nis',C.c_double)]
class Mag(C.Structure):
    _fields_=[('corrected_sensor_uT',A3),('covariance_sensor_uT2',A9),
              ('reference_strength_uT',C.c_double),('time_s',C.c_double),
              ('sensor_frame',C.c_uint),('calibration',C.c_uint)]
lib=C.CDLL(str(pathlib.Path(options.library).resolve()))
ptr=C.POINTER(C.c_double)
lib.Navigation_Validate.argtypes=[C.POINTER(State),C.POINTER(Work)]
lib.Navigation_Predict.argtypes=[C.POINTER(State),C.POINTER(Work),ptr,ptr,ptr,ptr,C.c_double]
lib.Navigation_UpdateVector.argtypes=[C.POINTER(State),C.POINTER(Work),ptr,ptr,C.c_int,C.c_double,C.c_double]
lib.Navigation_UpdateMagnetic.argtypes=[C.POINTER(State),C.POINTER(Work),C.POINTER(Mag),C.c_double]
lib.Navigation_Inject.argtypes=[C.POINTER(State),C.POINTER(Work),ptr]
results=[]
errors={}
def record(name, fn):
    fn(); results.append(name)
def arr(x): return np.asarray(x,dtype=np.float64)
def view(s,name): return np.ctypeslib.as_array(getattr(s,name))
def put(s,name,x): view(s,name)[:]=arr(x).ravel()
def nstate(s): return 15 if s.model==2 else 20
def cov(s): return view(s,'covariance').reshape(20,20)[:nstate(s),:nstate(s)]
def close(label,a,b,tol=3e-11):
    error=float(np.max(np.abs(arr(a)-arr(b))))
    errors[label]=max(errors.get(label,0),error)
    assert error < tol, (label,error,tol)
def state(model, random=False):
    s=State(); s.model=model; put(s,'rotation',np.eye(3)); put(s,'installation',np.eye(3))
    p=np.eye(20)*.1
    if random:
        rng=np.random.default_rng(42+model)
        for name in ('position','velocity','gyro_bias','accel_bias'):
            put(s,name,rng.normal(size=3)*.05)
        put(s,'rotation',Rotation.from_rotvec([.3,-.4,.2]).as_matrix())
        put(s,'installation',Rotation.from_rotvec([-.2,.15,.04]).as_matrix())
        m=rng.normal(size=(20,20))*.015; p=m@m.T+np.eye(20)*.01
        s.inclination=.8; s.declination=-.2
    put(s,'covariance',p)
    return s
def reference(s):
    r=view(s,'rotation').reshape(3,3).copy(); a=view(s,'installation').reshape(3,3).copy()
    g=np.eye(5); g[:3,:3]=r; g[:3,3]=view(s,'velocity'); g[:3,4]=view(s,'position')
    common=dict(gyro_bias=view(s,'gyro_bias'),accel_bias=view(s,'accel_bias'),covariance=cov(s).copy(),time_s=s.time_s)
    extra=dict(installation=a,inclination=s.inclination,declination=s.declination)
    if s.model==1: return es.Eskf20State(position=view(s,'position'),velocity=view(s,'velocity'),rotation=r,**common,**extra)
    if s.model==2: return i15.InEkf15State(group=g,**common)
    return i20.InEkf20State(group=g,**common,**extra)
def parity(s,r,label):
    close(label+'_P',cov(s),r.covariance)
    close(label+'_R',view(s,'rotation').reshape(3,3),r.rotation if s.model==1 else r.group[:3,:3])
    for name,col in [('position',4),('velocity',3)]:
        close(label+'_'+name,view(s,name),getattr(r,name) if s.model==1 else r.group[:3,col])
    for name in ('gyro_bias','accel_bias'): close(label+'_'+name,view(s,name),getattr(r,name))
    if s.model!=2:
        close(label+'_A',view(s,'installation').reshape(3,3),r.installation)
        close(label+'_ID',[s.inclination,s.declination],[r.inclination,r.declination])
def predict(s,omega=(0,0,0),force=(0,0,0),gravity=(0,0,0),density=None,dt=.01):
    if density is None: density=np.zeros(12)
    return lib.Navigation_Predict(C.byref(s),C.byref(Work()),A3(*omega),A3(*force),A3(*gravity),(C.c_double*12)(*density),dt)
def analytical_flow(model):
    s=state(model); put(s,'velocity',[1,2,3]); z=2.0; dt=.02; ax=4.0
    assert predict(s,(0,0,z),(ax,0,0),(0,0,-9.8),dt=dt)==0
    t=z*dt
    close('analytic_rotation',view(s,'rotation').reshape(3,3),[[np.cos(t),-np.sin(t),0],[np.sin(t),np.cos(t),0],[0,0,1]])
    close('analytic_velocity',view(s,'velocity'),[1+ax*np.sin(t)/z,2+ax*(1-np.cos(t))/z,3-9.8*dt])
    close('analytic_position',view(s,'position'),[dt+ax*(1-np.cos(t))/z**2,2*dt+ax*(t-np.sin(t))/z**2,3*dt-4.9*dt**2])
def analytical_cov(model):
    s=state(model); dt=.02; q=np.arange(1,13)*.001
    assert predict(s,density=q,dt=dt)==0
    # Zero angular rate/force: exact p-v-accel_bias chain and attitude-bg chain.
    p0=.1; c=cov(s); pi,vi,ri=(0,3,6) if model==1 else (6,3,0)
    qa,qg=(q[:3],q[3:6]) if model==1 else (q[3:6],q[:3])
    for axis in range(3):
        p=pi+axis;v=vi+axis;r=ri+axis;ba=12+axis;bg=9+axis
        close('analytic_pp',c[p,p],p0*(1+dt**2+.25*dt**4)+qa[axis]**2*dt**3/3+q[9+axis]**2*dt**5/20)
        close('analytic_vv',c[v,v],p0*(1+dt**2)+qa[axis]**2*dt+q[9+axis]**2*dt**3/3)
        close('analytic_pv',c[p,v],p0*(dt+.5*dt**3)+qa[axis]**2*dt**2/2+q[9+axis]**2*dt**4/8)
        close('analytic_vba',c[v,ba],-p0*dt-q[9+axis]**2*dt**2/2)
        close('analytic_rr',c[r,r],p0*(1+dt**2)+qg[axis]**2*dt+q[6+axis]**2*dt**3/3)
        close('analytic_rbg',c[r,bg],-p0*dt-q[6+axis]**2*dt**2/2)
def analytic_update(model):
    s=state(model); w=Work(); z=[.1,-.2,.3]; c=np.eye(3)*.4
    assert lib.Navigation_UpdateVector(C.byref(s),C.byref(w),A3(*z),A9(*c.ravel()),1,0,0)==0
    close('analytic_update_position',view(s,'position'),np.array(z)*.2)
    offset=0 if model==1 else 6
    expected=np.eye(3)*.08
    if model!=1:
        # Pure translation reset: J_rho,phi=skew(delta_rho)/2 exactly.
        correction=-np.array(z)*.2
        expected+=.025*(np.dot(correction,correction)*np.eye(3)-np.outer(correction,correction))
    close('analytic_update_variance',cov(s)[offset:offset+3,offset:offset+3],expected)
def no_alias_and_failures(model):
    s=state(model); w=Work(); before=bytes(s)
    assert predict(s,dt=.021)==2 and bytes(s)==before
    assert predict(s,density=[-1]*12)==2 and bytes(s)==before
    assert predict(s,omega=[float('nan'),0,0])==2 and bytes(s)==before
    assert predict(s,omega=[1e10,0,0])==2 and bytes(s)==before
    assert lib.Navigation_UpdateVector(C.byref(s),C.byref(w),None,None,1,0,0)==1 and bytes(s)==before
    assert lib.Navigation_UpdateVector(C.byref(s),C.byref(w),A3(10,0,0),A9(*np.eye(3).ravel()),1,0,.01)==4 and bytes(s)==before
    d=np.zeros(20); d[6 if model==1 else 0]=.4
    assert lib.Navigation_Inject(C.byref(s),C.byref(w),A20(*d))==5 and bytes(s)==before
    s.covariance[0]=-1; before=bytes(s)
    assert lib.Navigation_UpdateVector(C.byref(s),C.byref(w),None,None,1,0,0)==2 and bytes(s)==before
    assert lib.Navigation_UpdateMagnetic(C.byref(s),C.byref(w),None,0)==2 and bytes(s)==before
def reference_roundtrip(model):
    s=state(model,True); w=Work(); ref=reference(s)
    q=np.arange(1,13)*.002; omega=[.3,-.7,.5]; a=[2,-1,9.6]; g=[0,0,-9.81]
    pred={1:es.Eskf20_Predict,2:i15.InEkf15_Predict,3:i20.InEkf20_Predict}[model]
    for step in range(4):
        ref=pred(ref,omega,a,g,q,.02).state
        assert predict(s,omega,a,g,q,.02)==0
        parity(s,ref,f'parity_{model}_predict')
    update={1:es.Eskf20_UpdateVector,2:i15.InEkf15_Update,3:i20.InEkf20_UpdateVector}[model]
    for kind,index in [('position',1),('velocity',2)]:
        z=np.array([.1,-.1,.05]); noise=np.array([[.03,.002,0],[.002,.04,.001],[0,.001,.02]])
        result=update(ref,z,noise,kind,s.time_s); assert result.result.value=='ok'; ref=result.state
        assert lib.Navigation_UpdateVector(C.byref(s),C.byref(w),A3(*z),A9(*noise.ravel()),index,s.time_s,0)==0
        parity(s,ref,f'parity_{model}_{kind}')
    if model!=2:
        h=es.Magnetic_Field(ref.inclination,ref.declination)[0]
        r=ref.rotation if model==1 else ref.group[:3,:3]
        m=ref.installation.T@r.T@h*45+np.array([.1,-.15,.07]); noise=np.eye(3)*.2
        sample=es.MagneticSample(m,noise,45,s.time_s,'magnetometer_sensor','hard_soft_iron_only')
        result=(es.Eskf20_UpdateMagnetic if model==1 else i20.InEkf20_UpdateMagnetic)(ref,sample)
        assert result.result.value=='ok'; ref=result.state
        mag=Mag(A3(*m),A9(*noise.ravel()),45,s.time_s,1,1)
        assert lib.Navigation_UpdateMagnetic(C.byref(s),C.byref(w),C.byref(mag),0)==0
        parity(s,ref,f'parity_{model}_magnetic')
    d=np.linspace(-.02,.02,20); d[18:]=.001
    if model==1: reset=es.Error_ResetJacobian(d); ref=es.Error_Inject(ref,d,reset@ref.covariance@reset.T)
    elif model==2: reset=i15.InEkf15_ResetJacobian(d[:15]); ref=i15.InEkf15_Inject(ref,d[:15],reset@ref.covariance@reset.T)
    else: reset=i20.InEkf20_ResetJacobian(d); ref=i20.InEkf20_Inject(ref,d,reset@ref.covariance@reset.T)
    assert lib.Navigation_Inject(C.byref(s),C.byref(w),A20(*d))==0
    parity(s,ref,f'parity_{model}_inject_reset')
def independent_group_retraction(model):
    s=state(model,True); before=state(model,True); d=np.linspace(.001,.025,20)
    hat=np.zeros((5,5)); x,y,z=-d[:3]
    hat[:3,:3]=[[0,-z,y],[z,0,-x],[-y,x,0]]; hat[:3,3]=-d[3:6];hat[:3,4]=-d[6:9]
    x0=np.eye(5); x0[:3,:3]=view(s,'rotation').reshape(3,3);x0[:3,3]=view(s,'velocity');x0[:3,4]=view(s,'position')
    expected=x0@expm(hat)
    assert lib.Navigation_Inject(C.byref(s),C.byref(Work()),A20(*d))==0
    close('independent_group_R',view(s,'rotation').reshape(3,3),expected[:3,:3])
    close('independent_group_v',view(s,'velocity'),expected[:3,3])
    close('independent_group_p',view(s,'position'),expected[:3,4])
    assert np.linalg.norm(view(s,'position')-(view(before,'position')-x0[:3,:3]@d[6:9]))>1e-7
def pole_and_missing(model):
    s=state(model);w=Work()
    if model==2:
        assert lib.Navigation_UpdateMagnetic(C.byref(s),C.byref(w),None,0)==2
        return
    s.inclination=np.pi/2; mag=Mag(A3(0,0,-50),A9(*np.eye(3).ravel()),50,0,1,1)
    assert lib.Navigation_UpdateMagnetic(C.byref(s),C.byref(w),C.byref(mag),0)==0
    close('pole_D_column',np.ctypeslib.as_array(w.observation).reshape(3,20)[:,19],np.zeros(3),1e-30)
    close('pole_D_variance',cov(s)[19,19],.1)
    before=bytes(s);assert lib.Navigation_UpdateMagnetic(C.byref(s),C.byref(w),None,0)==1 and bytes(s)==before
    initial=cov(s)[15:,15:].copy();nominal=np.r_[view(s,'installation'),s.inclination,s.declination]
    assert predict(s,(.2,.3,.4),(1,2,3))==0
    close('missing_tail_cov',cov(s)[15:,15:],initial)
    close('missing_tail_nominal',np.r_[view(s,'installation'),s.inclination,s.declination],nominal)

def finite_difference_magnetic(model):
    s=state(model,True); w=Work(); r=view(s,'rotation').reshape(3,3).copy(); a=view(s,'installation').reshape(3,3).copy()
    def field(i,d): return np.array([np.sin(d)*np.cos(i),np.cos(d)*np.cos(i),-np.sin(i)])
    h=field(s.inclination,s.declination); m=a.T@r.T@h*50
    sample=Mag(A3(*m),A9(*np.eye(3).ravel()),50,0,1,1)
    assert lib.Navigation_UpdateMagnetic(C.byref(s),C.byref(w),C.byref(sample),0)==0
    analytic=np.ctypeslib.as_array(w.observation).reshape(3,20).copy()
    def residual(d):
        phi=d[6:9] if model==1 else -d[:3]
        truth_r=r@Rotation.from_rotvec(phi).as_matrix()
        truth_a=Rotation.from_rotvec(-d[15:18]).as_matrix()@a
        truth_h=field(.8-d[18],-.2-d[19])
        return r@a@truth_a.T@truth_r.T@truth_h-h
    numerical=np.zeros((3,20)); eps=1e-6
    for k in range(20):
        d=np.eye(20)[k]*eps; numerical[:,k]=(residual(d)-residual(-d))/(2*eps)
    close('fd_magnetic_'+str(model),analytic,numerical,3e-10)

def finite_difference_reset(model):
    s=state(model,True); p=cov(s).copy(); n=nstate(s); d=np.linspace(-.06,.07,20);d[18:]=.001
    reset=np.eye(n); eps=2e-6
    def hat(v):
        out=np.zeros((5,5));x,y,z=v[:3];out[:3,:3]=[[0,-z,y],[z,0,-x],[-y,x,0]]
        out[:3,3]=v[3:6];out[:3,4]=v[6:9];return out
    def logvec(x):
        l=logm(x).real;return np.r_[l[2,1],l[0,2],l[1,0],l[:3,3],l[:3,4]]
    if model==1:
        left=Rotation.from_rotvec(-d[6:9]).as_matrix()
        for k in range(3):
            e=np.eye(3)[k]*eps
            reset[6:9,6+k]=(Rotation.from_matrix(left@Rotation.from_rotvec(d[6:9]+e).as_matrix()).as_rotvec()-Rotation.from_matrix(left@Rotation.from_rotvec(d[6:9]-e).as_matrix()).as_rotvec())/(2*eps)
    else:
        right=expm(hat(-d[:9]))
        for k in range(9):
            e=np.eye(9)[k]*eps;reset[:9,k]=(logvec(expm(hat(d[:9]+e))@right)-logvec(expm(hat(d[:9]-e))@right))/(2*eps)
    if model!=2:
        left=Rotation.from_rotvec(-d[15:18]).as_matrix()
        for k in range(3):
            e=np.eye(3)[k]*eps
            reset[15:18,15+k]=(Rotation.from_matrix(left@Rotation.from_rotvec(d[15:18]+e).as_matrix()).as_rotvec()-Rotation.from_matrix(left@Rotation.from_rotvec(d[15:18]-e).as_matrix()).as_rotvec())/(2*eps)
    assert lib.Navigation_Inject(C.byref(s),C.byref(Work()),A20(*d))==0
    close('fd_reset_cov_'+str(model),cov(s),reset@p@reset.T,3e-10)

def scaled_flow_parity(model):
    s=state(model,True);ref=reference(s);omega=[50,-40,30];a=[700,-100,500];g=[0,0,-9.81];q=np.arange(1,13)*.01
    pred={1:es.Eskf20_Predict,2:i15.InEkf15_Predict,3:i20.InEkf20_Predict}[model]
    result=pred(ref,omega,a,g,q,.02);assert result.result.value=='ok'
    assert predict(s,omega,a,g,q,.02)==0;parity(s,result.state,f'parity_{model}_scaled')

def repeat_psd(model):
    s=state(model,True);w=Work()
    for step in range(100):
        assert predict(s,(.4,.3,-.7),(1,-2,9.6),(0,0,-9.81),np.ones(12)*.001,dt=.01)==0
        if step%5==0:
            measured=view(s,'position').copy()+np.array([.001,-.002,.001])
            assert lib.Navigation_UpdateVector(C.byref(s),C.byref(w),A3(*measured),A9(*(.01*np.eye(3)).ravel()),1,s.time_s,0)==0
        np.linalg.cholesky(cov(s))
    assert lib.Navigation_Validate(C.byref(s),C.byref(w))==0

def large_translation_reset(model):
    for magnitude in (65.,1e6):
        s=state(model);d=np.zeros(20);d[6]=magnitude;before=cov(s).copy()
        reset=np.eye(nstate(s));reset[7,2]=-.5*magnitude;reset[8,1]=.5*magnitude
        assert lib.Navigation_Inject(C.byref(s),C.byref(Work()),A20(*d))==0
        close('large_translation_nominal',view(s,'position'),[-magnitude,0,0])
        close('large_translation_P_relative',cov(s)/magnitude**2,(reset@before@reset.T)/magnitude**2)
def reference_large_translation(model):
    s=state(model,True);ref=reference(s);d=np.linspace(-.03,.03,20);d[6]=65.;d[18:]=.001
    if model==2:
        reset=i15.InEkf15_ResetJacobian(d[:15]);ref=i15.InEkf15_Inject(ref,d[:15],reset@ref.covariance@reset.T)
    else:
        reset=i20.InEkf20_ResetJacobian(d);ref=i20.InEkf20_Inject(ref,d,reset@ref.covariance@reset.T)
    assert lib.Navigation_Inject(C.byref(s),C.byref(Work()),A20(*d))==0
    parity(s,ref,f'parity_{model}_large_translation')

def covariance_scale_range(model):
    baseline=state(model);assert predict(baseline,(.3,-.2,.1),(2,3,4))==0
    for scale in (1e-200,1e-100,1e-20,1e20,1e100,1e200):
        s=state(model);put(s,'covariance',view(s,'covariance')*scale)
        assert predict(s,(.3,-.2,.1),(2,3,4))==0
        close('covariance_scale_relative',cov(s)/scale,cov(baseline))

def workspace_alias_rejection(model):
    s=state(model);w=Work();w.observation[0]=.2;before=bytes(s);scratch=bytes(w)
    assert lib.Navigation_UpdateVector(C.byref(s),C.byref(w),C.cast(w.observation,ptr),A9(*np.eye(3).ravel()),1,0,0)==2
    assert bytes(s)==before and bytes(w)==scratch
    assert lib.Navigation_Predict(C.byref(s),C.byref(w),C.cast(w.matrix[7],ptr),A3(0,0,0),A3(0,0,0),(C.c_double*12)(*np.zeros(12)),.01)==2
    assert bytes(s)==before and bytes(w)==scratch
    assert lib.Navigation_Inject(C.byref(s),C.byref(w),C.cast(w.correction,ptr))==2
    assert bytes(s)==before and bytes(w)==scratch
    assert lib.Navigation_Validate(C.byref(w.candidate),C.byref(w))==2 and bytes(w)==scratch

for model in (1,2,3):
    tests=[analytical_flow,analytical_cov,analytic_update,no_alias_and_failures,pole_and_missing,finite_difference_reset,repeat_psd,covariance_scale_range,workspace_alias_rejection]
    if model!=1: tests.extend([independent_group_retraction,large_translation_reset])
    if model!=2: tests.append(finite_difference_magnetic)
    for test in tests:
        record(f'independent/{test.__name__}/{model}',lambda test=test,model=model:test(model))
    record(f'reference_parity/{model}',lambda model=model:reference_roundtrip(model))
    record(f'reference_parity/scaled_flow/{model}',lambda model=model:scaled_flow_parity(model))
    if model!=1:
        record(f'reference_parity/large_translation/{model}',lambda model=model:reference_large_translation(model))
# Arguments are resolved before loading the exact freshly compiled library.
report=dict(optimization=options.label,passed=len(results),tests=results,maximum_absolute_errors=errors,state_bytes=C.sizeof(State),workspace_bytes=C.sizeof(Work),
            reference_snapshot={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in REF.glob('*.py') if p.name in ('eskf20_reference.py','inekf15_reference.py','inekf20_reference.py','lie_group.py','inekf_reference.py')})
(ROOT/'verification_results.json').write_text(json.dumps(report,indent=2)+'\n')
(ROOT/f'verification_results_{options.label}.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
