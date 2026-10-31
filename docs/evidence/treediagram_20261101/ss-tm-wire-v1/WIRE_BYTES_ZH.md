# SS-TM-S 当前逐字节定义

来源：`contracts/ss_tm_v0_1.json`。所有多字节量 little-endian，float 为 IEEE-754 binary32。偏移从完整帧第 0 字节起算；无应用层 CRC，链路硬件 CRC 仍启用。最大帧 61 B。S 是当前唯一生成配置；bit7=1 的 H 只保留历史解码/迁移语义。

## 公共头（8 B）

| offset | bytes | type | field | meaning |
|---:|---:|---|---|---|
| 0 | 1 | u8 | version | 0x01 |
| 1 | 1 | u8 | profile_type | bit7 S/H; bits0..6 message |
| 2 | 2 | u16 | tx_sequence | frame sequence modulo65536 |
| 4 | 4 | u32 | boot_session | nonzero FC boot identity; not authentication |

## FLIGHT_DATA (type 0x10, total 56 B)

| offset | bytes | type | field | unit / meaning |
|---:|---:|---|---|---|
| 8 | 4 | u32 | time_ms | ms monotonic |
| 12 | 6 | i16[3] | accel_i16 | configured full scale |
| 18 | 6 | i16[3] | gyro_i16 | configured full scale |
| 24 | 8 | i16[4] | quaternion_q15 | Body to ENU Hamilton wxyz |
| 32 | 12 | f32[3] | velocity_enu_mps | m/s |
| 44 | 12 | f32[3] | position_enu_m | m |

## PREFLIGHT_DATA (type 0x11, total 32 B)

| offset | bytes | type | field | unit / meaning |
|---:|---:|---|---|---|
| 8 | 4 | u32 | time_ms | ms monotonic |
| 12 | 6 | i16[3] | accel_i16 | configured full scale |
| 18 | 6 | i16[3] | gyro_i16 | configured full scale |
| 24 | 8 | i16[4] | quaternion_q15 | Body to ENU Hamilton wxyz |

## CAPABILITY (type 0x12, total 24 B)

| offset | bytes | type | field | unit / meaning |
|---:|---:|---|---|---|
| 8 | 1 | u8 | flight_encoding | 0 compact layout |
| 9 | 1 | u8 | command_policy | 1 preflight-only, 2 mission allowed |
| 10 | 1 | u8 | calibration_mode_mask | bits0..2 |
| 11 | 1 | u8 | sensor_summary_flags | bits0..3 |
| 12 | 1 | u8 | accel_full_scale_g | g |
| 13 | 2 | u16 | gyro_full_scale_dps | deg/s |
| 15 | 1 | u8 | preflight_flags | bit0 preflight advertisement, others0 |
| 16 | 8 | u64 | advertised_monotonic_us | us |

## PREFLIGHT_STATUS (type 0x13, total 15 B)

| offset | bytes | type | field | unit / meaning |
|---:|---:|---|---|---|
| 8 | 1 | u8 | lifecycle_state | lifecycle enum |
| 9 | 1 | u8 | calibration_state_mode | low nibble state, high mode; 15 not selected |
| 10 | 1 | u8 | completed_face_mask | 6 bits |
| 11 | 1 | u8 | current_face | 0..5 or255 |
| 12 | 1 | u8 | alignment_state | low nibble; upper0 |
| 13 | 1 | u8 | flags | preflight flags bits0..6 |
| 14 | 1 | u8 | start_block_reason | stable admission reason |

## SENSOR_STATUS (type 0x14, total 15 B)

| offset | bytes | type | field | unit / meaning |
|---:|---:|---|---|---|
| 8 | 1 | u8 | snapshot_id | transaction snapshot |
| 9 | 1 | u8 | sensor_id | stable physical type |
| 10 | 1 | u8 | instance_id | physical instance |
| 11 | 1 | u8 | status_flags | sensor flags |
| 12 | 1 | u8 | detail_code | sensor detail |
| 13 | 1 | u8 | index | ordinal |
| 14 | 1 | u8 | total | count |

## NAV_CAPABILITY (type 0x15, total 15 B)

| offset | bytes | type | field | unit / meaning |
|---:|---:|---|---|---|
| 8 | 2 | u16 | navigation_session | legacy navigation generation scope |
| 10 | 2 | u16 | generation | counter |
| 12 | 1 | u8 | schema | 1 |
| 13 | 1 | u8 | algorithm_id | navigation enum |
| 14 | 1 | u8 | group_mask | bits0..4 |

## NAV_PREPARATION (type 0x16, total 15 B)

| offset | bytes | type | field | unit / meaning |
|---:|---:|---|---|---|
| 8 | 2 | u16 | navigation_session | legacy navigation generation scope |
| 10 | 2 | u16 | generation | counter |
| 12 | 1 | u8 | required_mask | bits0..6 |
| 13 | 1 | u8 | ready_mask | bits0..6 |
| 14 | 1 | u8 | reason | start reason |

## NAV_HEALTH (type 0x17, total 15 B)

