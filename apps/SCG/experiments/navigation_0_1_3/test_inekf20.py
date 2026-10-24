"""Independent joint group, magnetic geometry and 20x20 covariance checks."""
from dataclasses import replace

import numpy as np
import pytest
from numpy.testing import assert_allclose
from scipy.spatial.transform import Rotation

import eskf20_reference as eskf
import inekf20_reference as ref
import test_inekf15 as oracle


def State_Create():
    base = oracle.State_Create()
    rng = np.random.default_rng(20018)
    factor = rng.normal(size=(20, 20)) * .008
    return ref.InEkf20State(base.group, base.gyro_bias, base.accel_bias,
        Rotation.from_rotvec([.34, -.18, .21]).as_matrix(), .73, -.34,
        factor @ factor.T + np.eye(20) * .004, base.time_s)


def Truth_Oracle(estimate, error):
    state = oracle.Truth_Oracle(estimate, error[:15])
    return replace(state, installation=Rotation.from_rotvec(-error[15:18]).as_matrix() @ estimate.installation,
        inclination=estimate.inclination - error[18], declination=estimate.declination - error[19])


def Error_Oracle(estimate, truth):
    return np.r_[oracle.Error_Oracle(estimate, truth),
        -Rotation.from_matrix(truth.installation @ estimate.installation.T).as_rotvec(),
        estimate.inclination - truth.inclination, estimate.declination - truth.declination]


def Field_Oracle(state):
    if abs(state.inclination) == np.pi / 2:
        return np.array([0., 0., -np.sign(state.inclination)])
    return (Rotation.from_rotvec([0., 0., -state.declination]).as_matrix() @
            Rotation.from_rotvec([-state.inclination, 0., 0.]).as_matrix() @ [0., 1., 0.])


def Sample_Create(truth):
    vector = truth.installation.T @ truth.group[:3, :3].T @ Field_Oracle(truth)
    return eskf.MagneticSample(vector * 48., np.diag([.03, .02, .04]), 48., truth.time_s,
                               "magnetometer_sensor", "hard_soft_iron_only")


@pytest.mark.parametrize("inclination", [-1.4, -.6, 0., .73, 1.4])
@pytest.mark.parametrize("nonzero_installation", [False, True])
def test_magnetic_h_all_twenty_columns(inclination, nonzero_installation):
    state = replace(State_Create(), inclination=inclination)
    if not nonzero_installation:
        state = replace(state, installation=np.eye(3))
    def Residual(error):
        truth = Truth_Oracle(state, error)
        measurement = Sample_Create(truth).corrected_sensor_uT / 48.
        return state.group[:3, :3] @ state.installation @ measurement - Field_Oracle(state)
    numeric = oracle.Jacobian_Finite(Residual, 20, step=2e-6)
    assert_allclose(ref.InEkf20_MagneticJacobian(state), numeric, atol=4e-10, rtol=3e-9)


@pytest.mark.parametrize("scale", [0., .2, 1.])
def test_full_twenty_injection_and_reset_by_general_group_oracle(scale):
    state, correction = State_Create(), np.linspace(-.09, .1, 20) * scale
    updated = ref.InEkf20_Inject(state, correction)
    assert_allclose(Error_Oracle(updated, Truth_Oracle(state, correction)), 0., atol=2e-15)
    numeric = oracle.Jacobian_Finite(lambda e: Error_Oracle(updated, Truth_Oracle(state, correction+e)), 20)
    reset = ref.InEkf20_ResetJacobian(correction)
    assert_allclose(reset, numeric, atol=6e-11, rtol=1e-8)
    assert_allclose(reset @ state.covariance @ reset.T, numeric @ state.covariance @ numeric.T,
                    atol=8e-13, rtol=3e-8)
    if scale:
        assert np.linalg.norm(reset[3:9, :3]) > .001


