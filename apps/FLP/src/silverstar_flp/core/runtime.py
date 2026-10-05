"""Reject a known leaking numerical runtime before replay work starts."""

from __future__ import annotations

import sys

import numpy as np


def NumericalRuntime_Validate() -> None:
    # Exclude only the confirmed bad release, including its local-build suffix.
    if np.__version__.split("+", 1)[0] == "2.4.0":
        raise RuntimeError(
            "numpy_version_unsafe:NumPy 2.4.0 has a known memory leak in np.eye/flat assignment. "
            "Install a fixed NumPy release in the FLP environment (validated: 2.4.1) before "
            f"starting replay. Python: {sys.executable}. "
            "https://github.com/numpy/numpy/pull/30512"
        )
