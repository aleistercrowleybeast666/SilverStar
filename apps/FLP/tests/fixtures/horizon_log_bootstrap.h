#ifndef __HORIZON_LOG_BOOTSTRAP_H
#define __HORIZON_LOG_BOOTSTRAP_H

/* CPU fixture only. The generated configuration and Descriptor are exact;
 * device, preflight and clock values below are explicitly synthetic inputs. */
#include "project_log_decoder_profile.h"

_Static_assert(SYSTEM_IMU_OUTPUT_RATE_HZ == 200U && SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT == 2U,
    "This CPU producer supplies 10ms intervals for the declared 200Hz/two-sample configuration");

static void HorizonLog_RecordWrite(FlightLogRecord *record)
{
    uint8_t wire[284];
    uint16_t size = 0U;
    TEST_CHECK(FlightLog_RecordSerialize(record,s_test_wire_sequence++,wire,sizeof(wire),&size)
        == FLIGHT_LOG_SERIALIZE_RESULT_OK);
    TEST_CHECK(fwrite(wire,1U,size,s_test_wire) == size);
}

static void HorizonLog_BootstrapWrite(void)
{
    const uint8_t telemetry_tag[8] = SILVERSTAR_LOG_TELEMETRY_COMPATIBILITY_TAG;
    const uint8_t build_tag[] = SILVERSTAR_LOG_BUILD_TAG;
    FlightLogFileHeaderInfo info = {0};
    ProjectLogDecoderProfile profile;
    FlightLogRecord record = {0};
    uint8_t bytes[64];
    uint16_t length = 0U;
    info.profile_id = SYSTEM_LOG_PROFILE_ID;
    info.nominal_imu_rate_hz = SYSTEM_IMU_OUTPUT_RATE_HZ;
    info.nominal_ins_rate_hz = SYSTEM_IMU_OUTPUT_RATE_HZ / SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT;
    info.mechanization_subsample_count = SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT;
    info.coordinate_frame = 1U;
    info.position_axis_order[0] = 3U; info.position_axis_order[1] = 1U; info.position_axis_order[2] = 2U;
    info.quaternion_order = 1U; info.quaternion_semantics = 1U;
    info.local_gravity_mps2 = SYSTEM_LOCAL_GRAVITY_MPS2;
    info.firmware_version[0] = SILVERSTAR_VERSION_MAJOR; info.firmware_version[1] = SILVERSTAR_VERSION_MINOR;
    info.firmware_version[2] = SILVERSTAR_VERSION_PATCH; info.firmware_version[3] = SILVERSTAR_VERSION_BUILD;
    memcpy(info.air_compatibility_tag,telemetry_tag,8U); memcpy(info.build_tag,build_tag,8U);
    TEST_CHECK(FlightLog_FileHeaderSerialize(&info,bytes,sizeof(bytes),&length) == FLIGHT_LOG_SERIALIZE_RESULT_OK);
    TEST_CHECK(fwrite(bytes,1U,length,s_test_wire) == length);
    ProjectLogDecoderProfile_Get(&profile);
    record.record_type = FLIGHT_LOG_RECORD_DECODER_PROFILE_DESCRIPTOR;
    record.payload.decoder_profile_descriptor.package_schema_major = profile.package_schema_major;
    record.payload.decoder_profile_descriptor.package_schema_minor = profile.package_schema_minor;
    record.payload.decoder_profile_descriptor.container_format_major = profile.container_format_major;
    record.payload.decoder_profile_descriptor.container_format_minor = profile.container_format_minor;
    memcpy(record.payload.decoder_profile_descriptor.record_catalog_hash_128,profile.record_catalog_hash_128,16U);
    memcpy(record.payload.decoder_profile_descriptor.project_semantics_hash_128,profile.project_semantics_hash_128,16U);
    memcpy(record.payload.decoder_profile_descriptor.generation_profile_hash_128,profile.generation_profile_hash_128,16U);
    HorizonLog_RecordWrite(&record);
}

static void HorizonLog_MissionWrite(const float diagonal[6])
{
    FlightLogRecord record = {0};
    TEST_CHECK(LoggerBus_SystemConfigPush(10U) == LOGGER_BUS_RESULT_OK);
    HorizonTest_RecordsDrain();
    record.record_type = FLIGHT_LOG_RECORD_CALIBRATION_RESULT;
    record.timestamp_us = 20U;
    record.payload.calibration_result.state = 4U; record.payload.calibration_result.ready = 1U;
    for (uint32_t axis = 0U; axis < 3U; axis++)
    {
        record.payload.calibration_result.accel_scale[axis] = 1.0f;
        record.payload.calibration_result.gyro_scale[axis] = 1.0f;
    }
    HorizonLog_RecordWrite(&record);
    memset(&record,0,sizeof(record)); record.record_type = FLIGHT_LOG_RECORD_INITIAL_STATE;
    record.timestamp_us = 30U; record.payload.initial_state.q_nb[0] = 1.0f;
    record.payload.initial_state.origin_valid_flags = 1U;
    record.payload.initial_state.gnss_origin_latitude_e7 = 300000000;
    record.payload.initial_state.gnss_origin_longitude_e7 = 1200000000;
    memcpy(record.payload.initial_state.p0_diagonal,diagonal,6U*sizeof(float));
    HorizonLog_RecordWrite(&record);
    memset(&record,0,sizeof(record)); record.record_type = FLIGHT_LOG_RECORD_EVENT;
    record.timestamp_us = 1000000ULL; record.payload.event.event_id = FLIGHT_LOG_EVENT_MISSION_START;
    HorizonLog_RecordWrite(&record);
}

#endif
