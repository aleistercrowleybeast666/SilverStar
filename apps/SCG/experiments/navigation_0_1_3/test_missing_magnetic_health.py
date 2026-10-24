"""Missing data is not permission to bypass stored-state or gate validation."""
import numpy as np
import pytest
import eskf20_reference as ref


def state_create():
    return ref.Eskf20State(np.zeros(3), np.zeros(3), np.eye(3), np.zeros(3),
        np.zeros(3), np.eye(3), .5, -.2, np.eye(20))


@pytest.mark.parametrize("field,value", [
    ("covariance", np.full((20,20), np.nan)),
    ("covariance", np.eye(20)*-1),
    ("covariance", np.zeros((20,20))),
    ("covariance", np.eye(19)),
    ("rotation", np.eye(3)*2),
    ("installation", np.diag([1.,1.,-1.])),
    ("position", np.array([0.,np.inf,0.])),
    ("gyro_bias", np.array([0.,np.nan,0.])),
    ("time_s", -1.),
    ("inclination", 2.),
])
def test_missing_sample_still_rejects_invalid_stored_state(field, value):
    state = state_create()
    object.__setattr__(state, field, value)  # Deliberate test-only corruption.
    step = ref.Eskf20_UpdateMagnetic(state, None)
    assert step.result is ref.NavigationEskf20Result.INVALID_INPUT
    assert step.state is state
    assert getattr(state, field) is value


@pytest.mark.parametrize("gate", [0., -1., np.nan, np.inf, True, [1.]])
def test_missing_sample_rejects_invalid_policy_without_mutation(gate):
    state = state_create()
    before = state.covariance.tobytes()
    step = ref.Eskf20_UpdateMagnetic(state, None, gate=gate)
    assert step.result is ref.NavigationEskf20Result.INVALID_INPUT
    assert step.state is state and state.covariance.tobytes() == before


@pytest.mark.parametrize("state", [None, object()])
def test_missing_sample_rejects_wrong_state_type(state):
    step = ref.Eskf20_UpdateMagnetic(state, None)
    assert step.result is ref.NavigationEskf20Result.INVALID_INPUT
    assert step.state is state


@pytest.mark.parametrize("gate", [None, 10.])
def test_healthy_missing_sample_remains_a_transactional_noop(gate):
    state = state_create()
    before = {name:value.tobytes() for name,value in vars(state).items() if isinstance(value,np.ndarray)}
    step = ref.Eskf20_UpdateMagnetic(state, None, gate=gate)
    assert step.result is ref.NavigationEskf20Result.NO_OBSERVATION
    assert step.state is state
    assert before == {name:value.tobytes() for name,value in vars(state).items() if isinstance(value,np.ndarray)}
