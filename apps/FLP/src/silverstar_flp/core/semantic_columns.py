"""Audited SilverStar labels; no sample reordering or transformation."""

from __future__ import annotations


def SemanticColumns_Get(record_name: str, field_name: str, count: int) -> tuple[str, ...]:
    record = record_name.upper()
    field = field_name.lower()
    if count == 4 and field in {"q_nb", "q_raw", "q_nb0", "quaternion_wxyz", "quat_raw_q15"}:
        return ("W", "X", "Y", "Z")
    if count == 3:
        if any(name in field for name in ("position_enu", "velocity_enu", "accel_enu")):
            return ("E", "N", "U")
        if "_b_" in field or field.endswith("_b"):
            return ("X", "Y", "Z")
        if record in {
            "IMU_NATIVE",
            "MAG_NATIVE",
            "SAMPLE",
            "RAW_SENSOR",
            "CALIBRATION_RESULT",
        } and field.startswith(("acc", "gyro", "mag")):
            return ("X", "Y", "Z")
        if record in {"KF6_DIAGNOSTIC", "GNSS_NATIVE", "SYSTEM_CONFIG", "INITIAL_STATE"} and (
            field
            in {
                "position_innovation",
                "velocity_innovation",
                "position_variance_r",
                "velocity_variance_r",
                "velocity_variance_m2ps2",
                "process_accel_std_mps2",
                "gnss_origin_position_std_m",
                "initial_velocity_std_mps",
            }
        ):
            return ("E", "N", "U")
        if field.startswith("euler"):
            return ("Roll", "Pitch", "Yaw")
    # Audited recorded/offline KF6 contract: position first. Explicit metadata wins.
    if count == 6 and record in {"ESTIMATOR", "KF6_STATE", "INITIAL_STATE", "SYSTEM_CONFIG"}:
        if field in {"state", "state_vector", "x"}:
            return ("xE", "xN", "xU", "vE", "vN", "vU")
        if field in {"covariance_diagonal", "p0_diagonal"}:
            return ("PxE", "PxN", "PxU", "PvE", "PvN", "PvU")
    return tuple(f"[{index}]" for index in range(count)) if count > 1 else ()
