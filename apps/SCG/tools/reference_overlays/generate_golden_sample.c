#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "project_log_decoder_profile.h"
#include "sslog_protocol.h"
#include "system_user_config.h"

static const FlightLogRecordType s_golden_record_types[] =
{
    FLIGHT_LOG_RECORD_DECODER_PROFILE_DESCRIPTOR,
    FLIGHT_LOG_RECORD_SYSTEM_CONFIG,
    FLIGHT_LOG_RECORD_DEVICE_DESCRIPTOR,
    FLIGHT_LOG_RECORD_LOG_STREAM_DESCRIPTOR,
    FLIGHT_LOG_RECORD_IMU_CORRECTED,
    FLIGHT_LOG_RECORD_GNSS_NATIVE,
    FLIGHT_LOG_RECORD_BARO_NATIVE,
    FLIGHT_LOG_RECORD_EVENT,
    FLIGHT_LOG_RECORD_STATS,
    FLIGHT_LOG_RECORD_TELEMETRY_DIAG,
    FLIGHT_LOG_RECORD_INERTIAL_INCREMENT,
    FLIGHT_LOG_RECORD_PURE_INS,
    FLIGHT_LOG_RECORD_ESTIMATOR
};

static void GoldenSample_DecoderProfileSet(FlightLogRecord *record)
{
    ProjectLogDecoderProfile profile;
    FlightLogDecoderProfileDescriptorRecord *descriptor =
        &record->payload.decoder_profile_descriptor;

    ProjectLogDecoderProfile_Get(&profile);
    descriptor->package_schema_major = profile.package_schema_major;
    descriptor->package_schema_minor = profile.package_schema_minor;
    descriptor->container_format_major = profile.container_format_major;
    descriptor->container_format_minor = profile.container_format_minor;
    (void)memcpy(descriptor->record_catalog_hash_128,
        profile.record_catalog_hash_128,
        sizeof(descriptor->record_catalog_hash_128));
    (void)memcpy(descriptor->project_semantics_hash_128,
        profile.project_semantics_hash_128,
        sizeof(descriptor->project_semantics_hash_128));
    (void)memcpy(descriptor->generation_profile_hash_128,
        profile.generation_profile_hash_128,
        sizeof(descriptor->generation_profile_hash_128));
}

static void GoldenSample_RecordPrepare(
    FlightLogRecordType record_type, uint32_t sequence,
    FlightLogRecord *record)
{
    (void)memset(record, 0, sizeof(*record));
    record->record_type = record_type;
    record->timestamp_us = 1000000ULL + ((uint64_t)sequence * 100000ULL);
    record->valid_flags = 1UL;
    switch (record_type)
    {
        case FLIGHT_LOG_RECORD_DECODER_PROFILE_DESCRIPTOR:
            GoldenSample_DecoderProfileSet(record);
            break;
        case FLIGHT_LOG_RECORD_SYSTEM_CONFIG:
            record->payload.system_config.version[0] = 0U;
            record->payload.system_config.version[1] = 0U;
            record->payload.system_config.version[2] = SILVERSTAR_VERSION_PATCH;
            record->payload.system_config.profile_id = 1UL;
            record->payload.system_config.configured_imu_rate_hz = 100U;
            record->payload.system_config.configured_gnss_rate_hz = 10U;
            record->payload.system_config.device_descriptor_count = 13U;
            record->payload.system_config.log_stream_descriptor_count =
                SSLOG_RECORD_COUNT;
            break;
        case FLIGHT_LOG_RECORD_DEVICE_DESCRIPTOR:
            record->payload.device_descriptor.descriptor_id = 1U;
            record->payload.device_descriptor.physical_device_id = 1U;
            record->payload.device_descriptor.device_class = 1U;
            record->payload.device_descriptor.instance_id = 0U;
            record->payload.device_descriptor.configured_rate_hz = 100UL;
            break;
        case FLIGHT_LOG_RECORD_LOG_STREAM_DESCRIPTOR:
            record->payload.stream_descriptor.record_type =
                (uint8_t)FLIGHT_LOG_RECORD_IMU_CORRECTED;
            record->payload.stream_descriptor.enabled = 1U;
            record->payload.stream_descriptor.policy =
                (uint8_t)SSLOG_STREAM_POLICY_DECIMATION;
            record->payload.stream_descriptor.decimation = 1U;
            break;
        case FLIGHT_LOG_RECORD_IMU_CORRECTED:
            record->payload.imu_corrected.source_id = 1U;
            record->payload.imu_corrected.virtual_imu_id = 0U;
            record->payload.imu_corrected.sequence = sequence;
            record->payload.imu_corrected.sample_timestamp_us =
                record->timestamp_us;
            record->payload.imu_corrected.accel_b_mps2[2] = 9.80665f;
            record->payload.imu_corrected.valid_mask = 0x3FUL;
            break;
        case FLIGHT_LOG_RECORD_GNSS_NATIVE:
            record->payload.gnss_native.source_descriptor_id = 2U;
            record->payload.gnss_native.instance_id = 0U;
            record->payload.gnss_native.sequence = sequence;
            record->payload.gnss_native.sample_timestamp_us =
                record->timestamp_us;
            record->payload.gnss_native.latitude_e7 = 320000000;
            record->payload.gnss_native.longitude_e7 = 1180000000;
            record->payload.gnss_native.fix_type = 3U;
            record->payload.gnss_native.position_usable = 1U;
            record->payload.gnss_native.online = 1U;
            break;
        case FLIGHT_LOG_RECORD_BARO_NATIVE:
            record->payload.baro_native.source_descriptor_id = 3U;
            record->payload.baro_native.instance_id = 0U;
            record->payload.baro_native.sequence = sequence;
            record->payload.baro_native.sample_timestamp_us =
                record->timestamp_us;
            record->payload.baro_native.pressure_pa = 101325.0f;
            record->payload.baro_native.valid_mask = 3UL;
            break;
        case FLIGHT_LOG_RECORD_EVENT:
            record->payload.event.event_id = FLIGHT_LOG_EVENT_BOOT;
            record->payload.event.arg0 = 0x53534C47UL;
            break;
        case FLIGHT_LOG_RECORD_STATS:
            record->payload.stats.ins_update_count = 1000UL;
            break;
        case FLIGHT_LOG_RECORD_TELEMETRY_DIAG:
            record->payload.telemetry_diagnostic.transmit_packet_count = 10UL;
            record->payload.telemetry_diagnostic.receive_packet_count = 8UL;
            record->payload.telemetry_diagnostic.last_rssi_dbm = -72;
            record->payload.telemetry_diagnostic.online = 1U;
            break;
        case FLIGHT_LOG_RECORD_INERTIAL_INCREMENT:
            record->payload.inertial_increment.sequence = sequence;
            record->payload.inertial_increment.interval_end_timestamp_us = record->timestamp_us;
            record->payload.inertial_increment.interval_start_timestamp_us = record->timestamp_us - 10000ULL;
            record->payload.inertial_increment.dt_s = 0.01f;
            break;
        case FLIGHT_LOG_RECORD_PURE_INS:
            record->payload.pure_ins.update_sequence = sequence;
            record->payload.pure_ins.q_nb[0] = 1.0f;
            record->payload.pure_ins.alignment_valid = 1U;
            record->payload.pure_ins.ins_valid = 1U;
            break;
        case FLIGHT_LOG_RECORD_ESTIMATOR:
            record->payload.estimator.initialized = 1U;
            record->payload.estimator.gnss_origin_valid = 1U;
            record->payload.estimator.baro_origin_valid = 1U;
            break;
        default:
            break;
    }
}