def test_augmented_twenty_f_and_constant_extra_dynamics():
    state = State_Create()
    omega, force, gravity, dt = np.array([.4, -.3, .7]), np.array([1., 2., 9.5]), np.array([0., 0., -9.81]), .02
    nominal = oracle.Flow_Oracle(state, omega, force, gravity, dt)
    transition, noise = ref.InEkf20_Discretize(omega-state.gyro_bias, force-state.accel_bias, np.zeros(12), dt)
    numeric = oracle.Jacobian_Finite(lambda e: Error_Oracle(nominal,
        oracle.Flow_Oracle(Truth_Oracle(state, e), omega, force, gravity, dt)), 20)
    assert_allclose(transition, numeric, atol=1e-10, rtol=3e-7)
    assert_allclose(ref.InEkf20_Dynamics(omega, force)[15:], 0., atol=0.)
    assert_allclose(noise, 0., atol=0.)
    assert_allclose(transition[15:, 15:], np.eye(5), atol=0.)


def Conventional_Create(state):
    transform = ref.Coordinates_ToEskf20(state.group)
    return eskf.Eskf20State(state.group[:3, 4], state.group[:3, 3], state.group[:3, :3],
        state.gyro_bias, state.accel_bias, state.installation, state.inclination, state.declination,
        transform @ state.covariance @ transform.T, state.time_s)


def test_common_coordinates_full_prediction_magnetic_h_and_noise():
    state, conventional = State_Create(), Conventional_Create(State_Create())
    transform = ref.Coordinates_ToEskf20(state.group)
    assert_allclose(ref.InEkf20_MagneticJacobian(state), eskf.Magnetic_Jacobian(conventional) @ transform, atol=2e-16)
    omega, force, gravity, dt = np.array([.4, -.3, .7]), np.array([1., 2., 9.5]), np.array([0., 0., -9.81]), .02
    density = np.linspace(.001, .012, 12)
    result = ref.InEkf20_Predict(state, omega, force, gravity, density, dt)
    compared = eskf.Eskf20_Predict(conventional, omega, force, gravity, np.r_[density[3:6],density[:3],density[6:]], dt)
    assert result.result is ref.NavigationAugmentedResult.OK
    assert compared.result is eskf.NavigationEskf20Result.OK
    mapping = ref.Coordinates_ToEskf20(result.state.group)
    assert_allclose(mapping @ result.state.covariance @ mapping.T, compared.state.covariance, atol=3e-17, rtol=1e-10)
    assert not np.array_equal(result.state.covariance[:15,15:], state.covariance[:15,15:])
    assert_allclose(result.state.covariance[15:,15:], state.covariance[15:,15:], atol=0.)


def test_complete_magnetic_joseph_reset_against_independent_numeric_reset():
    state = State_Create()
    truth = Truth_Oracle(state, np.linspace(-.005, .007, 20))
    sample, matrix = Sample_Create(truth), ref.InEkf20_MagneticJacobian(state)
    transform = state.group[:3,:3] @ state.installation
    residual = transform @ sample.corrected_sensor_uT / 48. - Field_Oracle(state)
    noise = transform @ sample.covariance_sensor_uT2 @ transform.T / 48.**2
    gain = state.covariance @ matrix.T @ np.linalg.inv(matrix @ state.covariance @ matrix.T + noise)
    correction = gain @ residual
    expected = Truth_Oracle(state, correction)
    numeric = oracle.Jacobian_Finite(lambda e: Error_Oracle(expected, Truth_Oracle(state, correction+e)),20)
    contraction = np.eye(20) - gain @ matrix
    posterior = contraction @ state.covariance @ contraction.T + gain @ noise @ gain.T
    result = ref.InEkf20_UpdateMagnetic(state, sample, gate=20.)
    assert result.result is ref.NavigationAugmentedResult.OK
    assert_allclose(Error_Oracle(result.state, expected), 0., atol=2e-15)
    assert_allclose(result.state.covariance, numeric @ posterior @ numeric.T, atol=8e-13, rtol=3e-8)
    assert np.linalg.norm(result.state.gyro_bias-state.gyro_bias) > 1e-5


