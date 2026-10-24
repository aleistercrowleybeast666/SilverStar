import math

import matplotlib.pyplot as plt
import numpy as np

from processing.flight_plotter import FlightPlotter


def test_rotated_body_mesh_is_plotted_in_enu_not_xyz():
    plotter=FlightPlotter()
    figure=plt.figure()
    try:
        axis=figure.add_subplot(111,projection='3d')
        # A right-hand +90-degree body-to-ENU Y rotation takes body +Z to East.
        quaternion=(math.sqrt(0.5),0,math.sqrt(0.5),0)
        rotation=plotter._quat_to_rot(quaternion)
        np.testing.assert_allclose(rotation @ np.array([0,0,1]),[1,0,0],atol=1e-12)
        assert np.linalg.det(rotation) > 0
        plotter._draw_rocket_attitude(axis,quaternion)
        assert (axis.get_xlabel(),axis.get_ylabel(),axis.get_zlabel())==('E','N','U')
    finally:
        plt.close(figure)
