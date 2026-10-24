"""Book b->bm component-map fixtures; estimator retraction is not the truth.

Finite fixture rotations are explicitly defined here. The book supplies the
small-angle relation, not an ordered finite Euler-angle sequence for gamma.
"""
from dataclasses import replace

import numpy as np
import pytest
from numpy.testing import assert_allclose
from scipy.spatial.transform import Rotation

import eskf20_reference as eskf
import inekf20_reference as inekf


def Axis_ComponentMap(axis, angle):
    c, s = np.cos(angle), np.sin(angle)
    if axis == 0:
        return np.array([[1., 0., 0.], [0., c, -s], [0., s, c]])
    if axis == 1:
        return np.array([[c, 0., s], [0., 1., 0.], [-s, 0., c]])
    return np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])


def Combined_ComponentMap(angles):
    # Explicit fixture convention: first x component map, then y, then z.
    return Axis_ComponentMap(2, angles[2]) @ Axis_ComponentMap(1, angles[1]) @ Axis_ComponentMap(0, angles[0])


def Field_Oracle(inclination, declination):
    return Axis_ComponentMap(2, -declination) @ Axis_ComponentMap(0, -inclination) @ np.array([0., 1., 0.])


def State_Create(model, component_map=None, inclination=.61, declination=-.37):
    rotation = Combined_ComponentMap([.27, -.19, .43])
    installation = np.eye(3) if component_map is None else component_map.T
    if model == "eskf":
        return eskf.Eskf20State(np.zeros(3), np.zeros(3), rotation, np.zeros(3), np.zeros(3),
            installation, inclination, declination, np.eye(20)*.002)
    group = np.eye(5); group[:3,:3] = rotation
    return inekf.InEkf20State(group, np.zeros(3), np.zeros(3), installation,
                             inclination, declination, np.eye(20)*.002)


def Rotation_Get(state, model):
    return state.rotation if model == "eskf" else state.group[:3,:3]


def Error_Inject(state, model, error):
    return eskf.Error_Inject(state, error) if model == "eskf" else inekf.InEkf20_Inject(state, error)


def Sample_Create(state, model, true_component_map):
    # Book direction: sensor components = C_b^bm * IMU components.
    body_field = Rotation_Get(state, model).T @ Field_Oracle(state.inclination, state.declination)
    return eskf.MagneticSample(48.*true_component_map @ body_field, np.eye(3)*.03,
                               48., state.time_s, "magnetometer_sensor", "hard_soft_iron_only")


def Residual_Get(state, model, sample):
    return (Rotation_Get(state, model) @ state.installation @ sample.corrected_sensor_uT / 48. -
            Field_Oracle(state.inclination, state.declination))


def Update_Apply(state, model, sample):
    return eskf.Eskf20_UpdateMagnetic(state, sample) if model == "eskf" else inekf.InEkf20_UpdateMagnetic(state, sample)


@pytest.mark.parametrize("model", ["eskf", "inekf"])
@pytest.mark.parametrize("axis", [0, 1, 2])
@pytest.mark.parametrize("sign", [-1., 1.])
def test_known_signed_axis_book_gamma_maps_components_and_corrects(model, axis, sign):
    angle = sign*.06
    component_map = Axis_ComponentMap(axis, angle)
    # Fix passive component-map sign with an explicit basis-vector calculation.
    source_axis, target_axis = (axis+1)%3, (axis+2)%3
    transformed = component_map @ np.eye(3)[:,source_axis]
    assert_allclose(transformed[source_axis], np.cos(angle), atol=1e-16)
    assert_allclose(transformed[target_axis], np.sin(angle), atol=1e-16)
    state = State_Create(model)
    sample = Sample_Create(state, model, component_map)
    error = np.zeros(20); error[15+axis] = angle
    corrected = Error_Inject(state, model, error)
    assert_allclose(corrected.installation, component_map.T, atol=2e-16)
    assert_allclose(Residual_Get(corrected, model, sample), 0., atol=8e-16)
    wrong = Error_Inject(state, model, -error)
    assert np.linalg.norm(Residual_Get(wrong, model, sample)) > .01
    step = Update_Apply(corrected, model, sample)
    assert step.result.value == "ok"
    assert step.nis < 1e-24
    assert_allclose(step.state.installation, corrected.installation, atol=8e-16)
    assert_allclose(Rotation_Get(step.state,model), Rotation_Get(corrected,model), atol=8e-16)
    assert_allclose([step.state.inclination,step.state.declination],
                    [corrected.inclination,corrected.declination],atol=8e-16)