def test_common_mean_updates_agree_to_first_order_not_finite_equality():
    state = State_Create()
    differences=[]
    for scale in (.02,.01):
        sample = Sample_Create(Truth_Oracle(state, np.linspace(-.1,.1,20)*scale))
        invariant = ref.InEkf20_UpdateMagnetic(state,sample)
        conventional = eskf.Eskf20_UpdateMagnetic(Conventional_Create(state),sample)
        assert invariant.result is ref.NavigationAugmentedResult.OK
        assert conventional.result is eskf.NavigationEskf20Result.OK
        assert_allclose(invariant.state.group[:3,:3],conventional.state.rotation,atol=2e-15)
        assert_allclose(invariant.state.installation,conventional.state.installation,atol=2e-15)
        differences.append(np.linalg.norm(np.r_[invariant.state.group[:3,3]-conventional.state.velocity,
            invariant.state.group[:3,4]-conventional.state.position]))
    assert differences[1] > 1e-10  # SE_2(3)'s translation retraction is actually used.
    assert 3.9 < differences[0]/differences[1] < 4.1


@pytest.mark.parametrize("pole", [-np.pi/2,np.pi/2])
def test_exact_pole_large_independent_declination_variance_not_reduced(pole):
    covariance=np.eye(20)*1e-6; covariance[19,19]=1e28
    state=replace(State_Create(),inclination=pole,covariance=covariance)
    assert np.array_equal(ref.InEkf20_MagneticJacobian(state)[:,19],np.zeros(3))
    step=ref.InEkf20_UpdateMagnetic(state,Sample_Create(state))
    assert step.result is ref.NavigationAugmentedResult.OK
    assert step.declination_sensitivity == 0.
    assert step.state.covariance[19,19] == state.covariance[19,19]
    assert step.state.declination == state.declination


@pytest.mark.parametrize("distance", [1e-7,1e-10])
def test_near_pole_preserves_real_sensitivity(distance):
    state=replace(State_Create(),inclination=np.pi/2-distance)
    assert np.linalg.norm(ref.InEkf20_MagneticJacobian(state)[:,19]) > 0.
    assert_allclose(np.linalg.norm(ref.InEkf20_MagneticJacobian(state)[:,19]),np.sin(distance),atol=2e-16)


def test_sixty_degree_exact_derivative_and_static_gauge():
    state=replace(State_Create(),group=np.eye(5),inclination=np.pi/3)
    assert_allclose(np.linalg.norm(ref.InEkf20_MagneticJacobian(state)[:,19]),.5,atol=2e-16)
    direction=np.zeros(20); direction[2],direction[19]=-1.,1.
    matrix=ref.InEkf20_MagneticJacobian(state)
    assert_allclose(matrix@direction,0.,atol=2e-16)
    assert_allclose(ref.InEkf20_Dynamics(np.zeros(3),[0.,0.,9.81])@direction,0.,atol=0.)
    truth=Truth_Oracle(state,direction*.13)
    assert_allclose(Sample_Create(truth).corrected_sensor_uT,Sample_Create(state).corrected_sensor_uT,atol=3e-14)
    assert np.linalg.matrix_rank(matrix,tol=1e-10)==2


def test_sensor_axis_relabeling_with_full_measurement_covariance():
    state=State_Create(); sample=Sample_Create(Truth_Oracle(state,np.linspace(-.01,.015,20)))
    relabel=Rotation.from_rotvec([.4,-.3,.5]).as_matrix()
    changed=replace(state,installation=state.installation@relabel.T)
    new_sample=replace(sample,corrected_sensor_uT=relabel@sample.corrected_sensor_uT,
                       covariance_sensor_uT2=relabel@sample.covariance_sensor_uT2@relabel.T)
    first,second=ref.InEkf20_UpdateMagnetic(state,sample),ref.InEkf20_UpdateMagnetic(changed,new_sample)
    assert first.result is second.result is ref.NavigationAugmentedResult.OK
    assert_allclose(first.state.group,second.state.group,atol=3e-15)
    assert_allclose(first.state.installation@relabel.T,second.state.installation,atol=3e-15)
    assert_allclose(first.state.covariance,second.state.covariance,atol=3e-17,rtol=1e-10)
    # Whitened residual bound, given ||dr|| <= 32 eps for these unit-vector products.
    residual_bound=32*np.finfo(float).eps
    noise_lower=np.linalg.eigvalsh(sample.covariance_sensor_uT2).min()/48.**2
    bound=2*np.sqrt(first.nis/noise_lower)*residual_bound+residual_bound**2/noise_lower
    assert abs(first.nis-second.nis) <= bound