static int GoldenSample_FileWrite(const char *path)
{
    FILE *file;
    FlightLogFileHeaderInfo header;
    FlightLogRecord record;
    FlightLogRecord decoded_record;
    uint8_t buffer[FLIGHT_LOG_MAX_RECORD_SIZE];
    uint16_t size;
    uint16_t decoded_size;
    uint32_t index;
    uint32_t decoded_sequence;

    file = fopen(path, "wb");
    if (file == NULL) { return 1; }
    (void)memset(&header, 0, sizeof(header));
    header.profile_id = 1U;
    header.nominal_imu_rate_hz = 100U;
    header.nominal_ins_rate_hz = 100U;
    header.position_axis_order[0] = 0U;
    header.position_axis_order[1] = 1U;
    header.position_axis_order[2] = 2U;
    header.local_gravity_mps2 = 9.80665f;
    header.firmware_version[2] = SILVERSTAR_VERSION_PATCH;
    if (FlightLog_FileHeaderSerialize(&header, buffer, sizeof(buffer), &size) !=
        FLIGHT_LOG_SERIALIZE_RESULT_OK)
    {
        (void)fclose(file);
        return 2;
    }
    if (fwrite(buffer, 1U, size, file) != size)
    {
        (void)fclose(file);
        return 3;
    }
    for (index = 0U;
         index < (sizeof(s_golden_record_types) /
                  sizeof(s_golden_record_types[0]));
         index++)
    {
        GoldenSample_RecordPrepare(
            s_golden_record_types[index], index + 1U, &record);
        if (FlightLog_RecordSerialize(
                &record, index + 1U, buffer, sizeof(buffer), &size) !=
            FLIGHT_LOG_SERIALIZE_RESULT_OK)
        {
            (void)fclose(file);
            return 4;
        }
        if ((FlightLog_RecordDeserialize(
                 buffer, size, &decoded_record, &decoded_sequence,
                 &decoded_size) != FLIGHT_LOG_DESERIALIZE_RESULT_OK) ||
            (decoded_sequence != (index + 1U)) ||
            (decoded_size != size) ||
            (decoded_record.record_type != record.record_type))
        {
            (void)fclose(file);
            return 5;
        }
        if (fwrite(buffer, 1U, size, file) != size)
        {
            (void)fclose(file);
            return 6;
        }
    }
    return (fclose(file) == 0) ? 0 : 7;
}

int main(void)
{
    const char *path = getenv("SILVERSTAR_GOLDEN_OUTPUT");
    int result;

    if ((path == NULL) || (path[0] == '\0'))
    {
        (void)fprintf(stderr, "SILVERSTAR_GOLDEN_OUTPUT is not set\n");
        return 1;
    }
    result = GoldenSample_FileWrite(path);
    if (result != 0)
    {
        (void)fprintf(stderr, "Golden Sample write failed: %d\n", result);
        return result;
    }
    (void)printf("golden_sample: 1 checks, 0 failures\n");
    return 0;
}