@pytest.mark.parametrize("model", ["eskf", "inekf"])
@pytest.mark.parametrize("angles", [[.12,-.09,.07],[-.12,.09,-.07],[.03,.04,-.05]])
def test_combined_fixture_uses_defined_rotation_vector_not_euler_tuple(model, angles):
    component_map = Combined_ComponentMap(angles)
    total_rotvec = Rotation.from_matrix(component_map).as_rotvec()
    state = State_Create(model); sample = Sample_Create(state,model,component_map)
    error = np.zeros(20); error[15:18] = total_rotvec
    corrected = Error_Inject(state,model,error)
    assert_allclose(corrected.installation@component_map,np.eye(3),atol=5e-16)
    assert_allclose(Residual_Get(corrected,model,sample),0.,atol=8e-16)
    assert np.linalg.norm(total_rotvec-np.asarray(angles)) > 5e-4
    error[15:18] = angles
    wrong = Error_Inject(state,model,error)
    assert np.linalg.norm(Residual_Get(wrong,model,sample)) > 1e-4


@pytest.mark.parametrize("model", ["eskf", "inekf"])
def test_nonzero_nominal_book_map_has_right_residual_without_global_sign_flip(model):
    nominal_map = Combined_ComponentMap([.37,-.24,.29])
    residual_map = Combined_ComponentMap([.04,-.03,.02])
    true_map = nominal_map@residual_map
    state = State_Create(model,nominal_map); sample = Sample_Create(state,model,true_map)
    residual = Rotation.from_matrix(residual_map).as_rotvec()
    assert_allclose(Rotation.from_matrix(nominal_map.T@true_map).as_rotvec(),residual,atol=2e-16)
    error = np.zeros(20); error[15:18] = residual
    corrected = Error_Inject(state,model,error)
    assert_allclose(corrected.installation,true_map.T,atol=4e-16)
    assert_allclose(Residual_Get(corrected,model,sample),0.,atol=8e-16)
    naive = Rotation.from_matrix(true_map).as_rotvec()-Rotation.from_matrix(nominal_map).as_rotvec()
    assert np.linalg.norm(naive-residual) > 1e-3
    error[15:18] = naive
    assert np.linalg.norm(Residual_Get(Error_Inject(state,model,error),model,sample)) > 1e-4


def test_total_rotation_vector_mapping_jacobian_at_nonzero_nominal():
    nominal_map = Combined_ComponentMap([.37,-.24,.29])
    vector = Rotation.from_matrix(nominal_map).as_rotvec()
    x,y,z = vector; skew=np.array([[0.,-z,y],[z,0.,-x],[-y,x,0.]])
    angle=np.linalg.norm(vector)
    inverse_right=(np.eye(3)+.5*skew+
        (1./angle**2-(1.+np.cos(angle))/(2.*angle*np.sin(angle)))*(skew@skew))
    step=2e-6
    numeric=np.column_stack([(Rotation.from_matrix(nominal_map@Rotation.from_rotvec(e).as_matrix()).as_rotvec()-
        Rotation.from_matrix(nominal_map@Rotation.from_rotvec(-e).as_matrix()).as_rotvec())/(2*step)
        for e in np.eye(3)*step])
    assert_allclose(numeric,inverse_right,atol=7e-11,rtol=2e-9)
    assert np.linalg.norm(inverse_right-np.eye(3)) > .1


@pytest.mark.parametrize("model", ["eskf", "inekf"])
def test_fixed_installation_is_applied_once_and_body_label_is_rejected(model):
    fixed_map=Combined_ComponentMap([.23,-.17,.31])
    state=State_Create(model,fixed_map);raw=Sample_Create(state,model,fixed_map)
    assert_allclose(Residual_Get(state,model,raw),0.,atol=8e-16)
    already_corrected=state.installation@raw.corrected_sensor_uT
    double_applied=replace(raw,corrected_sensor_uT=already_corrected,frame="system_body",
                          calibration="hard_soft_iron_and_installation")
    assert np.linalg.norm(Residual_Get(state,model,double_applied)) > .02
    step=Update_Apply(state,model,double_applied)
    assert step.result.value == "invalid_input" and step.state is state
    assert_allclose(Rotation_Get(state,model)@already_corrected/48.,
                    Field_Oracle(state.inclination,state.declination),atol=5e-16)