def Scenario_Run(excited,magnetic=True,count=650):
    truth=replace(State_Create(),group=np.eye(5),time_s=0.)
    error=np.r_[[.012,-.01,.015],np.zeros(6),[.008,-.006,.007],[.035,-.03,.025],[.012,-.015,.01],.02,-.025]
    estimate=Truth_Oracle(truth,-error)
    estimate=replace(estimate,covariance=np.diag(np.r_[np.full(3,.02),np.full(6,.04),
        np.full(3,.005),np.full(3,.02),np.full(5,.02)]))
    density=np.r_[np.full(3,1e-4),np.full(3,1e-3),np.full(6,1e-6)]
    gravity,dt=np.array([0.,0.,-9.81]),.02
    transition,rows,missing=np.eye(20),[],0
    before=np.r_[estimate.gyro_bias-truth.gyro_bias,estimate.accel_bias-truth.accel_bias]
    extra_before=(estimate.installation.copy(),estimate.inclination,estimate.declination,estimate.covariance[15:,15:].copy())
    for index in range(count):
        time=index*dt
        omega=np.array([.5*np.sin(.9*time),.4*np.cos(.7*time),.3*np.sin(1.1*time)]) if excited else np.zeros(3)
        force=np.array([1.3*np.sin(.8*time),.9*np.cos(1.2*time),9.81+.7*np.sin(.6*time)]) if excited else -gravity
        omega_m,force_m=omega+truth.gyro_bias,force+truth.accel_bias
        truth=oracle.Flow_Oracle(truth,omega_m,force_m,gravity,dt)
        phi,_=ref.InEkf20_Discretize(omega,force,np.zeros(12),dt)
        transition=phi@transition
        step=ref.InEkf20_Predict(estimate,omega_m,force_m,gravity,density,dt)
        assert step.result is ref.NavigationAugmentedResult.OK
        estimate=step.state
        for kind,column,offset in (("position",4,6),("velocity",3,3)):
            matrix=np.zeros((3,20));matrix[:,offset:offset+3]=np.eye(3)
            if index%5==0:
                rows.append(matrix@transition)
                update=ref.InEkf20_UpdateVector(estimate,truth.group[:3,column],np.eye(3)*.0025,kind,truth.time_s)
                assert update.result is ref.NavigationAugmentedResult.OK
                estimate=update.state
        sample=Sample_Create(truth) if magnetic and index%5==0 else None
        update=ref.InEkf20_UpdateMagnetic(estimate,sample)
        if sample is None:
            assert update.result is ref.NavigationAugmentedResult.NO_OBSERVATION and update.state is estimate
            missing+=1
        else:
            assert update.result is ref.NavigationAugmentedResult.OK
            rows.append(ref.InEkf20_MagneticJacobian(truth)@transition)
        estimate=update.state
        np.linalg.cholesky(estimate.covariance)
    singular=np.linalg.svd(np.vstack(rows),compute_uv=False)
    rank=int(np.count_nonzero(singular>singular[0]*1e-8))
    after=np.r_[estimate.gyro_bias-truth.gyro_bias,estimate.accel_bias-truth.accel_bias]
    return before,after,rank,singular[-1]/singular[0],missing,estimate,extra_before


def test_excited_twenty_state_window_bias_convergence_and_spd():
    before,after,rank,ratio,missing,_,_=Scenario_Run(True)
    print(f"InEKF20 excited 13s window: rank={rank}/20, singular_ratio={ratio:.6g}, bias_initial={before.tolist()}, bias_final={after.tolist()}, missing_mag={missing}")
    assert rank==20 and ratio>1e-6
    assert np.linalg.norm(after[:3]) < .25*np.linalg.norm(before[:3])
    assert np.linalg.norm(after[3:]) < .25*np.linalg.norm(before[3:])
    assert missing>0


def test_twenty_static_window_retains_unobservable_directions():
    before,after,rank,ratio,_,_,_=Scenario_Run(False,count=160)
    print(f"InEKF20 static 3.2s window: rank={rank}/20, singular_ratio={ratio:.6g}, bias_initial={before.tolist()}, bias_final={after.tolist()}")
    assert rank<20 and ratio<1e-10