| offset | bytes | type | field | unit / meaning |
|---:|---:|---|---|---|
| 8 | 2 | u16 | navigation_session | legacy navigation generation scope |
| 10 | 2 | u16 | generation | counter |
| 12 | 1 | u8 | selector | navigation selector |
| 13 | 2 | u16 | value | selector-specific |

## POSITION (type 0x18, total 28 B)

| offset | bytes | type | field | unit / meaning |
|---:|---:|---|---|---|
| 8 | 4 | i32 | latitude_e7 | WGS84 deg*1e7 |
| 12 | 4 | i32 | longitude_e7 | WGS84 deg*1e7 |
| 16 | 4 | i32 | ellipsoid_height_mm | WGS84 ellipsoid mm |
| 20 | 4 | u32 | sample_age_ms | ms |
| 24 | 2 | u16 | horizontal_accuracy_cm | cm |
| 26 | 1 | u8 | position_flags | bits0..5 |
| 27 | 1 | u8 | satellite_count | count |

## HEALTH (type 0x19, total 16 B)

| offset | bytes | type | field | unit / meaning |
|---:|---:|---|---|---|
| 8 | 2 | u16 | battery_mv | mV |
| 10 | 2 | u16 | battery_age_ds | 0.1 s |
| 12 | 2 | u16 | known_mask | bits0..10 |
| 14 | 2 | u16 | fault_mask | subset of known |

## EVENT (type 0x20, total 32 B)

| offset | bytes | type | field | unit / meaning |
|---:|---:|---|---|---|
| 8 | 4 | u32 | event_id | nonzero unique within boot |
| 12 | 8 | u64 | occurred_us | original monotonic us |
| 20 | 2 | u16 | event_code | stable event code |
| 22 | 4 | u32 | stage_id | stable generated stage hash,0 unknown |
| 26 | 2 | u16 | instance_id | stable generated instance code,0 none |
| 28 | 2 | u16 | transaction_id | START/command sequence when event declares it |
| 30 | 1 | u8 | arg0 | event-specific |
| 31 | 1 | u8 | arg1 | event-specific |

## CMD (type 0x30, total 15 B)

| offset | bytes | type | field | unit / meaning |
|---:|---:|---|---|---|
| 8 | 1 | u8 | command_id | legacy stable command ID |
| 9 | 4 | u32 | token | admission token, not authentication |
| 13 | 1 | u8 | param0 | command-specific; CAP_ACK correlation low byte |
| 14 | 1 | u8 | param1 | command-specific; CAP_ACK correlation high byte |

## ACK (type 0x40, total 16 B)

| offset | bytes | type | field | unit / meaning |
|---:|---:|---|---|---|
| 8 | 2 | u16 | acked_sequence | full command frame sequence |
| 10 | 1 | u8 | command_id | stable command ID |
| 11 | 1 | u8 | result | stable result |
| 12 | 4 | u32 | time_ms | monotonic ms modulo2^32 |

## position_flags

| name | value |
|---|---|
| POSITION_VALID | 1 |
| HEIGHT_VALID | 2 |
| CURRENT_FIX_USABLE | 4 |
| AGE_FROM_MEASUREMENT | 8 |
| RETAINED_FIX | 16 |
| QUALITY_DEGRADED | 32 |

## invalid

| name | value |
|---|---|
| coordinate | -2147483648 |
| height | -2147483648 |
| age_unknown | 4294967295 |
| age_saturated | 4294967294 |
| accuracy_unknown | 65535 |
| accuracy_saturated | 65534 |
| satellite_count_unknown | 255 |
| battery_unknown | 65535 |
| battery_age_unknown | 65535 |
| battery_age_saturated | 65534 |

## events

| name | value |
|---|---|
| BOOT | 1 |
| SELFTEST_COMPLETE | 2 |
| MISSION_START | 3 |
| LAUNCH | 4 |
| PARACHUTE_DEPLOY | 5 |
| LANDED | 6 |
| LOCKED | 7 |
| UNLOCKED | 8 |
| GNSS_USABILITY | 9 |
| ALIGNMENT | 10 |
| CALIBRATION | 11 |
| CALIBRATION_FACE | 12 |
| CALIBRATION_DIAGNOSTIC | 13 |
| STAGE_ENTER | 256 |
| STAGE_EXIT | 257 |
| FUNCTION_START | 512 |
| FUNCTION_COMPLETE | 513 |
| FUNCTION_FAILED | 514 |

## queue

| name | value |
|---|---|
| event_depth | 16 |
| event_transmissions | 3 |
| event_expiry_us | 30000000 |
| periodic_latest_only | True |

## phy_baseline

| name | value |
|---|---|
| spreading_factor | 10 |
| bandwidth_label_hz | 800000 |
| bandwidth_calculation_hz | 812500 |
| coding_rate | 4/5 |
| preamble_symbols | 16 |
| header | explicit |
| crc | True |

## HEALTH known/fault bit indices

| bit | meaning |
|---:|---|
| 0 | power |
| 1 | primary_imu |
| 2 | gnss |
| 3 | barometer |
| 4 | magnetometer |
| 5 | estimator |
| 6 | storage |
| 7 | logger |
| 8 | telemetry_tx |
| 9 | scheduler |
| 10 | configuration_calibration |