@pytest.mark.parametrize("model", ["eskf", "inekf"])
@pytest.mark.parametrize("nominal_angles", [[0.,0.,0.],[.37,-.24,.29]])
@pytest.mark.parametrize("inclination,declination", [(-.8,.3),(0.,-.4),(1.2,.7)])
def test_h_from_book_direction_and_independent_state_perturbations(model,nominal_angles,inclination,declination):
    nominal_map=Combined_ComponentMap(nominal_angles)
    state=State_Create(model,nominal_map,inclination,declination)
    nominal_rotation=Rotation_Get(state,model)
    def Residual(error):
        # Generate from book B direction, not A_true=Exp(-gamma) A_hat.
        true_map=nominal_map@Rotation.from_rotvec(error[15:18]).as_matrix()
        theta=error[6:9] if model=="eskf" else -error[:3]
        true_rotation=nominal_rotation@Rotation.from_rotvec(theta).as_matrix()
        true_field=Field_Oracle(inclination-error[18],declination-error[19])
        sensor=true_map@true_rotation.T@true_field
        return nominal_rotation@state.installation@sensor-Field_Oracle(inclination,declination)
    step=2e-6
    numeric=np.column_stack([(Residual(e)-Residual(-e))/(2*step) for e in np.eye(20)*step])
    actual=eskf.Magnetic_Jacobian(state) if model=="eskf" else inekf.InEkf20_MagneticJacobian(state)
    assert_allclose(actual,numeric,atol=4e-10,rtol=2e-9)


@pytest.mark.parametrize("model", ["eskf", "inekf"])
@pytest.mark.parametrize("correction", [[.06,0.,0.],[0.,-.06,0.],[.08,-.07,.05]])
def test_reset_from_book_component_map_recentering(model,correction):
    nominal=Combined_ComponentMap([.37,-.24,.29]);delta=np.array(correction)
    recentered=nominal@Rotation.from_rotvec(delta).as_matrix()
    def Error(perturbation):
        true_map=nominal@Rotation.from_rotvec(delta+perturbation).as_matrix()
        return Rotation.from_matrix(recentered.T@true_map).as_rotvec()
    step=2e-6
    numeric=np.column_stack([(Error(e)-Error(-e))/(2*step) for e in np.eye(3)*step])
    full=np.zeros(20);full[15:18]=delta
    reset=eskf.Error_ResetJacobian(full) if model=="eskf" else inekf.InEkf20_ResetJacobian(full)
    assert_allclose(reset[15:18,15:18],numeric,atol=5e-11,rtol=2e-9)


@pytest.mark.parametrize("model", ["eskf", "inekf"])
@pytest.mark.parametrize("coordinate", ["attitude","installation","inclination","declination"])
def test_coordinate_injections_do_not_alias_different_physical_states(model,coordinate):
    state=State_Create(model,Combined_ComponentMap([.13,-.08,.17]))
    index={"attitude":6 if model=="eskf" else 0,"installation":15,"inclination":18,"declination":19}[coordinate]
    error=np.zeros(20);error[index]=.02
    updated=Error_Inject(state,model,error)
    fields={"attitude":(Rotation_Get(state,model),Rotation_Get(updated,model)),
        "installation":(state.installation,updated.installation),
        "inclination":(state.inclination,updated.inclination),
        "declination":(state.declination,updated.declination)}
    for name,(before,after) in fields.items():
        if name==coordinate:
            assert np.linalg.norm(np.asarray(before)-np.asarray(after)) > .01
        else:
            assert_allclose(before,after,atol=0.,rtol=0.)
    assert_allclose(state.gyro_bias,updated.gyro_bias,atol=0.,rtol=0.)
    assert_allclose(state.accel_bias,updated.accel_bias,atol=0.,rtol=0.)
    if model=="eskf":
        assert_allclose(updated.position,state.position,atol=0.,rtol=0.)
        assert_allclose(updated.velocity,state.velocity,atol=0.,rtol=0.)
    else:
        assert_allclose(updated.group[:3,3:],state.group[:3,3:],atol=0.,rtol=0.)
    matrix=eskf.Magnetic_Jacobian(state) if model=="eskf" else inekf.InEkf20_MagneticJacobian(state)
    assert np.linalg.matrix_rank(matrix,tol=1e-10)==2  # Distinct states need not be identifiable from one vector.