def test_missing_magnetics_do_not_identify_independent_installation_or_angles():
    _,_,rank,_,_,estimate,initial=Scenario_Run(True,magnetic=False,count=100)
    assert rank<=15
    assert_allclose(estimate.installation,initial[0],atol=0.,rtol=0.)
    assert estimate.inclination==initial[1] and estimate.declination==initial[2]
    assert_allclose(estimate.covariance[15:,15:],initial[3],atol=0.,rtol=0.)


@pytest.mark.parametrize("change", [
    {"frame":"system_body"},{"frame":np.array(["magnetometer_sensor"])},
    {"calibration":"hard_soft_iron_and_installation"},{"calibration":"raw"},
    {"time_s":[1.]},{"time_s":1+0j},{"time_s":.99},
    {"reference_strength_uT":0.},{"reference_strength_uT":"48"},
    {"corrected_sensor_uT":[10**1000,0,0]},{"corrected_sensor_uT":[np.nan,0,0]},
    {"corrected_sensor_uT":[1j,0,0]},{"covariance_sensor_uT2":np.zeros((3,3))}])
def test_magnetic_transaction_boundaries_preserve_state(change):
    state=State_Create()
    step=ref.InEkf20_UpdateMagnetic(state,replace(Sample_Create(state),**change))
    assert step.result is ref.NavigationAugmentedResult.INVALID_INPUT and step.state is state


@pytest.mark.parametrize("bad", [True,"0.01",[.01],.01+0j,np.nan,10**1000])
def test_scalar_time_and_gate_rejections(bad):
    state=State_Create()
    predicted=ref.InEkf20_Predict(state,np.zeros(3),np.zeros(3),np.zeros(3),np.zeros(12),bad)
    update=ref.InEkf20_UpdateMagnetic(state,Sample_Create(state),bad)
    vector=ref.InEkf20_UpdateVector(state,np.ones(3),np.eye(3),"position",bad)
    for step in (predicted,update,vector):
        assert step.result is ref.NavigationAugmentedResult.INVALID_INPUT and step.state is state


def test_numeric_failures_gate_and_correction_rejection_are_transactions():
    state=State_Create()
    step=ref.InEkf20_Predict(state,np.zeros(3),np.zeros(3),np.zeros(3),np.full(12,1e308),.01)
    assert step.result is ref.NavigationAugmentedResult.NUMERIC_ERROR and step.state is state
    sample=replace(Sample_Create(state),corrected_sensor_uT=np.full(3,1e308),reference_strength_uT=1e-308)
    step=ref.InEkf20_UpdateMagnetic(state,sample)
    assert step.result is ref.NavigationAugmentedResult.NUMERIC_ERROR and step.state is state
    sample=replace(Sample_Create(state),corrected_sensor_uT=np.full(3,480.))
    step=ref.InEkf20_UpdateMagnetic(state,sample,.01)
    assert step.result is ref.NavigationAugmentedResult.REJECTED_NIS and step.state is state
    step=ref.InEkf20_UpdateMagnetic(state,sample)
    assert step.result is ref.NavigationAugmentedResult.REJECTED_CORRECTION and step.state is state


@pytest.mark.parametrize("field", ["group","installation","covariance"])
def test_corrupt_stored_state_and_missing_measurement_do_not_bypass_validation(field):
    state=State_Create();bad=getattr(state,field).copy();bad[0,0]=1e308
    if field=="covariance":bad[0,1],bad[1,0]=1e308,-1e308
    object.__setattr__(state,field,bad)
    for step in (ref.InEkf20_UpdateMagnetic(state,None),
                 ref.InEkf20_Predict(state,np.zeros(3),np.zeros(3),np.zeros(3),np.zeros(12),.01)):
        assert step.result is ref.NavigationAugmentedResult.INVALID_INPUT and step.state is state


def test_constructor_copies_scalar_and_array_inputs():
    state=State_Create();alias=np.array(.73);rotation=state.installation.copy()
    copied=replace(state,inclination=alias,installation=rotation)
    alias[...],rotation[0,0]=0.,100.
    assert copied.inclination==.73 and isinstance(copied.inclination,float)
    assert_allclose(copied.installation,state.installation,atol=0.,rtol=0.)
    with pytest.raises(ValueError):copied.covariance[0,0]=0.
    with pytest.raises(ValueError):replace(state,inclination="0.73")
    with pytest.raises(ValueError):replace(state,inclination=1.7)
