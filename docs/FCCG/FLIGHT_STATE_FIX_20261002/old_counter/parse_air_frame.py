def parse_air_frame(frame: bytes) -> tuple[AirFrame, Any]:
    if len(frame) < 2:
        raise ValueError("AIR frame too short")

    air_type = int(frame[0])
    seq = int(frame[1])
    air = AirFrame(air_type=air_type, seq=seq, payload=bytes(frame[2:]), raw=bytes(frame))

    if air_type in (AirType.NAV_CAPABILITY, AirType.NAV_PREPARATION, AirType.NAV_HEALTH):
        if len(frame) != 9:
            raise ValueError(f"bad AIR navigation status length: {len(frame)}")
        session, generation = struct.unpack_from("<HH", frame, 2)
        if session == 0:
            raise ValueError("navigation status session must be nonzero")
        if air_type == AirType.NAV_CAPABILITY:
            return air, AirNavigationCapabilityMessage(seq, session, generation, *frame[6:9])
        if air_type == AirType.NAV_PREPARATION:
            return air, AirNavigationPreparationMessage(seq, session, generation, *frame[6:9])
        return air, AirNavigationHealthMessage(seq, session, generation, frame[6], struct.unpack_from("<H", frame, 7)[0])

    if air_type == AirType.FLIGHT_STATE:
        if len(frame) != AIR_FLIGHT_STATE_LEN:
            raise ValueError(f"bad AIR_FLIGHT_STATE length: {len(frame)}")
        prefix = parse_compact_v0_inertial_attitude_prefix(frame)
        vx, vy, vz, px, py, pz = struct.unpack_from("<ffffff", frame, AIR_PREFLIGHT_STATE_LEN)
        return air, AirFlightStateMessage(
            seq=prefix.seq,
            time_ms=prefix.time_ms,
            accel_raw=prefix.accel_raw,
            gyro_raw=prefix.gyro_raw,
            quat_q15=prefix.quat_q15,
            quat=prefix.quat,
            quat_raw_zero=prefix.quat_raw_zero,
            quat_valid=prefix.quat_valid,
            vel_mps=(float(vx), float(vy), float(vz)),
            pos_m=(float(px), float(py), float(pz)),
        )

    if air_type == AirType.PREFLIGHT_STATE:
        if len(frame) != AIR_PREFLIGHT_STATE_LEN:
            raise ValueError(f"bad AIR_PREFLIGHT_STATE length: {len(frame)}")
        prefix = parse_compact_v0_inertial_attitude_prefix(frame)
        return air, AirPreflightStateMessage(
            seq=prefix.seq,
            time_ms=prefix.time_ms,
            accel_raw=prefix.accel_raw,
            gyro_raw=prefix.gyro_raw,
            quat_q15=prefix.quat_q15,
            quat=prefix.quat,
            quat_raw_zero=prefix.quat_raw_zero,
            quat_valid=prefix.quat_valid,
        )

    if air_type == AirType.CAPABILITY:
        if len(frame) != AIR_CAPABILITY_LEN:
            raise ValueError(f"bad AIR_CAPABILITY length: {len(frame)}")
        _type, seq, profile, policy, calibration_mask, sensor_flags, accel_fs, gyro_fs = struct.unpack(
            "<BBBBBBBH", frame
        )
        return air, AirCapabilityMessage(
            seq=int(seq),
            air_profile_id=int(profile),
            command_policy=int(policy),
            calibration_mode_mask=int(calibration_mask),
            sensor_summary_flags=int(sensor_flags),
            accel_full_scale_g=int(accel_fs),
            gyro_full_scale_dps=int(gyro_fs),
        )

    if air_type == AirType.PREFLIGHT_STATUS:
        if len(frame) != AIR_PREFLIGHT_STATUS_LEN:
            raise ValueError(f"bad AIR_PREFLIGHT_STATUS length: {len(frame)}")
        calibration_byte = int(frame[3])
        alignment_byte = int(frame[6])
        flags = int(frame[7])
        calibration_mode_nibble = (calibration_byte >> 4) & 0x0F
        calibration_mode = 0xFF if calibration_mode_nibble == 0x0F else calibration_mode_nibble
        return air, AirPreflightStatusMessage(
            seq=seq,
            lifecycle_state=int(frame[2]),
            calibration_state=calibration_byte & 0x0F,
            calibration_mode=calibration_mode,
            completed_face_mask=int(frame[4]) & 0x3F,
            current_face=int(frame[5]),
            alignment_state=alignment_byte & 0x0F,
            system_ready=bool(flags & (1 << 0)),
            start_unlocked=bool(flags & (1 << 1)),
            selftest_passed=bool(flags & (1 << 2)),
            gnss_position_usable=bool(flags & (1 << 3)),
            capability_acked=bool(flags & (1 << 4)),
            calibration_ready=bool(flags & (1 << 5)),
            alignment_ready=bool(flags & (1 << 6)),
            start_block_reason=int(frame[8]),
        )

    if air_type == AirType.SENSOR_STATUS:
        if len(frame) != AIR_SENSOR_STATUS_LEN:
            raise ValueError(f"bad AIR_SENSOR_STATUS length: {len(frame)}")
        (
            _type,
            seq,
            snapshot_id,
            sensor_id,
            instance_id,
            status_flags,
            detail_code,
            index,
            total,
        ) = struct.unpack("<BBBBBBBBB", frame)
        if total == 0:
            raise ValueError("bad AIR_SENSOR_STATUS total: 0")
        if index >= total:
            raise ValueError(
                f"bad AIR_SENSOR_STATUS index/total: {index}/{total}"
            )
        return air, AirSensorStatusMessage(
            seq=int(seq),
            snapshot_id=int(snapshot_id),
            sensor_id=int(sensor_id),
            instance_id=int(instance_id),
            status_flags=int(status_flags),
            detail_code=int(detail_code),
            index=int(index),
            total=int(total),
        )

    if air_type == AirType.STATUS:
        if len(frame) != AIR_STATUS_LEN:
            raise ValueError(f"bad AIR_STATUS length: {len(frame)}")
        _type, seq, status_id, time_ms, arg0, arg1 = struct.unpack("<BBBIBB", frame)
        return air, AirStatusMessage(
            seq=int(seq),
            status_id=int(status_id),
            time_ms=int(time_ms),
            arg0=int(arg0),
            arg1=int(arg1),
        )

    if air_type == AirType.ACK:
        if len(frame) != AIR_ACK_LEN:
            raise ValueError(f"bad AIR_ACK length: {len(frame)}")
        _type, seq, ack_seq, ack_cmd_id, result, time_ms = struct.unpack("<BBBBBI", frame)
        return air, AirAckMessage(
            seq=int(seq),
            ack_seq=int(ack_seq),
            ack_cmd_id=int(ack_cmd_id),
            result=int(result),
            time_ms=int(time_ms),
        )

    if air_type == AirType.CMD:
        if len(frame) != AIR_CMD_LEN:
            raise ValueError(f"bad AIR_CMD length: {len(frame)}")
        _type, seq, cmd_id, token, param0, param1 = struct.unpack("<BBBIBB", frame)
        return air, AirCmdMessage(
            seq=int(seq),
            cmd_id=int(cmd_id),
            token=int(token),
            param0=int(param0),
            param1=int(param1),
        )

    raise ValueError(f"unknown AIR_TYPE: 0x{air_type:02X}")
