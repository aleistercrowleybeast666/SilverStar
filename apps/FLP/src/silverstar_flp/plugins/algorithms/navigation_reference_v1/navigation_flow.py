"""Audited held-input nominal flow and invariant dynamics; no InEKF9 plugin."""
import numpy as np
from scipy.linalg import expm
from .lie_group import Array_Validate, Group_Validate, Scalar_Validate, Vector_Skew

def Navigation_ErrorDynamics(angular_rate, specific_force):
    omega = Vector_Skew(angular_rate)
    acceleration = Vector_Skew(specific_force)
    matrix = np.kron(np.eye(3), -omega)
    matrix[3:6, :3] = -acceleration
    matrix[6:9, 3:6] = np.eye(3)
    return matrix


def Navigation_PropagateGroup(group, angular_rate, specific_force, gravity, dt):
    """Exact nominal flow for held body omega/a and constant world gravity."""
    group = Group_Validate(group)
    acceleration = Array_Validate(specific_force, (3,))
    gravity = Array_Validate(gravity, (3,))
    dt = Scalar_Validate(dt)
    if not 0 < dt <= 0.02:
        raise ValueError("dt_outside_reference_domain")
    block = np.zeros((9, 9))
    block[:3, :3] = Vector_Skew(angular_rate)
    block[:3, 3:6] = np.eye(3)
    block[3:6, 6:9] = np.eye(3)
    flow = expm(block * dt)
    result = np.eye(5)
    rotation, velocity, position = group[:3, :3], group[:3, 3], group[:3, 4]
    result[:3, :3] = rotation @ flow[:3, :3]
    result[:3, 3] = velocity + gravity * dt + rotation @ flow[:3, 3:6] @ acceleration
    result[:3, 4] = (position + velocity * dt + gravity * (0.5 * dt * dt) +
                      rotation @ flow[:3, 6:9] @ acceleration)
    return Group_Validate(result)

