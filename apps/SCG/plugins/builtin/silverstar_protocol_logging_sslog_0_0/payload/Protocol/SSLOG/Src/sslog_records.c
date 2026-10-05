/* SSLOG record metadata and explicit little-endian wire codecs.
 *
 * Payloads are serialized field by field.  C structure layout is never used
 * as the on-storage representation.
 */
#include "sslog_protocol.h"

#include "silverstar_assert.h"

#include <stddef.h>
#include <string.h>

static const SslogRecordMetadata s_sslog_metadata[] =
{
    { FLIGHT_LOG_RECORD_SF6_STATE, 1U, FLIGHT_LOG_SF6_STATE_PAYLOAD_SIZE, "SF6_STATE" },
    { FLIGHT_LOG_RECORD_SF6_MEASUREMENT, 1U, FLIGHT_LOG_SF6_MEASUREMENT_PAYLOAD_SIZE, "SF6_MEASUREMENT" },

    { FLIGHT_LOG_RECORD_MAG_CALIBRATION_IDENTITY, 1U,
      FLIGHT_LOG_MAG_CALIBRATION_IDENTITY_PAYLOAD_SIZE,
      "MAG_CALIBRATION_IDENTITY" },
    { FLIGHT_LOG_RECORD_MISSION_SNAPSHOT_IDENTITY, 1U,
      FLIGHT_LOG_MISSION_SNAPSHOT_IDENTITY_PAYLOAD_SIZE,
      "MISSION_SNAPSHOT_IDENTITY" },
    { FLIGHT_LOG_RECORD_ALIGNMENT_EVIDENCE, 1U,
      FLIGHT_LOG_ALIGNMENT_EVIDENCE_PAYLOAD_SIZE, "ALIGNMENT_EVIDENCE" },
    { FLIGHT_LOG_RECORD_NAV_QUALITY, 1U, FLIGHT_LOG_NAV_QUALITY_PAYLOAD_SIZE, "NAV_QUALITY" },
    { FLIGHT_LOG_RECORD_ESKF15_BODY_INPUT, 1U, FLIGHT_LOG_ESKF15_BODY_INPUT_PAYLOAD_SIZE, "ESKF15_BODY_INPUT" },
    { FLIGHT_LOG_RECORD_ESKF15_STATE, 1U, FLIGHT_LOG_ESKF15_STATE_PAYLOAD_SIZE, "ESKF15_STATE" },
    { FLIGHT_LOG_RECORD_ESKF15_FULL_P_PART, 1U, FLIGHT_LOG_ESKF15_FULL_P_PART_PAYLOAD_SIZE, "ESKF15_FULL_P_PART" },
    { FLIGHT_LOG_RECORD_ESKF15_INITIAL_STATE, 1U, FLIGHT_LOG_ESKF15_INITIAL_STATE_PAYLOAD_SIZE, "ESKF15_INITIAL_STATE" },
    { FLIGHT_LOG_RECORD_ESKF15_INITIAL_P_PART, 1U, FLIGHT_LOG_ESKF15_INITIAL_P_PART_PAYLOAD_SIZE, "ESKF15_INITIAL_P_PART" },
    { FLIGHT_LOG_RECORD_ESKF15_MEASUREMENT, 1U, FLIGHT_LOG_ESKF15_MEASUREMENT_PAYLOAD_SIZE, "ESKF15_MEASUREMENT" },

    { FLIGHT_LOG_RECORD_LANDING_DIAGNOSTIC, 0U, FLIGHT_LOG_LANDING_DIAGNOSTIC_PAYLOAD_SIZE, "LANDING_DIAGNOSTIC" },
    { FLIGHT_LOG_RECORD_GNSS_RECOVERY, 1U, FLIGHT_LOG_GNSS_RECOVERY_PAYLOAD_SIZE, "GNSS_RECOVERY" },
    { FLIGHT_LOG_RECORD_ESTIMATOR_STEP, 0U, FLIGHT_LOG_ESTIMATOR_STEP_PAYLOAD_SIZE, "ESTIMATOR_STEP" },
    {
        FLIGHT_LOG_RECORD_EVENT, 0U,
        FLIGHT_LOG_EVENT_PAYLOAD_SIZE, "EVENT"
    },
    {
        FLIGHT_LOG_RECORD_STATS, 0U,
        FLIGHT_LOG_STATS_PAYLOAD_SIZE, "STATS"
    },
    {
        FLIGHT_LOG_RECORD_ESTIMATOR, 1U,
        FLIGHT_LOG_ESTIMATOR_PAYLOAD_SIZE, "ESTIMATOR"
    },
    {
        FLIGHT_LOG_RECORD_SYSTEM_CONFIG, 0U,
        FLIGHT_LOG_SYSTEM_CONFIG_PAYLOAD_SIZE, "SYSTEM_CONFIG"
    },
    {
        FLIGHT_LOG_RECORD_PURE_INS, 0U,
        FLIGHT_LOG_PURE_INS_PAYLOAD_SIZE, "PURE_INS"
    },
    {
        FLIGHT_LOG_RECORD_KF6_DIAGNOSTIC, 0U,
        FLIGHT_LOG_KF6_DIAGNOSTIC_PAYLOAD_SIZE, "KF6_DIAGNOSTIC"
    },
    {
        FLIGHT_LOG_RECORD_KF6_FULL_P, 0U,
        FLIGHT_LOG_KF6_FULL_P_PAYLOAD_SIZE, "KF6_FULL_P"
    },
    {
        FLIGHT_LOG_RECORD_POWER, 0U,
        FLIGHT_LOG_POWER_PAYLOAD_SIZE, "POWER"
    },
    {
        FLIGHT_LOG_RECORD_HEALTH, 0U,
        FLIGHT_LOG_HEALTH_PAYLOAD_SIZE, "HEALTH"
    },
    {
        FLIGHT_LOG_RECORD_TELEMETRY_DIAG, 0U,
        FLIGHT_LOG_TELEMETRY_DIAG_PAYLOAD_SIZE, "TELEMETRY_DIAG"
    },
    {
        FLIGHT_LOG_RECORD_INITIAL_STATE, 0U,
        FLIGHT_LOG_INITIAL_STATE_PAYLOAD_SIZE, "INITIAL_STATE"
    },
    {
        FLIGHT_LOG_RECORD_GNSS_NATIVE, 1U,
        FLIGHT_LOG_GNSS_NATIVE_PAYLOAD_SIZE, "GNSS_NATIVE"
    },
    {
        FLIGHT_LOG_RECORD_BARO_NATIVE, 1U,
        FLIGHT_LOG_BARO_NATIVE_PAYLOAD_SIZE, "BARO_NATIVE"
    },
    {
        FLIGHT_LOG_RECORD_MAG_NATIVE, 0U,
        FLIGHT_LOG_MAG_NATIVE_PAYLOAD_SIZE, "MAG_NATIVE"
    },
    {
        FLIGHT_LOG_RECORD_INERTIAL_INCREMENT, 0U,
        FLIGHT_LOG_INERTIAL_INCREMENT_PAYLOAD_SIZE, "INERTIAL_INCREMENT"
    },
    {
        FLIGHT_LOG_RECORD_GNSS_MEASUREMENT, 1U,
        FLIGHT_LOG_GNSS_MEASUREMENT_PAYLOAD_SIZE, "GNSS_MEASUREMENT"
    },
    {
        FLIGHT_LOG_RECORD_BARO_MEASUREMENT, 1U,
        FLIGHT_LOG_BARO_MEASUREMENT_PAYLOAD_SIZE, "BARO_MEASUREMENT"
    },
    {
        FLIGHT_LOG_RECORD_IMU_CORRECTED, 0U,
        FLIGHT_LOG_IMU_CORRECTED_PAYLOAD_SIZE, "IMU_CORRECTED"
    },
    {
        FLIGHT_LOG_RECORD_CALIBRATION_RESULT, 0U,
        FLIGHT_LOG_CALIBRATION_RESULT_PAYLOAD_SIZE, "CALIBRATION_RESULT"
    },
    {
        FLIGHT_LOG_RECORD_ALIGNMENT_RESULT, 0U,
        FLIGHT_LOG_ALIGNMENT_RESULT_PAYLOAD_SIZE, "ALIGNMENT_RESULT"
    },
    {
        FLIGHT_LOG_RECORD_MISSION_CONFIG, 0U,
        FLIGHT_LOG_MISSION_CONFIG_PAYLOAD_SIZE, "MISSION_CONFIG"
    },
    {
        FLIGHT_LOG_RECORD_DEVICE_DESCRIPTOR, 0U,
        FLIGHT_LOG_DEVICE_DESCRIPTOR_PAYLOAD_SIZE, "DEVICE_DESCRIPTOR"
    },
    {
        FLIGHT_LOG_RECORD_ALGORITHM_DESCRIPTOR, 0U,
        FLIGHT_LOG_ALGORITHM_DESCRIPTOR_PAYLOAD_SIZE,
        "ALGORITHM_DESCRIPTOR"
    },
    {
        FLIGHT_LOG_RECORD_LOG_STREAM_DESCRIPTOR, 0U,
        FLIGHT_LOG_STREAM_DESCRIPTOR_PAYLOAD_SIZE,
        "LOG_STREAM_DESCRIPTOR"
    },
    {
        FLIGHT_LOG_RECORD_DECODER_PROFILE_DESCRIPTOR, 0U,
        FLIGHT_LOG_DECODER_PROFILE_DESCRIPTOR_PAYLOAD_SIZE,
        "DECODER_PROFILE_DESCRIPTOR"
    },
};

_Static_assert((sizeof(s_sslog_metadata) / sizeof(s_sslog_metadata[0])) ==
               SSLOG_RECORD_COUNT, "SSLOG metadata count mismatch");

static void SslogRecords_U16Put(uint8_t *buffer, uint16_t value)
{
    buffer[0] = (uint8_t)(value & 0xFFU);
    buffer[1] = (uint8_t)((value >> 8U) & 0xFFU);
}

static void SslogRecords_U32Put(uint8_t *buffer, uint32_t value)
{
    buffer[0] = (uint8_t)(value & 0xFFU);
    buffer[1] = (uint8_t)((value >> 8U) & 0xFFU);
    buffer[2] = (uint8_t)((value >> 16U) & 0xFFU);
    buffer[3] = (uint8_t)((value >> 24U) & 0xFFU);
}

static void SslogRecords_U64Put(uint8_t *buffer, uint64_t value)
{
    uint8_t index;
    for (index = 0U; index < 8U; index++)
    {
        buffer[index] = (uint8_t)((value >> (8U * index)) & 0xFFU);
    }
}

static void SslogRecords_F32Put(uint8_t *buffer, float value)
{
    uint32_t bits;
    (void)memcpy(&bits, &value, sizeof(bits));
    SslogRecords_U32Put(buffer, bits);
}

static uint16_t SslogRecords_U16Get(const uint8_t *buffer)
{
    return (uint16_t)((uint16_t)buffer[0] |
        ((uint16_t)buffer[1] << 8U));
}

static uint32_t SslogRecords_U32Get(const uint8_t *buffer)
{
    return (uint32_t)buffer[0] |
        ((uint32_t)buffer[1] << 8U) |
        ((uint32_t)buffer[2] << 16U) |
        ((uint32_t)buffer[3] << 24U);
}

static uint64_t SslogRecords_U64Get(const uint8_t *buffer)
{
    uint64_t value = 0U;
    uint8_t index;

    for (index = 0U; index < 8U; index++)
    {
        value |= ((uint64_t)buffer[index] << (8U * index));
    }
    return value;
}

static float SslogRecords_F32Get(const uint8_t *buffer)
{
    uint32_t bits = SslogRecords_U32Get(buffer);
    float value;

    (void)memcpy(&value, &bits, sizeof(value));
    return value;
}

typedef struct
{
    uint8_t *buffer;
    uint16_t capacity;
    uint16_t offset;
} SslogWriteCursor;

typedef struct
{
    const uint8_t *buffer;
    uint16_t size;
    uint16_t offset;
} SslogReadCursor;

static uint8_t *SslogRecords_WriteReserve(SslogWriteCursor *writer,
    uint16_t width)
{
    uint8_t *field;
    uint16_t capacity;
    uint16_t offset;

    SILVERSTAR_ASSERT(writer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    capacity = writer->capacity;
    offset = writer->offset;
    SILVERSTAR_ASSERT((offset <= capacity) &&
                      (width <= (uint16_t)(capacity - offset)),
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    field = &writer->buffer[offset];
    writer->offset = (uint16_t)(offset + width);
    return field;
}

static const uint8_t *SslogRecords_ReadReserve(SslogReadCursor *reader,
    uint16_t width)
{
    const uint8_t *field;
    uint16_t offset;
    uint16_t size;

    SILVERSTAR_ASSERT(reader != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    size = reader->size;
    offset = reader->offset;
    SILVERSTAR_ASSERT((offset <= size) &&
                      (width <= (uint16_t)(size - offset)),
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    field = &reader->buffer[offset];
    reader->offset = (uint16_t)(offset + width);
    return field;
}

static void SslogRecords_WriterU8Put(SslogWriteCursor *writer, uint8_t value)
{
    uint8_t *field = SslogRecords_WriteReserve(writer, 1U);
    field[0] = value;
}

static void SslogRecords_WriterZero(SslogWriteCursor *writer, uint16_t width)
{
    uint8_t *field = SslogRecords_WriteReserve(writer, width);
    (void)memset(field, 0, width);
}

static void SslogRecords_WriterU16Put(SslogWriteCursor *writer, uint16_t value)
{
    SslogRecords_U16Put(SslogRecords_WriteReserve(writer, 2U), value);
}

static void SslogRecords_WriterU32Put(SslogWriteCursor *writer, uint32_t value)
{
    SslogRecords_U32Put(SslogRecords_WriteReserve(writer, 4U), value);
}

static void SslogRecords_WriterU64Put(SslogWriteCursor *writer, uint64_t value)
{
    SslogRecords_U64Put(SslogRecords_WriteReserve(writer, 8U), value);
}

static void SslogRecords_WriterF32Put(SslogWriteCursor *writer, float value)
{
    SslogRecords_F32Put(SslogRecords_WriteReserve(writer, 4U), value);
}

static uint8_t SslogRecords_ReaderU8Get(SslogReadCursor *reader)
{
    return SslogRecords_ReadReserve(reader, 1U)[0];
}

static void SslogRecords_ReaderSkip(SslogReadCursor *reader, uint16_t width)
{
    (void)SslogRecords_ReadReserve(reader, width);
}

static uint16_t SslogRecords_ReaderU16Get(SslogReadCursor *reader)
{
    return SslogRecords_U16Get(SslogRecords_ReadReserve(reader, 2U));
}

static uint32_t SslogRecords_ReaderU32Get(SslogReadCursor *reader)
{
    return SslogRecords_U32Get(SslogRecords_ReadReserve(reader, 4U));
}

static uint64_t SslogRecords_ReaderU64Get(SslogReadCursor *reader)
{
    return SslogRecords_U64Get(SslogRecords_ReadReserve(reader, 8U));
}

static float SslogRecords_ReaderF32Get(SslogReadCursor *reader)
{
    return SslogRecords_F32Get(SslogRecords_ReadReserve(reader, 4U));
}

uint16_t SslogRecords_RecordCountGet(void)
{
    return SSLOG_RECORD_COUNT;
}

const SslogRecordMetadata *SslogRecords_MetadataByIndexGet(
    uint16_t index)
{
    return (index < SSLOG_RECORD_COUNT) ? &s_sslog_metadata[index] : NULL;
}

const SslogRecordMetadata *SslogRecords_MetadataGet(
    FlightLogRecordType record_type)
{
    uint16_t index;
    for (index = 0U; index < SSLOG_RECORD_COUNT; index++)
    {
        if (s_sslog_metadata[index].record_type == record_type)
        {
            return &s_sslog_metadata[index];
        }
    }
    return NULL;
}

static uint16_t SslogRecords_EventSerialize(
    const FlightLogEventRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->event_id));
    SslogRecords_WriterZero(&writer, 3U);
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->arg0));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->arg1));

    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_StatsSerialize(
    const FlightLogStatsRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->imu_queue_overflow_count));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->logger_queue_overflow_count));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->ins_update_count));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->health_flags));

    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static void SslogRecords_EstimatorMotionSerialize(
    const FlightLogEstimatorRecord *payload,
    SslogWriteCursor *cursor)
{
    SILVERSTAR_ASSERT_OBJECT(payload, FlightLogEstimatorRecord, SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    SILVERSTAR_ASSERT(cursor != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL, SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    for (uint16_t index = 0U; index < 4U; index++)
    {
        SslogRecords_WriterF32Put(cursor, payload->q_nb[index]);
    }
    for (uint16_t index = 0U; index < 3U; index++)
    {
        SslogRecords_WriterF32Put(cursor, payload->acceleration_enu_mps2[index]);
    }
}

static uint16_t SslogRecords_EstimatorSerialize(
    const FlightLogEstimatorRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->position_enu_m[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->velocity_enu_mps[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 6U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->covariance_diagonal[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->gnss_position_enu_m[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->gnss_velocity_enu_mps[field_index]);
    }
    SslogRecords_WriterF32Put(&writer, payload->baro_relative_altitude_m);
    SslogRecords_WriterF32Put(&writer, payload->last_position_nis);
    SslogRecords_WriterF32Put(&writer, payload->last_velocity_nis);
    SslogRecords_WriterF32Put(&writer, payload->last_baro_nis);
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->measurement_result_flags));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->health_flags));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->prediction_queue_overflow_count));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->gnss_sequence));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->baro_sequence));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->gnss_timestamp_us));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->baro_timestamp_us));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->gnss_measurement_age_us));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->baro_measurement_age_us));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->gnss_origin_valid));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->baro_origin_valid));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->initialized));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->mission_running));

    SslogRecords_EstimatorMotionSerialize(payload, &writer);
    SslogRecords_WriterU32Put(&writer, payload->operation_sequence);
    SslogRecords_WriterU32Put(&writer, payload->replay_epoch);
    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_SystemConfigSerialize(
    const FlightLogSystemConfigRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    for (uint16_t field_index = 0U; field_index < 4U; field_index++)
    {
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->version[field_index]));
    }
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->profile_id));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->device_config_digest));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->configured_imu_rate_hz));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->configured_gnss_rate_hz));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->configured_magnetometer_rate_hz));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->configured_barometer_rate_hz));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->configured_hardware_quaternion_rate_hz));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->mechanization_subsample_count));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->expected_ins_rate_hz));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->mechanization_min_sample_rate_hz));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->mechanization_max_sample_rate_hz));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->log_profile_id));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->sync_period_us));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->aggregation_buffer_size));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->normal_queue_depth));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->estimator_queue_depth));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->device_descriptor_count));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->algorithm_descriptor_count));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->log_stream_descriptor_count));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->reserved));
    for (uint16_t field_index = 0U; field_index < 6U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->p0_diagonal[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->process_accel_std_mps2[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 5U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->measurement_profile[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 7U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->nis_profile[field_index]);
    }

    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_PureInsSerialize(
    const FlightLogPureInsRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->update_sequence));
    for (uint16_t field_index = 0U; field_index < 4U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->q_nb[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->velocity_enu_mps[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->position_enu_m[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->accel_enu_mps2[field_index]);
    }
    SslogRecords_WriterF32Put(&writer, payload->dt_s);
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->health_flags));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->alignment_valid));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->ins_valid));
    SslogRecords_WriterZero(&writer, 2U);

    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_Kf6DiagnosticSerialize(
    const FlightLogKf6DiagnosticRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->position_innovation[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->velocity_innovation[field_index]);
    }
    SslogRecords_WriterF32Put(&writer, payload->baro_innovation);
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->position_variance_r[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->velocity_variance_r[field_index]);
    }
    SslogRecords_WriterF32Put(&writer, payload->baro_variance_r);
    SslogRecords_WriterF32Put(&writer, payload->position_nis);
    SslogRecords_WriterF32Put(&writer, payload->velocity_nis);
    SslogRecords_WriterF32Put(&writer, payload->baro_nis);
    SslogRecords_WriterF32Put(&writer, payload->position_r_scale);
    SslogRecords_WriterF32Put(&writer, payload->velocity_r_scale);
    SslogRecords_WriterF32Put(&writer, payload->baro_r_scale);
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->process_accel_std_mps2[field_index]);
    }
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->gnss_velocity_valid_mask));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->velocity_update_dimension));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->position_update_result));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->velocity_update_result));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->baro_update_result));
    SslogRecords_WriterZero(&writer, 7U);

    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_Kf6FullPSerialize(
    const FlightLogKf6FullPRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    for (uint16_t field_index = 0U; field_index < 21U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->covariance_upper_triangle[field_index]);
    }

    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_PowerSerialize(
    const FlightLogPowerRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU16Put(&writer, payload->source_descriptor_id);
    SslogRecords_WriterU8Put(&writer, payload->instance_id);
    SslogRecords_WriterU8Put(&writer, payload->reserved);
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->sample_timestamp_us));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->receive_timestamp_us));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->sequence));
    SslogRecords_WriterF32Put(&writer, payload->voltage_v);
    SslogRecords_WriterF32Put(&writer, payload->current_a);
    SslogRecords_WriterF32Put(&writer, payload->power_w);
    SslogRecords_WriterF32Put(&writer, payload->state_of_charge_percent);
    SslogRecords_WriterF32Put(&writer, payload->temperature_c);
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->valid_mask));

    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_HealthSerialize(
    const FlightLogHealthRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->timestamp_us));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->compiled_mask));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->enabled_mask));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->present_mask));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->healthy_mask));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->start_blocking_mask));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->warning_mask));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->sequence));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->ready));
    SslogRecords_WriterZero(&writer, 3U);

    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_TelemetryDiagSerialize(
    const FlightLogTelemetryDiagnosticRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->last_transmit_timestamp_us));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->last_receive_timestamp_us));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->transmit_packet_count));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->receive_packet_count));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->transmit_error_count));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->receive_error_count));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->integrity_error_count));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->last_rssi_dbm));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->last_snr_q4));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->online));
    SslogRecords_WriterZero(&writer, 8U);

    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_InitialStateSerialize(
    const FlightLogInitialStateRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->alignment_algorithm));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->hardware_mode));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->mode_verified));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->origin_valid_flags));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->alignment_sample_count));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->gnss_sample_count));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->barometer_sample_count));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->reserved));
    for (uint16_t field_index = 0U; field_index < 4U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->q_nb[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->acceleration_mean_b_mps2[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->gyro_mean_b_radps[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->magnetic_field_mean_b_uT[field_index]);
    }
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->gnss_origin_latitude_e7));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->gnss_origin_longitude_e7));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->gnss_origin_height_mm));
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->gnss_origin_position_std_m[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->initial_velocity_enu_mps[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->initial_velocity_std_mps[field_index]);
    }
    SslogRecords_WriterF32Put(&writer, payload->barometer_origin_altitude_m);
    SslogRecords_WriterF32Put(&writer, payload->barometer_origin_std_m);
    for (uint16_t field_index = 0U; field_index < 6U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->p0_diagonal[field_index]);
    }

    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_GnssNativeSerialize(
    const FlightLogGnssNativeRecord *payload,
    uint8_t *buffer, uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->source_descriptor_id));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->instance_id));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->reserved));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->sample_timestamp_us));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->receive_timestamp_us));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->sequence));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->latitude_e7));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->longitude_e7));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->ellipsoid_height_mm));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->msl_height_mm));
    SslogRecords_WriterF32Put(&writer, (float)(payload->velocity_enu_mps[0]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->velocity_enu_mps[1]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->velocity_enu_mps[2]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->velocity_variance_m2ps2[0]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->velocity_variance_m2ps2[1]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->velocity_variance_m2ps2[2]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->horizontal_accuracy_m));
    SslogRecords_WriterF32Put(&writer, (float)(payload->vertical_accuracy_m));
    SslogRecords_WriterF32Put(&writer, (float)(payload->speed_accuracy_mps));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->velocity_valid_mask));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->fix_type));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->position_usable));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->course_usable));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->online));
    SslogRecords_WriterU8Put(&writer, 0U);
    SslogRecords_WriterU8Put(&writer, 0U);
    SslogRecords_WriterU8Put(&writer, 0U);
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->fix_ok));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->satellite_count));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->valid_group_mask));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->measurement_timestamp_trusted));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->supported_fields));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->valid_fields));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->group_reject_mask[0]));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->group_reject_mask[1]));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->group_reject_mask[2]));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->group_reject_mask[3]));
    SILVERSTAR_ASSERT(writer.offset == buffer_size, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_BaroNativeSerialize(
    const FlightLogBaroNativeRecord *payload,
    uint8_t *buffer, uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->source_descriptor_id));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->instance_id));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->reserved));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->sample_timestamp_us));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->receive_timestamp_us));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->sequence));
    SslogRecords_WriterF32Put(&writer, (float)(payload->pressure_pa));
    SslogRecords_WriterF32Put(&writer, (float)(payload->altitude_m));
    SslogRecords_WriterF32Put(&writer, (float)(payload->altitude_variance_m2));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->valid_mask));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->supported_fields));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->valid_fields));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->healthy));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->measurement_timestamp_trusted));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->reserved_quality));
    SILVERSTAR_ASSERT(writer.offset == buffer_size, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_MagNativeSerialize(
    const FlightLogMagNativeRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU16Put(&writer, payload->source_descriptor_id);
    SslogRecords_WriterU8Put(&writer, payload->instance_id);
    SslogRecords_WriterU8Put(&writer, payload->reserved);
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->sample_timestamp_us));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->receive_timestamp_us));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->sequence));
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->raw[field_index]));
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->magnetic_field_b_uT[field_index]);
    }
    SslogRecords_WriterF32Put(&writer, payload->temperature_c);
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->valid_mask));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->calibration_valid));
    SslogRecords_WriterZero(&writer, 3U);

    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_InertialIncrementSerialize(
    const FlightLogInertialIncrementRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->interval_start_timestamp_us));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->interval_end_timestamp_us));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->sequence));
    SslogRecords_WriterF32Put(&writer, payload->dt_s);
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->delta_theta_b_corrected[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->delta_velocity_b_sculling_corrected[field_index]);
    }
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->health_flags));

    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_EstimatorStepSerialize(
    const FlightLogEstimatorStepRecord *payload,
    uint8_t *buffer, uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->estimator_present_timestamp_us));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->interval_end_timestamp_us));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->operation_sequence));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->source_sequence));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->replay_epoch));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->replay_generation));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->replay_result));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->attitude_result));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->reserved));
    SILVERSTAR_ASSERT(writer.offset == buffer_size, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_GnssRecoverySerialize(
    const FlightLogGnssRecoveryRecord *payload,
    uint8_t *buffer, uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->estimator_present_timestamp_us));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->source_sequence));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->replay_epoch));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->quality_reject_mask[0]));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->quality_reject_mask[1]));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->quality_reject_mask[2]));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->quality_reject_mask[3]));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->consistency_count[0]));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->consistency_count[1]));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->consistency_count[2]));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->consistency_count[3]));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->inflation_attempt_count[0]));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->inflation_attempt_count[1]));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->inflation_attempt_count[2]));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->inflation_attempt_count[3]));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->reanchor_count[0]));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->reanchor_count[1]));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->reanchor_count[2]));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->reanchor_count[3]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->inflation_factor[0]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->inflation_factor[1]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->inflation_factor[2]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->inflation_factor[3]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->valid[0]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->valid[1]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->valid[2]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->valid[3]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->update_result[0]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->update_result[1]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->update_result[2]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->update_result[3]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->outage[0]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->outage[1]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->outage[2]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->outage[3]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->recovery_active[0]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->recovery_active[1]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->recovery_active[2]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->recovery_active[3]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->reanchor_reason[0]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->reanchor_reason[1]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->reanchor_reason[2]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->reanchor_reason[3]));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->operation_sequence));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->replay_generation));
    SILVERSTAR_ASSERT(writer.offset == buffer_size, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_LandingDiagnosticSerialize(
    const FlightLogLandingDiagnosticRecord *payload,
    uint8_t *buffer, uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->evaluation_timestamp_us));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->candidate_start_timestamp_us));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->sequence));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->candidate_elapsed_us));
    SslogRecords_WriterF32Put(&writer, (float)(payload->valid_coverage));
    SslogRecords_WriterF32Put(&writer, (float)(payload->still_ratio));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->maximum_bad_duration_us));
    SslogRecords_WriterF32Put(&writer, (float)(payload->baro_slope_mps));
    SslogRecords_WriterF32Put(&writer, (float)(payload->baro_span_m));
    SslogRecords_WriterF32Put(&writer, (float)(payload->baro_coverage));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->transition));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->reset_reason));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->reserved));
    SILVERSTAR_ASSERT(writer.offset == buffer_size, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_GnssMeasurementSerialize(
    const FlightLogGnssMeasurementRecord *payload,
    uint8_t *buffer, uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->sample_timestamp_us));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->receive_timestamp_us));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->sequence));
    SslogRecords_WriterF32Put(&writer, (float)(payload->position_enu_m[0]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->position_enu_m[1]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->position_enu_m[2]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->velocity_enu_mps[0]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->velocity_enu_mps[1]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->velocity_enu_mps[2]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->position_variance_m2[0]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->position_variance_m2[1]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->position_variance_m2[2]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->velocity_variance_m2ps2[0]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->velocity_variance_m2ps2[1]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->velocity_variance_m2ps2[2]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->velocity_valid_mask));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->position_usable));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->fusion_allowed));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->reserved));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->position_measurement_timestamp_us));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->velocity_measurement_timestamp_us));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->estimator_present_timestamp_us));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->receive_operation_sequence));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->position_operation_sequence));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->velocity_operation_sequence));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->replay_epoch));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->replay_generation));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->valid_group_mask));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->position_replay_result));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->velocity_replay_result));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->receive_result));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->group_update_result[0]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->group_update_result[1]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->group_update_result[2]));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->group_update_result[3]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->group_nis[0]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->group_nis[1]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->group_nis[2]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->group_nis[3]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->position_innovation_m[0]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->position_innovation_m[1]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->position_innovation_m[2]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->velocity_innovation_mps[0]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->velocity_innovation_mps[1]));
    SslogRecords_WriterF32Put(&writer, (float)(payload->velocity_innovation_mps[2]));
    SILVERSTAR_ASSERT(writer.offset == buffer_size, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_BaroMeasurementSerialize(
    const FlightLogBaroMeasurementRecord *payload,
    uint8_t *buffer, uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->sample_timestamp_us));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->receive_timestamp_us));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->sequence));
    SslogRecords_WriterF32Put(&writer, (float)(payload->relative_altitude_m));
    SslogRecords_WriterF32Put(&writer, (float)(payload->variance_m2));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->valid_mask));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->measurement_timestamp_us));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->estimator_present_timestamp_us));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->operation_sequence));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->replay_epoch));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->replay_generation));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->update_result));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->replay_result));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->measurement_timestamp_trusted));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->reserved));
    SslogRecords_WriterF32Put(&writer, (float)(payload->innovation_m));
    SslogRecords_WriterF32Put(&writer, (float)(payload->nis));
    SILVERSTAR_ASSERT(writer.offset == buffer_size, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_ImuCorrectedSerialize(
    const FlightLogImuCorrectedRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->sample_timestamp_us));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->receive_timestamp_us));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->sequence));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->source_id));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->virtual_imu_id));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->valid_mask));
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->accel_b_mps2[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->gyro_b_radps[field_index]);
    }
    SslogRecords_WriterF32Put(&writer, payload->temperature_c);
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->calibration_mode));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->correction_valid));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->reserved));

    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_CalibrationResultSerialize(
    const FlightLogCalibrationResultRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->source_id));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->virtual_imu_id));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->mode));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->state));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->ready));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->completed_face_mask));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->samples));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->reject_count));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->retry_count));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->start_sequence));
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->accel_bias_mps2[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->accel_scale[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->gyro_bias_radps[field_index]);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->gyro_scale[field_index]);
    }

    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_AlignmentResultSerialize(
    const FlightLogAlignmentResultRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->capability_mask));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->selected_mask));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->required_mask));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->ready_mask));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->unavailable_mask));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->missing_adapter_mask));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->start_sequence));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->state));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->config_result));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->ready));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->source_count));
    SslogRecords_WriterU64Put(&writer, (uint64_t)(payload->attitude_timestamp_us));
    for (uint16_t field_index = 0U; field_index < 4U; field_index++)
    {
    SslogRecords_WriterF32Put(&writer, payload->q_nb[field_index]);
    }
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->gnss_origin_lat_e7));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->gnss_origin_lon_e7));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->gnss_origin_height_mm));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->gnss_sample_count));
    SslogRecords_WriterF32Put(&writer, payload->gnss_horizontal_accuracy_m);
    SslogRecords_WriterF32Put(&writer, payload->gnss_vertical_accuracy_m);
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->barometer_sample_count));
    SslogRecords_WriterF32Put(&writer, payload->barometer_origin_pressure_pa);
    SslogRecords_WriterF32Put(&writer, payload->barometer_origin_altitude_m);
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->attitude_state));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->gnss_state));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->barometer_state));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->attitude_source));

    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_AlignmentEvidenceSerialize(
    const FlightLogAlignmentEvidenceRecord *payload,
    uint8_t *buffer, uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT_OBJECT(payload, FlightLogAlignmentEvidenceRecord,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU8Put(&writer, payload->alignment_algorithm);
    SslogRecords_WriterU8Put(&writer, payload->constraint_count);
    SslogRecords_WriterU8Put(&writer, payload->valid_pair_count);
    SslogRecords_WriterU8Put(&writer, payload->yaw_authoritative);
    SslogRecords_WriterU8Put(&writer, payload->imu_source_instance);
    SslogRecords_WriterU8Put(&writer, payload->magnetometer_instance);
    SslogRecords_WriterU8Put(&writer, payload->external_source_instance);
    SslogRecords_WriterU8Put(&writer, payload->failure_reason);
    SslogRecords_WriterU16Put(&writer,
        payload->magnetometer_physical_device_id);
    SslogRecords_WriterU16Put(&writer, payload->flags);
    SslogRecords_WriterU32Put(&writer,
        payload->mag_calibration_generation);
    SslogRecords_WriterU32Put(&writer,
        payload->mag_calibration_set_hash);
    SslogRecords_WriterU64Put(&writer, payload->first_timestamp_us);
    SslogRecords_WriterU64Put(&writer, payload->last_timestamp_us);
    SslogRecords_WriterF32Put(&writer, payload->minimum_pair_sine);
    SslogRecords_WriterF32Put(&writer, payload->rms_mismatch_rad);
    SslogRecords_WriterF32Put(&writer, payload->max_mismatch_rad);
    SILVERSTAR_ASSERT(writer.offset == buffer_size,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_MissionSnapshotIdentitySerialize(
    const FlightLogMissionSnapshotIdentityRecord *payload,
    uint8_t *buffer, uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT_OBJECT(payload, FlightLogMissionSnapshotIdentityRecord,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU32Put(&writer, payload->mission_id);
    SslogRecords_WriterU32Put(&writer, payload->commit_generation);
    SslogRecords_WriterU32Put(&writer, payload->snapshot_sequence);
    SslogRecords_WriterU32Put(&writer, payload->imu_calibration_generation);
    SslogRecords_WriterU32Put(&writer, payload->mag_calibration_set_hash);
    SslogRecords_WriterU8Put(&writer, payload->base_instance);
    SslogRecords_WriterU8Put(&writer, payload->ready);
    SslogRecords_WriterU16Put(&writer, payload->reserved);
    SILVERSTAR_ASSERT(writer.offset == buffer_size,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_MagCalibrationIdentitySerialize(
    const FlightLogMagCalibrationIdentityRecord *payload,
    uint8_t *buffer, uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT_OBJECT(payload, FlightLogMagCalibrationIdentityRecord,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU16Put(&writer, payload->physical_device_id);
    SslogRecords_WriterU8Put(&writer, payload->instance_id);
    SslogRecords_WriterU8Put(&writer, payload->active);
    SslogRecords_WriterU8Put(&writer, payload->saved);
    SslogRecords_WriterU8Put(&writer, payload->load_error);
    SslogRecords_WriterU16Put(&writer, payload->reserved);
    SslogRecords_WriterU32Put(&writer, payload->generation);
    SslogRecords_WriterU32Put(&writer, payload->calibration_set_hash);
    SILVERSTAR_ASSERT(writer.offset == buffer_size,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_MissionConfigSerialize(
    const FlightLogMissionConfigRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->alignment_algorithm));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->rocket_longitudinal_axis));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->deploy_trigger_mask));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->tilt_reference));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->landing_enable));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->landing_mode));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->impact_capable));
    SslogRecords_WriterF32Put(&writer, payload->known_yaw_deg);
    SslogRecords_WriterF32Put(&writer, payload->magnetic_declination_deg);
    SslogRecords_WriterF32Put(&writer, payload->tilt_threshold_deg);
    SslogRecords_WriterF32Put(&writer, payload->apogee_vz_threshold_mps);
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->deploy_confirm_ms));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->deploy_delay_ms));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->baro_trigger_window_ms));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->baro_trigger_min_samples));
    SslogRecords_WriterF32Put(&writer, payload->baro_trigger_rate_mps);
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->candidate_duration_ms));
    SslogRecords_WriterF32Put(&writer, payload->baro_confirm_rate_mps);
    SslogRecords_WriterF32Put(&writer, payload->baro_max_span_m);
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->candidate_baro_min_samples));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->candidate_imu_min_samples));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->candidate_min_coverage_percent));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->impact_inhibit_ms));
    SslogRecords_WriterF32Put(&writer, payload->impact_threshold_mps2);
    SslogRecords_WriterF32Put(&writer, payload->still_gyro_threshold_radps);
    SslogRecords_WriterF32Put(&writer, payload->still_accel_tolerance_mps2);
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->landing_confirm_ms));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->landing_sample_max_age_ms));

    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_DeviceDescriptorSerialize(
    const FlightLogDeviceDescriptorRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->descriptor_id));
    SslogRecords_WriterU16Put(&writer, payload->physical_device_id);
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->device_class));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->instance_id));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->driver_id));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->flags));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->capability_mask));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->configured_rate_hz));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->driver_name_hash));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->model_name_hash));

    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_AlgorithmDescriptorSerialize(
    const FlightLogAlgorithmDescriptorRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->descriptor_id));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->algorithm_class));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->instance_id));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->algorithm_id));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->flags));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->config_digest));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->name_hash));

    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_LogStreamDescriptorSerialize(
    const FlightLogStreamDescriptorRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->record_type));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->record_version));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->enabled));
    SslogRecords_WriterU8Put(&writer, (uint8_t)(payload->policy));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->decimation));
    SslogRecords_WriterU16Put(&writer, (uint16_t)(payload->reserved));
    SslogRecords_WriterU32Put(&writer, (uint32_t)(payload->period_us));

    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_DecoderProfileDescriptorSerialize(
    const FlightLogDecoderProfileDescriptorRecord *payload,
    uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SslogRecords_WriterU16Put(&writer, payload->package_schema_major);
    SslogRecords_WriterU16Put(&writer, payload->package_schema_minor);
    SslogRecords_WriterU16Put(&writer, payload->container_format_major);
    SslogRecords_WriterU16Put(&writer, payload->container_format_minor);
    (void)memcpy(SslogRecords_WriteReserve(&writer, 16U),
        payload->record_catalog_hash_128, 16U);
    (void)memcpy(SslogRecords_WriteReserve(&writer, 16U),
        payload->project_semantics_hash_128, 16U);
    (void)memcpy(SslogRecords_WriteReserve(&writer, 16U),
        payload->generation_profile_hash_128, 16U);
    SslogRecords_WriterZero(&writer, 8U);
    SILVERSTAR_ASSERT(writer.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return writer.offset;
}

static uint16_t SslogRecords_EventDeserialize(
    FlightLogEventRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->event_id = SslogRecords_ReaderU8Get(&reader);
    SslogRecords_ReaderSkip(&reader, 3U);
    payload->arg0 = SslogRecords_ReaderU32Get(&reader);
    payload->arg1 = SslogRecords_ReaderU32Get(&reader);

    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_StatsDeserialize(
    FlightLogStatsRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->imu_queue_overflow_count = SslogRecords_ReaderU32Get(&reader);
    payload->logger_queue_overflow_count = SslogRecords_ReaderU32Get(&reader);
    payload->ins_update_count = SslogRecords_ReaderU32Get(&reader);
    payload->health_flags = SslogRecords_ReaderU32Get(&reader);

    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static void SslogRecords_EstimatorMotionDeserialize(
    FlightLogEstimatorRecord *payload,
    SslogReadCursor *cursor)
{
    SILVERSTAR_ASSERT_OBJECT(payload, FlightLogEstimatorRecord, SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    SILVERSTAR_ASSERT(cursor != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL, SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    for (uint16_t index = 0U; index < 4U; index++)
    {
        payload->q_nb[index] = SslogRecords_ReaderF32Get(cursor);
    }
    for (uint16_t index = 0U; index < 3U; index++)
    {
        payload->acceleration_enu_mps2[index] = SslogRecords_ReaderF32Get(cursor);
    }
}

static uint16_t SslogRecords_EstimatorDeserialize(
    FlightLogEstimatorRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->position_enu_m[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->velocity_enu_mps[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 6U; field_index++)
    {
    payload->covariance_diagonal[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->gnss_position_enu_m[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->gnss_velocity_enu_mps[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    payload->baro_relative_altitude_m = SslogRecords_ReaderF32Get(&reader);
    payload->last_position_nis = SslogRecords_ReaderF32Get(&reader);
    payload->last_velocity_nis = SslogRecords_ReaderF32Get(&reader);
    payload->last_baro_nis = SslogRecords_ReaderF32Get(&reader);
    payload->measurement_result_flags = SslogRecords_ReaderU32Get(&reader);
    payload->health_flags = SslogRecords_ReaderU32Get(&reader);
    payload->prediction_queue_overflow_count = SslogRecords_ReaderU32Get(&reader);
    payload->gnss_sequence = SslogRecords_ReaderU32Get(&reader);
    payload->baro_sequence = SslogRecords_ReaderU32Get(&reader);
    payload->gnss_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->baro_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->gnss_measurement_age_us = SslogRecords_ReaderU32Get(&reader);
    payload->baro_measurement_age_us = SslogRecords_ReaderU32Get(&reader);
    payload->gnss_origin_valid = SslogRecords_ReaderU8Get(&reader);
    payload->baro_origin_valid = SslogRecords_ReaderU8Get(&reader);
    payload->initialized = SslogRecords_ReaderU8Get(&reader);
    payload->mission_running = SslogRecords_ReaderU8Get(&reader);

    SslogRecords_EstimatorMotionDeserialize(payload, &reader);
    payload->operation_sequence = SslogRecords_ReaderU32Get(&reader);
    payload->replay_epoch = SslogRecords_ReaderU32Get(&reader);
    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_SystemConfigDeserialize(
    FlightLogSystemConfigRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    for (uint16_t field_index = 0U; field_index < 4U; field_index++)
    {
    payload->version[field_index] = SslogRecords_ReaderU8Get(&reader);
    }
    payload->profile_id = SslogRecords_ReaderU32Get(&reader);
    payload->device_config_digest = SslogRecords_ReaderU32Get(&reader);
    payload->configured_imu_rate_hz = SslogRecords_ReaderU16Get(&reader);
    payload->configured_gnss_rate_hz = SslogRecords_ReaderU16Get(&reader);
    payload->configured_magnetometer_rate_hz = SslogRecords_ReaderU16Get(&reader);
    payload->configured_barometer_rate_hz = SslogRecords_ReaderU16Get(&reader);
    payload->configured_hardware_quaternion_rate_hz = SslogRecords_ReaderU16Get(&reader);
    payload->mechanization_subsample_count = SslogRecords_ReaderU16Get(&reader);
    payload->expected_ins_rate_hz = SslogRecords_ReaderU16Get(&reader);
    payload->mechanization_min_sample_rate_hz = SslogRecords_ReaderU16Get(&reader);
    payload->mechanization_max_sample_rate_hz = SslogRecords_ReaderU16Get(&reader);
    payload->log_profile_id = SslogRecords_ReaderU16Get(&reader);
    payload->sync_period_us = SslogRecords_ReaderU32Get(&reader);
    payload->aggregation_buffer_size = SslogRecords_ReaderU16Get(&reader);
    payload->normal_queue_depth = SslogRecords_ReaderU8Get(&reader);
    payload->estimator_queue_depth = SslogRecords_ReaderU8Get(&reader);
    payload->device_descriptor_count = SslogRecords_ReaderU16Get(&reader);
    payload->algorithm_descriptor_count = SslogRecords_ReaderU16Get(&reader);
    payload->log_stream_descriptor_count = SslogRecords_ReaderU16Get(&reader);
    payload->reserved = SslogRecords_ReaderU16Get(&reader);
    for (uint16_t field_index = 0U; field_index < 6U; field_index++)
    {
    payload->p0_diagonal[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->process_accel_std_mps2[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 5U; field_index++)
    {
    payload->measurement_profile[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 7U; field_index++)
    {
    payload->nis_profile[field_index] = SslogRecords_ReaderF32Get(&reader);
    }

    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_PureInsDeserialize(
    FlightLogPureInsRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->update_sequence = SslogRecords_ReaderU32Get(&reader);
    for (uint16_t field_index = 0U; field_index < 4U; field_index++)
    {
    payload->q_nb[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->velocity_enu_mps[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->position_enu_m[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->accel_enu_mps2[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    payload->dt_s = SslogRecords_ReaderF32Get(&reader);
    payload->health_flags = SslogRecords_ReaderU32Get(&reader);
    payload->alignment_valid = SslogRecords_ReaderU8Get(&reader);
    payload->ins_valid = SslogRecords_ReaderU8Get(&reader);
    SslogRecords_ReaderSkip(&reader, 2U);

    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_Kf6DiagnosticDeserialize(
    FlightLogKf6DiagnosticRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->position_innovation[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->velocity_innovation[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    payload->baro_innovation = SslogRecords_ReaderF32Get(&reader);
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->position_variance_r[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->velocity_variance_r[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    payload->baro_variance_r = SslogRecords_ReaderF32Get(&reader);
    payload->position_nis = SslogRecords_ReaderF32Get(&reader);
    payload->velocity_nis = SslogRecords_ReaderF32Get(&reader);
    payload->baro_nis = SslogRecords_ReaderF32Get(&reader);
    payload->position_r_scale = SslogRecords_ReaderF32Get(&reader);
    payload->velocity_r_scale = SslogRecords_ReaderF32Get(&reader);
    payload->baro_r_scale = SslogRecords_ReaderF32Get(&reader);
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->process_accel_std_mps2[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    payload->gnss_velocity_valid_mask = SslogRecords_ReaderU8Get(&reader);
    payload->velocity_update_dimension = SslogRecords_ReaderU8Get(&reader);
    payload->position_update_result = SslogRecords_ReaderU8Get(&reader);
    payload->velocity_update_result = SslogRecords_ReaderU8Get(&reader);
    payload->baro_update_result = SslogRecords_ReaderU8Get(&reader);
    SslogRecords_ReaderSkip(&reader, 7U);

    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_Kf6FullPDeserialize(
    FlightLogKf6FullPRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    for (uint16_t field_index = 0U; field_index < 21U; field_index++)
    {
    payload->covariance_upper_triangle[field_index] = SslogRecords_ReaderF32Get(&reader);
    }

    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_PowerDeserialize(
    FlightLogPowerRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->source_descriptor_id = SslogRecords_ReaderU16Get(&reader);
    payload->instance_id = SslogRecords_ReaderU8Get(&reader);
    payload->reserved = SslogRecords_ReaderU8Get(&reader);
    payload->sample_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->receive_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->sequence = SslogRecords_ReaderU32Get(&reader);
    payload->voltage_v = SslogRecords_ReaderF32Get(&reader);
    payload->current_a = SslogRecords_ReaderF32Get(&reader);
    payload->power_w = SslogRecords_ReaderF32Get(&reader);
    payload->state_of_charge_percent = SslogRecords_ReaderF32Get(&reader);
    payload->temperature_c = SslogRecords_ReaderF32Get(&reader);
    payload->valid_mask = SslogRecords_ReaderU32Get(&reader);

    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_HealthDeserialize(
    FlightLogHealthRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->compiled_mask = SslogRecords_ReaderU32Get(&reader);
    payload->enabled_mask = SslogRecords_ReaderU32Get(&reader);
    payload->present_mask = SslogRecords_ReaderU32Get(&reader);
    payload->healthy_mask = SslogRecords_ReaderU32Get(&reader);
    payload->start_blocking_mask = SslogRecords_ReaderU32Get(&reader);
    payload->warning_mask = SslogRecords_ReaderU32Get(&reader);
    payload->sequence = SslogRecords_ReaderU32Get(&reader);
    payload->ready = SslogRecords_ReaderU8Get(&reader);
    SslogRecords_ReaderSkip(&reader, 3U);

    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_TelemetryDiagDeserialize(
    FlightLogTelemetryDiagnosticRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->last_transmit_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->last_receive_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->transmit_packet_count = SslogRecords_ReaderU32Get(&reader);
    payload->receive_packet_count = SslogRecords_ReaderU32Get(&reader);
    payload->transmit_error_count = SslogRecords_ReaderU32Get(&reader);
    payload->receive_error_count = SslogRecords_ReaderU32Get(&reader);
    payload->integrity_error_count = SslogRecords_ReaderU32Get(&reader);
    payload->last_rssi_dbm = (int16_t)SslogRecords_ReaderU16Get(&reader);
    payload->last_snr_q4 = (int8_t)SslogRecords_ReaderU8Get(&reader);
    payload->online = SslogRecords_ReaderU8Get(&reader);
    SslogRecords_ReaderSkip(&reader, 8U);

    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_InitialStateDeserialize(
    FlightLogInitialStateRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->alignment_algorithm = SslogRecords_ReaderU8Get(&reader);
    payload->hardware_mode = SslogRecords_ReaderU8Get(&reader);
    payload->mode_verified = SslogRecords_ReaderU8Get(&reader);
    payload->origin_valid_flags = SslogRecords_ReaderU8Get(&reader);
    payload->alignment_sample_count = SslogRecords_ReaderU16Get(&reader);
    payload->gnss_sample_count = SslogRecords_ReaderU16Get(&reader);
    payload->barometer_sample_count = SslogRecords_ReaderU16Get(&reader);
    payload->reserved = SslogRecords_ReaderU16Get(&reader);
    for (uint16_t field_index = 0U; field_index < 4U; field_index++)
    {
    payload->q_nb[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->acceleration_mean_b_mps2[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->gyro_mean_b_radps[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->magnetic_field_mean_b_uT[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    payload->gnss_origin_latitude_e7 = (int32_t)SslogRecords_ReaderU32Get(&reader);
    payload->gnss_origin_longitude_e7 = (int32_t)SslogRecords_ReaderU32Get(&reader);
    payload->gnss_origin_height_mm = (int32_t)SslogRecords_ReaderU32Get(&reader);
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->gnss_origin_position_std_m[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->initial_velocity_enu_mps[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->initial_velocity_std_mps[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    payload->barometer_origin_altitude_m = SslogRecords_ReaderF32Get(&reader);
    payload->barometer_origin_std_m = SslogRecords_ReaderF32Get(&reader);
    for (uint16_t field_index = 0U; field_index < 6U; field_index++)
    {
    payload->p0_diagonal[field_index] = SslogRecords_ReaderF32Get(&reader);
    }

    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_GnssNativeDeserialize(
    FlightLogGnssNativeRecord *payload,
    const uint8_t *buffer, uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->source_descriptor_id = (uint16_t)SslogRecords_ReaderU16Get(&reader);
    payload->instance_id = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->reserved = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->sample_timestamp_us = (uint64_t)SslogRecords_ReaderU64Get(&reader);
    payload->receive_timestamp_us = (uint64_t)SslogRecords_ReaderU64Get(&reader);
    payload->sequence = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->latitude_e7 = (int32_t)SslogRecords_ReaderU32Get(&reader);
    payload->longitude_e7 = (int32_t)SslogRecords_ReaderU32Get(&reader);
    payload->ellipsoid_height_mm = (int32_t)SslogRecords_ReaderU32Get(&reader);
    payload->msl_height_mm = (int32_t)SslogRecords_ReaderU32Get(&reader);
    payload->velocity_enu_mps[0] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->velocity_enu_mps[1] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->velocity_enu_mps[2] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->velocity_variance_m2ps2[0] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->velocity_variance_m2ps2[1] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->velocity_variance_m2ps2[2] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->horizontal_accuracy_m = (float)SslogRecords_ReaderF32Get(&reader);
    payload->vertical_accuracy_m = (float)SslogRecords_ReaderF32Get(&reader);
    payload->speed_accuracy_mps = (float)SslogRecords_ReaderF32Get(&reader);
    payload->velocity_valid_mask = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->fix_type = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->position_usable = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->course_usable = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->online = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    (void)SslogRecords_ReaderU8Get(&reader);
    (void)SslogRecords_ReaderU8Get(&reader);
    (void)SslogRecords_ReaderU8Get(&reader);
    payload->fix_ok = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->satellite_count = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->valid_group_mask = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->measurement_timestamp_trusted = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->supported_fields = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->valid_fields = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->group_reject_mask[0] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->group_reject_mask[1] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->group_reject_mask[2] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->group_reject_mask[3] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    SILVERSTAR_ASSERT(reader.offset == buffer_size, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_BaroNativeDeserialize(
    FlightLogBaroNativeRecord *payload,
    const uint8_t *buffer, uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->source_descriptor_id = (uint16_t)SslogRecords_ReaderU16Get(&reader);
    payload->instance_id = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->reserved = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->sample_timestamp_us = (uint64_t)SslogRecords_ReaderU64Get(&reader);
    payload->receive_timestamp_us = (uint64_t)SslogRecords_ReaderU64Get(&reader);
    payload->sequence = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->pressure_pa = (float)SslogRecords_ReaderF32Get(&reader);
    payload->altitude_m = (float)SslogRecords_ReaderF32Get(&reader);
    payload->altitude_variance_m2 = (float)SslogRecords_ReaderF32Get(&reader);
    payload->valid_mask = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->supported_fields = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->valid_fields = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->healthy = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->measurement_timestamp_trusted = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->reserved_quality = (uint16_t)SslogRecords_ReaderU16Get(&reader);
    SILVERSTAR_ASSERT(reader.offset == buffer_size, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_MagNativeDeserialize(
    FlightLogMagNativeRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->source_descriptor_id = SslogRecords_ReaderU16Get(&reader);
    payload->instance_id = SslogRecords_ReaderU8Get(&reader);
    payload->reserved = SslogRecords_ReaderU8Get(&reader);
    payload->sample_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->receive_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->sequence = SslogRecords_ReaderU32Get(&reader);
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->raw[field_index] = (int32_t)SslogRecords_ReaderU32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->magnetic_field_b_uT[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    payload->temperature_c = SslogRecords_ReaderF32Get(&reader);
    payload->valid_mask = SslogRecords_ReaderU32Get(&reader);
    payload->calibration_valid = SslogRecords_ReaderU8Get(&reader);
    SslogRecords_ReaderSkip(&reader, 3U);

    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_InertialIncrementDeserialize(
    FlightLogInertialIncrementRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->interval_start_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->interval_end_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->sequence = SslogRecords_ReaderU32Get(&reader);
    payload->dt_s = SslogRecords_ReaderF32Get(&reader);
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->delta_theta_b_corrected[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->delta_velocity_b_sculling_corrected[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    payload->health_flags = SslogRecords_ReaderU32Get(&reader);

    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_EstimatorStepDeserialize(
    FlightLogEstimatorStepRecord *payload,
    const uint8_t *buffer, uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->estimator_present_timestamp_us = (uint64_t)SslogRecords_ReaderU64Get(&reader);
    payload->interval_end_timestamp_us = (uint64_t)SslogRecords_ReaderU64Get(&reader);
    payload->operation_sequence = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->source_sequence = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->replay_epoch = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->replay_generation = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->replay_result = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->attitude_result = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->reserved = (uint16_t)SslogRecords_ReaderU16Get(&reader);
    SILVERSTAR_ASSERT(reader.offset == buffer_size, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_GnssRecoveryDeserialize(
    FlightLogGnssRecoveryRecord *payload,
    const uint8_t *buffer, uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->estimator_present_timestamp_us = (uint64_t)SslogRecords_ReaderU64Get(&reader);
    payload->source_sequence = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->replay_epoch = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->quality_reject_mask[0] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->quality_reject_mask[1] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->quality_reject_mask[2] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->quality_reject_mask[3] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->consistency_count[0] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->consistency_count[1] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->consistency_count[2] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->consistency_count[3] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->inflation_attempt_count[0] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->inflation_attempt_count[1] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->inflation_attempt_count[2] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->inflation_attempt_count[3] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->reanchor_count[0] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->reanchor_count[1] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->reanchor_count[2] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->reanchor_count[3] = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->inflation_factor[0] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->inflation_factor[1] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->inflation_factor[2] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->inflation_factor[3] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->valid[0] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->valid[1] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->valid[2] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->valid[3] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->update_result[0] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->update_result[1] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->update_result[2] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->update_result[3] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->outage[0] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->outage[1] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->outage[2] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->outage[3] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->recovery_active[0] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->recovery_active[1] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->recovery_active[2] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->recovery_active[3] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->reanchor_reason[0] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->reanchor_reason[1] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->reanchor_reason[2] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->reanchor_reason[3] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->operation_sequence = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->replay_generation = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    SILVERSTAR_ASSERT(reader.offset == buffer_size, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_LandingDiagnosticDeserialize(
    FlightLogLandingDiagnosticRecord *payload,
    const uint8_t *buffer, uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->evaluation_timestamp_us = (uint64_t)SslogRecords_ReaderU64Get(&reader);
    payload->candidate_start_timestamp_us = (uint64_t)SslogRecords_ReaderU64Get(&reader);
    payload->sequence = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->candidate_elapsed_us = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->valid_coverage = (float)SslogRecords_ReaderF32Get(&reader);
    payload->still_ratio = (float)SslogRecords_ReaderF32Get(&reader);
    payload->maximum_bad_duration_us = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->baro_slope_mps = (float)SslogRecords_ReaderF32Get(&reader);
    payload->baro_span_m = (float)SslogRecords_ReaderF32Get(&reader);
    payload->baro_coverage = (float)SslogRecords_ReaderF32Get(&reader);
    payload->transition = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->reset_reason = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->reserved = (uint16_t)SslogRecords_ReaderU16Get(&reader);
    SILVERSTAR_ASSERT(reader.offset == buffer_size, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_GnssMeasurementDeserialize(
    FlightLogGnssMeasurementRecord *payload,
    const uint8_t *buffer, uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->sample_timestamp_us = (uint64_t)SslogRecords_ReaderU64Get(&reader);
    payload->receive_timestamp_us = (uint64_t)SslogRecords_ReaderU64Get(&reader);
    payload->sequence = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->position_enu_m[0] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->position_enu_m[1] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->position_enu_m[2] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->velocity_enu_mps[0] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->velocity_enu_mps[1] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->velocity_enu_mps[2] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->position_variance_m2[0] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->position_variance_m2[1] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->position_variance_m2[2] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->velocity_variance_m2ps2[0] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->velocity_variance_m2ps2[1] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->velocity_variance_m2ps2[2] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->velocity_valid_mask = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->position_usable = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->fusion_allowed = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->reserved = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->position_measurement_timestamp_us = (uint64_t)SslogRecords_ReaderU64Get(&reader);
    payload->velocity_measurement_timestamp_us = (uint64_t)SslogRecords_ReaderU64Get(&reader);
    payload->estimator_present_timestamp_us = (uint64_t)SslogRecords_ReaderU64Get(&reader);
    payload->receive_operation_sequence = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->position_operation_sequence = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->velocity_operation_sequence = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->replay_epoch = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->replay_generation = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->valid_group_mask = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->position_replay_result = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->velocity_replay_result = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->receive_result = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->group_update_result[0] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->group_update_result[1] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->group_update_result[2] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->group_update_result[3] = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->group_nis[0] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->group_nis[1] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->group_nis[2] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->group_nis[3] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->position_innovation_m[0] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->position_innovation_m[1] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->position_innovation_m[2] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->velocity_innovation_mps[0] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->velocity_innovation_mps[1] = (float)SslogRecords_ReaderF32Get(&reader);
    payload->velocity_innovation_mps[2] = (float)SslogRecords_ReaderF32Get(&reader);
    SILVERSTAR_ASSERT(reader.offset == buffer_size, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_BaroMeasurementDeserialize(
    FlightLogBaroMeasurementRecord *payload,
    const uint8_t *buffer, uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->sample_timestamp_us = (uint64_t)SslogRecords_ReaderU64Get(&reader);
    payload->receive_timestamp_us = (uint64_t)SslogRecords_ReaderU64Get(&reader);
    payload->sequence = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->relative_altitude_m = (float)SslogRecords_ReaderF32Get(&reader);
    payload->variance_m2 = (float)SslogRecords_ReaderF32Get(&reader);
    payload->valid_mask = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->measurement_timestamp_us = (uint64_t)SslogRecords_ReaderU64Get(&reader);
    payload->estimator_present_timestamp_us = (uint64_t)SslogRecords_ReaderU64Get(&reader);
    payload->operation_sequence = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->replay_epoch = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->replay_generation = (uint32_t)SslogRecords_ReaderU32Get(&reader);
    payload->update_result = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->replay_result = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->measurement_timestamp_trusted = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->reserved = (uint8_t)SslogRecords_ReaderU8Get(&reader);
    payload->innovation_m = (float)SslogRecords_ReaderF32Get(&reader);
    payload->nis = (float)SslogRecords_ReaderF32Get(&reader);
    SILVERSTAR_ASSERT(reader.offset == buffer_size, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_ImuCorrectedDeserialize(
    FlightLogImuCorrectedRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->sample_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->receive_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->sequence = SslogRecords_ReaderU32Get(&reader);
    payload->source_id = SslogRecords_ReaderU16Get(&reader);
    payload->virtual_imu_id = SslogRecords_ReaderU16Get(&reader);
    payload->valid_mask = SslogRecords_ReaderU32Get(&reader);
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->accel_b_mps2[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->gyro_b_radps[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    payload->temperature_c = SslogRecords_ReaderF32Get(&reader);
    payload->calibration_mode = SslogRecords_ReaderU8Get(&reader);
    payload->correction_valid = SslogRecords_ReaderU8Get(&reader);
    payload->reserved = SslogRecords_ReaderU16Get(&reader);

    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_CalibrationResultDeserialize(
    FlightLogCalibrationResultRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->source_id = SslogRecords_ReaderU16Get(&reader);
    payload->virtual_imu_id = SslogRecords_ReaderU16Get(&reader);
    payload->mode = SslogRecords_ReaderU8Get(&reader);
    payload->state = SslogRecords_ReaderU8Get(&reader);
    payload->ready = SslogRecords_ReaderU8Get(&reader);
    payload->completed_face_mask = SslogRecords_ReaderU8Get(&reader);
    payload->samples = SslogRecords_ReaderU32Get(&reader);
    payload->reject_count = SslogRecords_ReaderU32Get(&reader);
    payload->retry_count = SslogRecords_ReaderU32Get(&reader);
    payload->start_sequence = SslogRecords_ReaderU32Get(&reader);
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->accel_bias_mps2[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->accel_scale[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->gyro_bias_radps[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t field_index = 0U; field_index < 3U; field_index++)
    {
    payload->gyro_scale[field_index] = SslogRecords_ReaderF32Get(&reader);
    }

    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_AlignmentResultDeserialize(
    FlightLogAlignmentResultRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->capability_mask = SslogRecords_ReaderU32Get(&reader);
    payload->selected_mask = SslogRecords_ReaderU32Get(&reader);
    payload->required_mask = SslogRecords_ReaderU32Get(&reader);
    payload->ready_mask = SslogRecords_ReaderU32Get(&reader);
    payload->unavailable_mask = SslogRecords_ReaderU32Get(&reader);
    payload->missing_adapter_mask = SslogRecords_ReaderU32Get(&reader);
    payload->start_sequence = SslogRecords_ReaderU32Get(&reader);
    payload->state = SslogRecords_ReaderU8Get(&reader);
    payload->config_result = SslogRecords_ReaderU8Get(&reader);
    payload->ready = SslogRecords_ReaderU8Get(&reader);
    payload->source_count = SslogRecords_ReaderU8Get(&reader);
    payload->attitude_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    for (uint16_t field_index = 0U; field_index < 4U; field_index++)
    {
    payload->q_nb[field_index] = SslogRecords_ReaderF32Get(&reader);
    }
    payload->gnss_origin_lat_e7 = (int32_t)SslogRecords_ReaderU32Get(&reader);
    payload->gnss_origin_lon_e7 = (int32_t)SslogRecords_ReaderU32Get(&reader);
    payload->gnss_origin_height_mm = (int32_t)SslogRecords_ReaderU32Get(&reader);
    payload->gnss_sample_count = SslogRecords_ReaderU32Get(&reader);
    payload->gnss_horizontal_accuracy_m = SslogRecords_ReaderF32Get(&reader);
    payload->gnss_vertical_accuracy_m = SslogRecords_ReaderF32Get(&reader);
    payload->barometer_sample_count = SslogRecords_ReaderU32Get(&reader);
    payload->barometer_origin_pressure_pa = SslogRecords_ReaderF32Get(&reader);
    payload->barometer_origin_altitude_m = SslogRecords_ReaderF32Get(&reader);
    payload->attitude_state = SslogRecords_ReaderU8Get(&reader);
    payload->gnss_state = SslogRecords_ReaderU8Get(&reader);
    payload->barometer_state = SslogRecords_ReaderU8Get(&reader);
    payload->attitude_source = SslogRecords_ReaderU8Get(&reader);

    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_AlignmentEvidenceDeserialize(
    FlightLogAlignmentEvidenceRecord *payload,
    const uint8_t *buffer, uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT_OBJECT(payload, FlightLogAlignmentEvidenceRecord,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->alignment_algorithm = SslogRecords_ReaderU8Get(&reader);
    payload->constraint_count = SslogRecords_ReaderU8Get(&reader);
    payload->valid_pair_count = SslogRecords_ReaderU8Get(&reader);
    payload->yaw_authoritative = SslogRecords_ReaderU8Get(&reader);
    payload->imu_source_instance = SslogRecords_ReaderU8Get(&reader);
    payload->magnetometer_instance = SslogRecords_ReaderU8Get(&reader);
    payload->external_source_instance = SslogRecords_ReaderU8Get(&reader);
    payload->failure_reason = SslogRecords_ReaderU8Get(&reader);
    payload->magnetometer_physical_device_id =
        SslogRecords_ReaderU16Get(&reader);
    payload->flags = SslogRecords_ReaderU16Get(&reader);
    payload->mag_calibration_generation =
        SslogRecords_ReaderU32Get(&reader);
    payload->mag_calibration_set_hash =
        SslogRecords_ReaderU32Get(&reader);
    payload->first_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->last_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->minimum_pair_sine = SslogRecords_ReaderF32Get(&reader);
    payload->rms_mismatch_rad = SslogRecords_ReaderF32Get(&reader);
    payload->max_mismatch_rad = SslogRecords_ReaderF32Get(&reader);
    SILVERSTAR_ASSERT(reader.offset == buffer_size,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_MissionSnapshotIdentityDeserialize(
    FlightLogMissionSnapshotIdentityRecord *payload,
    const uint8_t *buffer, uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT_OBJECT(payload, FlightLogMissionSnapshotIdentityRecord,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->mission_id = SslogRecords_ReaderU32Get(&reader);
    payload->commit_generation = SslogRecords_ReaderU32Get(&reader);
    payload->snapshot_sequence = SslogRecords_ReaderU32Get(&reader);
    payload->imu_calibration_generation = SslogRecords_ReaderU32Get(&reader);
    payload->mag_calibration_set_hash = SslogRecords_ReaderU32Get(&reader);
    payload->base_instance = SslogRecords_ReaderU8Get(&reader);
    payload->ready = SslogRecords_ReaderU8Get(&reader);
    payload->reserved = SslogRecords_ReaderU16Get(&reader);
    SILVERSTAR_ASSERT(reader.offset == buffer_size,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_MagCalibrationIdentityDeserialize(
    FlightLogMagCalibrationIdentityRecord *payload,
    const uint8_t *buffer, uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };
    SILVERSTAR_ASSERT_OBJECT(payload, FlightLogMagCalibrationIdentityRecord,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->physical_device_id = SslogRecords_ReaderU16Get(&reader);
    payload->instance_id = SslogRecords_ReaderU8Get(&reader);
    payload->active = SslogRecords_ReaderU8Get(&reader);
    payload->saved = SslogRecords_ReaderU8Get(&reader);
    payload->load_error = SslogRecords_ReaderU8Get(&reader);
    payload->reserved = SslogRecords_ReaderU16Get(&reader);
    payload->generation = SslogRecords_ReaderU32Get(&reader);
    payload->calibration_set_hash = SslogRecords_ReaderU32Get(&reader);
    SILVERSTAR_ASSERT(reader.offset == buffer_size,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_MissionConfigDeserialize(
    FlightLogMissionConfigRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->alignment_algorithm = SslogRecords_ReaderU8Get(&reader);
    payload->rocket_longitudinal_axis = SslogRecords_ReaderU8Get(&reader);
    payload->deploy_trigger_mask = SslogRecords_ReaderU8Get(&reader);
    payload->tilt_reference = SslogRecords_ReaderU8Get(&reader);
    payload->landing_enable = SslogRecords_ReaderU8Get(&reader);
    payload->landing_mode = SslogRecords_ReaderU8Get(&reader);
    payload->impact_capable = SslogRecords_ReaderU8Get(&reader);
    payload->known_yaw_deg = SslogRecords_ReaderF32Get(&reader);
    payload->magnetic_declination_deg = SslogRecords_ReaderF32Get(&reader);
    payload->tilt_threshold_deg = SslogRecords_ReaderF32Get(&reader);
    payload->apogee_vz_threshold_mps = SslogRecords_ReaderF32Get(&reader);
    payload->deploy_confirm_ms = SslogRecords_ReaderU32Get(&reader);
    payload->deploy_delay_ms = SslogRecords_ReaderU32Get(&reader);
    payload->baro_trigger_window_ms = SslogRecords_ReaderU32Get(&reader);
    payload->baro_trigger_min_samples = SslogRecords_ReaderU32Get(&reader);
    payload->baro_trigger_rate_mps = SslogRecords_ReaderF32Get(&reader);
    payload->candidate_duration_ms = SslogRecords_ReaderU32Get(&reader);
    payload->baro_confirm_rate_mps = SslogRecords_ReaderF32Get(&reader);
    payload->baro_max_span_m = SslogRecords_ReaderF32Get(&reader);
    payload->candidate_baro_min_samples = SslogRecords_ReaderU32Get(&reader);
    payload->candidate_imu_min_samples = SslogRecords_ReaderU32Get(&reader);
    payload->candidate_min_coverage_percent = SslogRecords_ReaderU32Get(&reader);
    payload->impact_inhibit_ms = SslogRecords_ReaderU32Get(&reader);
    payload->impact_threshold_mps2 = SslogRecords_ReaderF32Get(&reader);
    payload->still_gyro_threshold_radps = SslogRecords_ReaderF32Get(&reader);
    payload->still_accel_tolerance_mps2 = SslogRecords_ReaderF32Get(&reader);
    payload->landing_confirm_ms = SslogRecords_ReaderU32Get(&reader);
    payload->landing_sample_max_age_ms = SslogRecords_ReaderU32Get(&reader);

    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_DeviceDescriptorDeserialize(
    FlightLogDeviceDescriptorRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->descriptor_id = SslogRecords_ReaderU16Get(&reader);
    payload->physical_device_id = SslogRecords_ReaderU16Get(&reader);
    payload->device_class = SslogRecords_ReaderU8Get(&reader);
    payload->instance_id = SslogRecords_ReaderU8Get(&reader);
    payload->driver_id = SslogRecords_ReaderU16Get(&reader);
    payload->flags = SslogRecords_ReaderU16Get(&reader);
    payload->capability_mask = SslogRecords_ReaderU32Get(&reader);
    payload->configured_rate_hz = SslogRecords_ReaderU32Get(&reader);
    payload->driver_name_hash = SslogRecords_ReaderU32Get(&reader);
    payload->model_name_hash = SslogRecords_ReaderU32Get(&reader);

    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_AlgorithmDescriptorDeserialize(
    FlightLogAlgorithmDescriptorRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->descriptor_id = SslogRecords_ReaderU16Get(&reader);
    payload->algorithm_class = SslogRecords_ReaderU8Get(&reader);
    payload->instance_id = SslogRecords_ReaderU8Get(&reader);
    payload->algorithm_id = SslogRecords_ReaderU16Get(&reader);
    payload->flags = SslogRecords_ReaderU16Get(&reader);
    payload->config_digest = SslogRecords_ReaderU32Get(&reader);
    payload->name_hash = SslogRecords_ReaderU32Get(&reader);

    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_LogStreamDescriptorDeserialize(
    FlightLogStreamDescriptorRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->record_type = SslogRecords_ReaderU8Get(&reader);
    payload->record_version = SslogRecords_ReaderU8Get(&reader);
    payload->enabled = SslogRecords_ReaderU8Get(&reader);
    payload->policy = SslogRecords_ReaderU8Get(&reader);
    payload->decimation = SslogRecords_ReaderU16Get(&reader);
    payload->reserved = SslogRecords_ReaderU16Get(&reader);
    payload->period_us = SslogRecords_ReaderU32Get(&reader);

    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_DecoderProfileDescriptorDeserialize(
    FlightLogDecoderProfileDescriptorRecord *payload,
    const uint8_t *buffer,
    uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };

    SILVERSTAR_ASSERT(payload != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    payload->package_schema_major = SslogRecords_ReaderU16Get(&reader);
    payload->package_schema_minor = SslogRecords_ReaderU16Get(&reader);
    payload->container_format_major = SslogRecords_ReaderU16Get(&reader);
    payload->container_format_minor = SslogRecords_ReaderU16Get(&reader);
    (void)memcpy(payload->record_catalog_hash_128,
        SslogRecords_ReadReserve(&reader, 16U), 16U);
    (void)memcpy(payload->project_semantics_hash_128,
        SslogRecords_ReadReserve(&reader, 16U), 16U);
    (void)memcpy(payload->generation_profile_hash_128,
        SslogRecords_ReadReserve(&reader, 16U), 16U);
    SslogRecords_ReaderSkip(&reader, 8U);
    SILVERSTAR_ASSERT(reader.offset == buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reader.offset;
}

static uint16_t SslogRecords_Sf6StateSerialize(
    const FlightLogSf6StateRecord *payload,
    uint8_t *buffer, uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };
    if (payload == NULL || buffer == NULL) { return 0U; }
    SILVERSTAR_ASSERT(buffer_size == FLIGHT_LOG_SF6_STATE_PAYLOAD_SIZE,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    SslogRecords_WriterU32Put(&writer, payload->snapshot_id);
    SslogRecords_WriterU8Put(&writer, payload->algorithm_id);
    SslogRecords_WriterU8Put(&writer, payload->algorithm_revision);
    SslogRecords_WriterU8Put(&writer, payload->health);
    SslogRecords_WriterU8Put(&writer, payload->reserved);
    for (uint16_t index = 0U; index < 3U; index++)
    {
        SslogRecords_WriterF32Put(&writer, payload->position_enu_m[index]);
    }
    for (uint16_t index = 0U; index < 3U; index++)
    {
        SslogRecords_WriterF32Put(&writer, payload->velocity_enu_mps[index]);
    }
    for (uint16_t index = 0U; index < 4U; index++)
    {
        SslogRecords_WriterF32Put(&writer, payload->q_nb[index]);
    }
    for (uint16_t index = 0U; index < 6U; index++)
    {
        SslogRecords_WriterF32Put(&writer, payload->gain[index]);
    }
    return (writer.offset == buffer_size) ? writer.offset : 0U;
}

static uint16_t SslogRecords_Sf6StateDeserialize(
    FlightLogSf6StateRecord *payload,
    const uint8_t *buffer, uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };
    if (payload == NULL || buffer == NULL) { return 0U; }
    SILVERSTAR_ASSERT(buffer_size == FLIGHT_LOG_SF6_STATE_PAYLOAD_SIZE,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    payload->snapshot_id = SslogRecords_ReaderU32Get(&reader);
    payload->algorithm_id = SslogRecords_ReaderU8Get(&reader);
    payload->algorithm_revision = SslogRecords_ReaderU8Get(&reader);
    payload->health = SslogRecords_ReaderU8Get(&reader);
    payload->reserved = SslogRecords_ReaderU8Get(&reader);
    for (uint16_t index = 0U; index < 3U; index++)
    {
        payload->position_enu_m[index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t index = 0U; index < 3U; index++)
    {
        payload->velocity_enu_mps[index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t index = 0U; index < 4U; index++)
    {
        payload->q_nb[index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t index = 0U; index < 6U; index++)
    {
        payload->gain[index] = SslogRecords_ReaderF32Get(&reader);
    }
    return (reader.offset == buffer_size) ? reader.offset : 0U;
}

static uint16_t SslogRecords_Sf6MeasurementSerialize(
    const FlightLogSf6MeasurementRecord *payload,
    uint8_t *buffer, uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };
    if (payload == NULL || buffer == NULL) { return 0U; }
    SILVERSTAR_ASSERT(buffer_size == FLIGHT_LOG_SF6_MEASUREMENT_PAYLOAD_SIZE,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    SslogRecords_WriterU64Put(&writer, payload->sample_timestamp_us);
    SslogRecords_WriterU64Put(&writer, payload->receive_timestamp_us);
    SslogRecords_WriterU64Put(&writer, payload->measurement_timestamp_us);
    SslogRecords_WriterU64Put(&writer, payload->evaluation_timestamp_us);
    SslogRecords_WriterU64Put(&writer, payload->boundary_timestamp_us);
    SslogRecords_WriterU32Put(&writer, payload->sequence);
    SslogRecords_WriterU8Put(&writer, payload->group);
    SslogRecords_WriterU8Put(&writer, payload->physically_valid);
    SslogRecords_WriterU8Put(&writer, payload->result);
    SslogRecords_WriterU8Put(&writer, payload->effective_update);
    for (uint16_t index = 0U; index < 2U; index++)
    {
        SslogRecords_WriterF32Put(&writer, payload->observation[index]);
    }
    return (writer.offset == buffer_size) ? writer.offset : 0U;
}

static uint16_t SslogRecords_Sf6MeasurementDeserialize(
    FlightLogSf6MeasurementRecord *payload,
    const uint8_t *buffer, uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };
    if (payload == NULL || buffer == NULL) { return 0U; }
    SILVERSTAR_ASSERT(buffer_size == FLIGHT_LOG_SF6_MEASUREMENT_PAYLOAD_SIZE,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    payload->sample_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->receive_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->measurement_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->evaluation_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->boundary_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->sequence = SslogRecords_ReaderU32Get(&reader);
    payload->group = SslogRecords_ReaderU8Get(&reader);
    payload->physically_valid = SslogRecords_ReaderU8Get(&reader);
    payload->result = SslogRecords_ReaderU8Get(&reader);
    payload->effective_update = SslogRecords_ReaderU8Get(&reader);
    for (uint16_t index = 0U; index < 2U; index++)
    {
        payload->observation[index] = SslogRecords_ReaderF32Get(&reader);
    }
    return (reader.offset == buffer_size) ? reader.offset : 0U;
}

static uint16_t SslogRecords_Eskf15StateSerialize(
    const FlightLogEskf15StateRecord *payload,
    uint8_t *buffer, uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };
    if ((payload == NULL) || (buffer == NULL)) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(payload, FlightLogEskf15StateRecord,
                             SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    SILVERSTAR_ASSERT(buffer_size == 144U, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    SslogRecords_WriterU32Put(&writer, payload->snapshot_id);
    SslogRecords_WriterU32Put(&writer, payload->epoch);
    SslogRecords_WriterU32Put(&writer, payload->source_id);
    SslogRecords_WriterU32Put(&writer, payload->calibration_generation);
    SslogRecords_WriterU8Put(&writer, payload->algorithm_id);
    SslogRecords_WriterU8Put(&writer, payload->algorithm_revision);
    SslogRecords_WriterU8Put(&writer, payload->quality_revision);
    SslogRecords_WriterU8Put(&writer, payload->health);
    for (uint16_t index = 0U; index < 3U; index++)
    {
        SslogRecords_WriterF32Put(&writer, payload->position_enu_m[index]);
    }
    for (uint16_t index = 0U; index < 3U; index++)
    {
        SslogRecords_WriterF32Put(&writer, payload->velocity_enu_mps[index]);
    }
    for (uint16_t index = 0U; index < 4U; index++)
    {
        SslogRecords_WriterF32Put(&writer, payload->q_nb[index]);
    }
    for (uint16_t index = 0U; index < 3U; index++)
    {
        SslogRecords_WriterF32Put(&writer, payload->gyro_bias_radps[index]);
    }
    for (uint16_t index = 0U; index < 3U; index++)
    {
        SslogRecords_WriterF32Put(&writer, payload->accel_bias_mps2[index]);
    }
    for (uint16_t index = 0U; index < 15U; index++)
    {
        SslogRecords_WriterF32Put(&writer, payload->p_diagonal[index]);
    }
    return (writer.offset == buffer_size) ? writer.offset : 0U;
}

static uint16_t SslogRecords_Eskf15StateDeserialize(
    FlightLogEskf15StateRecord *payload,
    const uint8_t *buffer, uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };
    if ((payload == NULL) || (buffer == NULL)) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(payload, FlightLogEskf15StateRecord,
                             SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    SILVERSTAR_ASSERT(buffer_size == 144U, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    payload->snapshot_id = SslogRecords_ReaderU32Get(&reader);
    payload->epoch = SslogRecords_ReaderU32Get(&reader);
    payload->source_id = SslogRecords_ReaderU32Get(&reader);
    payload->calibration_generation = SslogRecords_ReaderU32Get(&reader);
    payload->algorithm_id = SslogRecords_ReaderU8Get(&reader);
    payload->algorithm_revision = SslogRecords_ReaderU8Get(&reader);
    payload->quality_revision = SslogRecords_ReaderU8Get(&reader);
    payload->health = SslogRecords_ReaderU8Get(&reader);
    for (uint16_t index = 0U; index < 3U; index++)
    {
        payload->position_enu_m[index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t index = 0U; index < 3U; index++)
    {
        payload->velocity_enu_mps[index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t index = 0U; index < 4U; index++)
    {
        payload->q_nb[index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t index = 0U; index < 3U; index++)
    {
        payload->gyro_bias_radps[index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t index = 0U; index < 3U; index++)
    {
        payload->accel_bias_mps2[index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t index = 0U; index < 15U; index++)
    {
        payload->p_diagonal[index] = SslogRecords_ReaderF32Get(&reader);
    }
    return (reader.offset == buffer_size) ? reader.offset : 0U;
}

static uint16_t SslogRecords_Eskf15CovariancePartSerialize(
    const FlightLogEskf15CovariancePartRecord *payload,
    uint8_t *buffer, uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };
    if ((payload == NULL) || (buffer == NULL)) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(payload, FlightLogEskf15CovariancePartRecord,
                             SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    SILVERSTAR_ASSERT(buffer_size == 144U, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    SslogRecords_WriterU32Put(&writer, payload->snapshot_id);
    SslogRecords_WriterU32Put(&writer, payload->epoch);
    SslogRecords_WriterU32Put(&writer, payload->source_id);
    SslogRecords_WriterU32Put(&writer, payload->calibration_generation);
    SslogRecords_WriterU8Put(&writer, payload->algorithm_id);
    SslogRecords_WriterU8Put(&writer, payload->phase);
    SslogRecords_WriterU8Put(&writer, payload->part_index);
    SslogRecords_WriterU8Put(&writer, payload->part_count);
    SslogRecords_WriterU16Put(&writer, payload->offset);
    SslogRecords_WriterU16Put(&writer, payload->count);
    for (uint16_t index = 0U; index < 30U; index++)
    {
        SslogRecords_WriterF32Put(&writer, payload->values[index]);
    }
    return (writer.offset == buffer_size) ? writer.offset : 0U;
}

static uint16_t SslogRecords_Eskf15CovariancePartDeserialize(
    FlightLogEskf15CovariancePartRecord *payload,
    const uint8_t *buffer, uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };
    if ((payload == NULL) || (buffer == NULL)) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(payload, FlightLogEskf15CovariancePartRecord,
                             SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    SILVERSTAR_ASSERT(buffer_size == 144U, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    payload->snapshot_id = SslogRecords_ReaderU32Get(&reader);
    payload->epoch = SslogRecords_ReaderU32Get(&reader);
    payload->source_id = SslogRecords_ReaderU32Get(&reader);
    payload->calibration_generation = SslogRecords_ReaderU32Get(&reader);
    payload->algorithm_id = SslogRecords_ReaderU8Get(&reader);
    payload->phase = SslogRecords_ReaderU8Get(&reader);
    payload->part_index = SslogRecords_ReaderU8Get(&reader);
    payload->part_count = SslogRecords_ReaderU8Get(&reader);
    payload->offset = SslogRecords_ReaderU16Get(&reader);
    payload->count = SslogRecords_ReaderU16Get(&reader);
    for (uint16_t index = 0U; index < 30U; index++)
    {
        payload->values[index] = SslogRecords_ReaderF32Get(&reader);
    }
    return (reader.offset == buffer_size) ? reader.offset : 0U;
}

static uint16_t SslogRecords_Eskf15MeasurementSerialize(
    const FlightLogEskf15MeasurementRecord *payload,
    uint8_t *buffer, uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };
    if ((payload == NULL) || (buffer == NULL)) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(payload, FlightLogEskf15MeasurementRecord,
                             SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    SILVERSTAR_ASSERT(buffer_size == 100U, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    SslogRecords_WriterU64Put(&writer, payload->sample_timestamp_us);
    SslogRecords_WriterU64Put(&writer, payload->receive_timestamp_us);
    SslogRecords_WriterU64Put(&writer, payload->measurement_timestamp_us);
    SslogRecords_WriterU64Put(&writer, payload->evaluation_timestamp_us);
    SslogRecords_WriterU32Put(&writer, payload->operation_sequence);
    SslogRecords_WriterU32Put(&writer, payload->epoch);
    SslogRecords_WriterU32Put(&writer, payload->source_id);
    SslogRecords_WriterU32Put(&writer, payload->calibration_generation);
    SslogRecords_WriterU8Put(&writer, payload->group);
    SslogRecords_WriterU8Put(&writer, payload->physically_valid);
    SslogRecords_WriterU8Put(&writer, payload->admitted);
    SslogRecords_WriterU8Put(&writer, payload->update_result);
    for (uint16_t index = 0U; index < 2U; index++)
    {
        SslogRecords_WriterF32Put(&writer, payload->observation[index]);
    }
    for (uint16_t index = 0U; index < 2U; index++)
    {
        SslogRecords_WriterF32Put(&writer, payload->innovation[index]);
    }
    for (uint16_t index = 0U; index < 2U; index++)
    {
        SslogRecords_WriterF32Put(&writer, payload->base_variance[index]);
    }
    for (uint16_t index = 0U; index < 2U; index++)
    {
        SslogRecords_WriterF32Put(&writer, payload->effective_variance[index]);
    }
    SslogRecords_WriterF32Put(&writer, payload->nis);
    SslogRecords_WriterF32Put(&writer, payload->quality_scale);
    SslogRecords_WriterF32Put(&writer, payload->consistency_scale);
    SslogRecords_WriterF32Put(&writer, payload->robust_scale);
    return (writer.offset == buffer_size) ? writer.offset : 0U;
}

static uint16_t SslogRecords_Eskf15MeasurementDeserialize(
    FlightLogEskf15MeasurementRecord *payload,
    const uint8_t *buffer, uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };
    if ((payload == NULL) || (buffer == NULL)) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(payload, FlightLogEskf15MeasurementRecord,
                             SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    SILVERSTAR_ASSERT(buffer_size == 100U, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    payload->sample_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->receive_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->measurement_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->evaluation_timestamp_us = SslogRecords_ReaderU64Get(&reader);
    payload->operation_sequence = SslogRecords_ReaderU32Get(&reader);
    payload->epoch = SslogRecords_ReaderU32Get(&reader);
    payload->source_id = SslogRecords_ReaderU32Get(&reader);
    payload->calibration_generation = SslogRecords_ReaderU32Get(&reader);
    payload->group = SslogRecords_ReaderU8Get(&reader);
    payload->physically_valid = SslogRecords_ReaderU8Get(&reader);
    payload->admitted = SslogRecords_ReaderU8Get(&reader);
    payload->update_result = SslogRecords_ReaderU8Get(&reader);
    for (uint16_t index = 0U; index < 2U; index++)
    {
        payload->observation[index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t index = 0U; index < 2U; index++)
    {
        payload->innovation[index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t index = 0U; index < 2U; index++)
    {
        payload->base_variance[index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t index = 0U; index < 2U; index++)
    {
        payload->effective_variance[index] = SslogRecords_ReaderF32Get(&reader);
    }
    payload->nis = SslogRecords_ReaderF32Get(&reader);
    payload->quality_scale = SslogRecords_ReaderF32Get(&reader);
    payload->consistency_scale = SslogRecords_ReaderF32Get(&reader);
    payload->robust_scale = SslogRecords_ReaderF32Get(&reader);
    return (reader.offset == buffer_size) ? reader.offset : 0U;
}

static uint16_t SslogRecords_Eskf15BodyInputSerialize(
    const FlightLogEskf15BodyInputRecord *payload,
    uint8_t *buffer, uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };
    if ((payload == NULL) || (buffer == NULL)) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(payload, FlightLogEskf15BodyInputRecord,
                             SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    SILVERSTAR_ASSERT(buffer_size == 84U, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
        SslogRecords_WriterU64Put(&writer, payload->interval_start_timestamp_us);
        SslogRecords_WriterU64Put(&writer, payload->interval_end_timestamp_us);
        SslogRecords_WriterU32Put(&writer, payload->sequence);
        SslogRecords_WriterU32Put(&writer, payload->source_id);
        SslogRecords_WriterU32Put(&writer, payload->calibration_generation);
        SslogRecords_WriterU32Put(&writer, payload->quality_flags);
        SslogRecords_WriterF32Put(&writer, payload->dt_s);
    for (uint16_t index = 0U; index < 6U; index++)
    {
        SslogRecords_WriterF32Put(&writer, payload->body_gyro_radps[index]);
    }
    for (uint16_t index = 0U; index < 6U; index++)
    {
        SslogRecords_WriterF32Put(&writer, payload->body_accel_mps2[index]);
    }
    return (writer.offset == buffer_size) ? writer.offset : 0U;
}

static uint16_t SslogRecords_Eskf15BodyInputDeserialize(
    FlightLogEskf15BodyInputRecord *payload,
    const uint8_t *buffer, uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };
    if ((payload == NULL) || (buffer == NULL)) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(payload, FlightLogEskf15BodyInputRecord,
                             SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    SILVERSTAR_ASSERT(buffer_size == 84U, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
        payload->interval_start_timestamp_us = SslogRecords_ReaderU64Get(&reader);
        payload->interval_end_timestamp_us = SslogRecords_ReaderU64Get(&reader);
        payload->sequence = SslogRecords_ReaderU32Get(&reader);
        payload->source_id = SslogRecords_ReaderU32Get(&reader);
        payload->calibration_generation = SslogRecords_ReaderU32Get(&reader);
        payload->quality_flags = SslogRecords_ReaderU32Get(&reader);
        payload->dt_s = SslogRecords_ReaderF32Get(&reader);
    for (uint16_t index = 0U; index < 6U; index++)
    {
        payload->body_gyro_radps[index] = SslogRecords_ReaderF32Get(&reader);
    }
    for (uint16_t index = 0U; index < 6U; index++)
    {
        payload->body_accel_mps2[index] = SslogRecords_ReaderF32Get(&reader);
    }
    return (reader.offset == buffer_size) ? reader.offset : 0U;
}

static uint16_t SslogRecords_NavigationQualitySerialize(
    const FlightLogNavigationQualityRecord *payload,
    uint8_t *buffer, uint16_t buffer_size)
{
    SslogWriteCursor writer = { buffer, buffer_size, 0U };
    if ((payload == NULL) || (buffer == NULL)) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(payload, FlightLogNavigationQualityRecord,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    if (buffer_size != FLIGHT_LOG_NAV_QUALITY_PAYLOAD_SIZE) { return 0U; }
        SslogRecords_WriterU64Put(&writer, payload->native_epoch_us);
        SslogRecords_WriterU64Put(&writer, payload->receive_us);
        SslogRecords_WriterU64Put(&writer, payload->evaluation_us);
        SslogRecords_WriterU64Put(&writer, payload->window_start_us);
        SslogRecords_WriterU64Put(&writer, payload->window_end_us);
        SslogRecords_WriterU64Put(&writer, payload->evidence_age_us);
        SslogRecords_WriterU32Put(&writer, payload->native_sequence);
        SslogRecords_WriterU32Put(&writer, payload->source_id);
        SslogRecords_WriterU32Put(&writer, payload->calibration_generation);
        SslogRecords_WriterU32Put(&writer, payload->covered_us);
        SslogRecords_WriterU32Put(&writer, payload->position_epoch_count);
        SslogRecords_WriterU32Put(&writer, payload->velocity_epoch_count);
    for (uint16_t index = 0U; index < 2U; index++)
    {
        SslogRecords_WriterF32Put(&writer, payload->closure_en_m[index]);
    }
        SslogRecords_WriterF32Put(&writer, payload->closure_norm_m);
        SslogRecords_WriterF32Put(&writer, payload->variance_scale);
        SslogRecords_WriterU8Put(&writer, payload->quality_revision);
        SslogRecords_WriterU8Put(&writer, payload->physical_mask);
        SslogRecords_WriterU8Put(&writer, payload->admitted_mask);
        SslogRecords_WriterU8Put(&writer, payload->accepted_mask);
        SslogRecords_WriterU8Put(&writer, payload->nav_output_valid);
        SslogRecords_WriterU8Put(&writer, payload->health);
        SslogRecords_WriterU8Put(&writer, payload->evidence_valid);
        SslogRecords_WriterU8Put(&writer, payload->numsv);
        SslogRecords_WriterU8Put(&writer, payload->window_reason);
        SslogRecords_WriterU8Put(&writer, payload->numsv_valid);
        SslogRecords_WriterU8Put(&writer, payload->window_index);
        SslogRecords_WriterU8Put(&writer, payload->quality_degraded_mask);
    return (writer.offset == buffer_size) ? writer.offset : 0U;
}

static uint16_t SslogRecords_NavigationQualityDeserialize(
    FlightLogNavigationQualityRecord *payload,
    const uint8_t *buffer, uint16_t buffer_size)
{
    SslogReadCursor reader = { buffer, buffer_size, 0U };
    if ((payload == NULL) || (buffer == NULL)) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(payload, FlightLogNavigationQualityRecord,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    if (buffer_size != FLIGHT_LOG_NAV_QUALITY_PAYLOAD_SIZE) { return 0U; }
        payload->native_epoch_us = SslogRecords_ReaderU64Get(&reader);
        payload->receive_us = SslogRecords_ReaderU64Get(&reader);
        payload->evaluation_us = SslogRecords_ReaderU64Get(&reader);
        payload->window_start_us = SslogRecords_ReaderU64Get(&reader);
        payload->window_end_us = SslogRecords_ReaderU64Get(&reader);
        payload->evidence_age_us = SslogRecords_ReaderU64Get(&reader);
        payload->native_sequence = SslogRecords_ReaderU32Get(&reader);
        payload->source_id = SslogRecords_ReaderU32Get(&reader);
        payload->calibration_generation = SslogRecords_ReaderU32Get(&reader);
        payload->covered_us = SslogRecords_ReaderU32Get(&reader);
        payload->position_epoch_count = SslogRecords_ReaderU32Get(&reader);
        payload->velocity_epoch_count = SslogRecords_ReaderU32Get(&reader);
    for (uint16_t index = 0U; index < 2U; index++)
    {
        payload->closure_en_m[index] = SslogRecords_ReaderF32Get(&reader);
    }
        payload->closure_norm_m = SslogRecords_ReaderF32Get(&reader);
        payload->variance_scale = SslogRecords_ReaderF32Get(&reader);
        payload->quality_revision = SslogRecords_ReaderU8Get(&reader);
        payload->physical_mask = SslogRecords_ReaderU8Get(&reader);
        payload->admitted_mask = SslogRecords_ReaderU8Get(&reader);
        payload->accepted_mask = SslogRecords_ReaderU8Get(&reader);
        payload->nav_output_valid = SslogRecords_ReaderU8Get(&reader);
        payload->health = SslogRecords_ReaderU8Get(&reader);
        payload->evidence_valid = SslogRecords_ReaderU8Get(&reader);
        payload->numsv = SslogRecords_ReaderU8Get(&reader);
        payload->window_reason = SslogRecords_ReaderU8Get(&reader);
        payload->numsv_valid = SslogRecords_ReaderU8Get(&reader);
        payload->window_index = SslogRecords_ReaderU8Get(&reader);
        payload->quality_degraded_mask = SslogRecords_ReaderU8Get(&reader);
    return (reader.offset == buffer_size) ? reader.offset : 0U;
}

static uint16_t SslogRecords_PayloadSerializeLow(
    const FlightLogRecord *record,
    uint8_t *buffer,
    uint16_t payload_size)
{
    SILVERSTAR_ASSERT(record != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    switch ((uint32_t)record->record_type)
    {
        case FLIGHT_LOG_RECORD_EVENT: return SslogRecords_EventSerialize(
            &record->payload.event, buffer, payload_size);
        case FLIGHT_LOG_RECORD_STATS: return SslogRecords_StatsSerialize(
            &record->payload.stats, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ESTIMATOR: return SslogRecords_EstimatorSerialize(
            &record->payload.estimator, buffer, payload_size);
        case FLIGHT_LOG_RECORD_SYSTEM_CONFIG: return SslogRecords_SystemConfigSerialize(
            &record->payload.system_config, buffer, payload_size);
        case FLIGHT_LOG_RECORD_PURE_INS: return SslogRecords_PureInsSerialize(
            &record->payload.pure_ins, buffer, payload_size);
        case FLIGHT_LOG_RECORD_KF6_DIAGNOSTIC: return SslogRecords_Kf6DiagnosticSerialize(
            &record->payload.kf6_diagnostic, buffer, payload_size);
        case FLIGHT_LOG_RECORD_KF6_FULL_P: return SslogRecords_Kf6FullPSerialize(
            &record->payload.kf6_full_p, buffer, payload_size);
        case FLIGHT_LOG_RECORD_POWER: return SslogRecords_PowerSerialize(
            &record->payload.power, buffer, payload_size);
        case FLIGHT_LOG_RECORD_HEALTH: return SslogRecords_HealthSerialize(
            &record->payload.health, buffer, payload_size);
        case FLIGHT_LOG_RECORD_TELEMETRY_DIAG: return SslogRecords_TelemetryDiagSerialize(
            &record->payload.telemetry_diagnostic, buffer, payload_size);
        case FLIGHT_LOG_RECORD_INITIAL_STATE: return SslogRecords_InitialStateSerialize(
            &record->payload.initial_state, buffer, payload_size);
        default: return 0U;
    }
}

static uint16_t SslogRecords_PayloadNavigationSerialize(
    const FlightLogRecord *record,
    uint8_t *buffer, uint16_t payload_size)
{
    SILVERSTAR_ASSERT_OBJECT(record, FlightLogRecord, SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    switch ((uint32_t)record->record_type)
    {
        case FLIGHT_LOG_RECORD_SF6_STATE: return SslogRecords_Sf6StateSerialize(
            &record->payload.sf6_state, buffer, payload_size);
        case FLIGHT_LOG_RECORD_SF6_MEASUREMENT: return SslogRecords_Sf6MeasurementSerialize(
            &record->payload.sf6_measurement, buffer, payload_size);
        case FLIGHT_LOG_RECORD_MAG_CALIBRATION_IDENTITY: return
            SslogRecords_MagCalibrationIdentitySerialize(
                &record->payload.mag_calibration_identity,
                buffer, payload_size);
        case FLIGHT_LOG_RECORD_MISSION_SNAPSHOT_IDENTITY: return
            SslogRecords_MissionSnapshotIdentitySerialize(
                &record->payload.mission_snapshot_identity,
                buffer, payload_size);
        case FLIGHT_LOG_RECORD_ALIGNMENT_EVIDENCE: return
            SslogRecords_AlignmentEvidenceSerialize(
                &record->payload.alignment_evidence, buffer, payload_size);
        case FLIGHT_LOG_RECORD_NAV_QUALITY: return SslogRecords_NavigationQualitySerialize(
            &record->payload.navigation_quality, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ESKF15_BODY_INPUT: return SslogRecords_Eskf15BodyInputSerialize(
            &record->payload.eskf15_body_input, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ESKF15_STATE: return SslogRecords_Eskf15StateSerialize(
            &record->payload.eskf15_state, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ESKF15_FULL_P_PART: return SslogRecords_Eskf15CovariancePartSerialize(
            &record->payload.eskf15_full_p_part, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ESKF15_INITIAL_STATE: return SslogRecords_Eskf15StateSerialize(
            &record->payload.eskf15_initial_state, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ESKF15_INITIAL_P_PART: return SslogRecords_Eskf15CovariancePartSerialize(
            &record->payload.eskf15_initial_p_part, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ESKF15_MEASUREMENT: return SslogRecords_Eskf15MeasurementSerialize(
            &record->payload.eskf15_measurement, buffer, payload_size);
        default: return 0U;
    }
}

static uint16_t SslogRecords_PayloadSerializeHigh(
    const FlightLogRecord *record,
    uint8_t *buffer,
    uint16_t payload_size)
{
    SILVERSTAR_ASSERT(record != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    if (record->record_type >= FLIGHT_LOG_RECORD_ESKF15_STATE)
    { return SslogRecords_PayloadNavigationSerialize(record, buffer, payload_size); }
    switch ((uint32_t)record->record_type)
    {
        case FLIGHT_LOG_RECORD_GNSS_NATIVE: return SslogRecords_GnssNativeSerialize(
            &record->payload.gnss_native, buffer, payload_size);
        case FLIGHT_LOG_RECORD_BARO_NATIVE: return SslogRecords_BaroNativeSerialize(
            &record->payload.baro_native, buffer, payload_size);
        case FLIGHT_LOG_RECORD_MAG_NATIVE: return SslogRecords_MagNativeSerialize(
            &record->payload.mag_native, buffer, payload_size);
        case FLIGHT_LOG_RECORD_INERTIAL_INCREMENT: return SslogRecords_InertialIncrementSerialize(
            &record->payload.inertial_increment, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ESTIMATOR_STEP: return SslogRecords_EstimatorStepSerialize(
            &record->payload.estimator_step, buffer, payload_size);
        case FLIGHT_LOG_RECORD_GNSS_RECOVERY: return SslogRecords_GnssRecoverySerialize(
            &record->payload.gnss_recovery, buffer, payload_size);
        case FLIGHT_LOG_RECORD_LANDING_DIAGNOSTIC: return SslogRecords_LandingDiagnosticSerialize(
            &record->payload.landing_diagnostic, buffer, payload_size);
        case FLIGHT_LOG_RECORD_GNSS_MEASUREMENT: return SslogRecords_GnssMeasurementSerialize(
            &record->payload.gnss_measurement, buffer, payload_size);
        case FLIGHT_LOG_RECORD_BARO_MEASUREMENT: return SslogRecords_BaroMeasurementSerialize(
            &record->payload.baro_measurement, buffer, payload_size);
        case FLIGHT_LOG_RECORD_IMU_CORRECTED: return SslogRecords_ImuCorrectedSerialize(
            &record->payload.imu_corrected, buffer, payload_size);
        case FLIGHT_LOG_RECORD_CALIBRATION_RESULT: return SslogRecords_CalibrationResultSerialize(
            &record->payload.calibration_result, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ALIGNMENT_RESULT: return SslogRecords_AlignmentResultSerialize(
            &record->payload.alignment_result, buffer, payload_size);
        case FLIGHT_LOG_RECORD_MISSION_CONFIG: return SslogRecords_MissionConfigSerialize(
            &record->payload.mission_config, buffer, payload_size);
        case FLIGHT_LOG_RECORD_DEVICE_DESCRIPTOR: return SslogRecords_DeviceDescriptorSerialize(
            &record->payload.device_descriptor, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ALGORITHM_DESCRIPTOR: return SslogRecords_AlgorithmDescriptorSerialize(
            &record->payload.algorithm_descriptor, buffer, payload_size);
        case FLIGHT_LOG_RECORD_LOG_STREAM_DESCRIPTOR: return SslogRecords_LogStreamDescriptorSerialize(
            &record->payload.stream_descriptor, buffer, payload_size);
        case FLIGHT_LOG_RECORD_DECODER_PROFILE_DESCRIPTOR: return SslogRecords_DecoderProfileDescriptorSerialize(
            &record->payload.decoder_profile_descriptor, buffer, payload_size);
        default: return 0U;
    }
}

uint16_t SslogRecords_PayloadSerialize(const FlightLogRecord *record,
    uint8_t *buffer, uint16_t buffer_capacity)
{
    const SslogRecordMetadata *metadata;

    if ((record == NULL) || (buffer == NULL))
    {
        return 0U;
    }
    metadata = SslogRecords_MetadataGet(record->record_type);
    if ((metadata == NULL) || (buffer_capacity < metadata->payload_size))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT(metadata->payload_size != 0U,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    SILVERSTAR_ASSERT(metadata->payload_size <= buffer_capacity,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    if ((uint32_t)record->record_type <=
        (uint32_t)FLIGHT_LOG_RECORD_INITIAL_STATE)
    {
        return SslogRecords_PayloadSerializeLow(
            record, buffer, metadata->payload_size);
    }
    return SslogRecords_PayloadSerializeHigh(
        record, buffer, metadata->payload_size);
}

static uint16_t SslogRecords_PayloadDeserializeLow(
    FlightLogRecord *record,
    const uint8_t *buffer,
    uint16_t payload_size)
{
    SILVERSTAR_ASSERT(record != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    switch ((uint32_t)record->record_type)
    {
        case FLIGHT_LOG_RECORD_EVENT: return SslogRecords_EventDeserialize(
            &record->payload.event, buffer, payload_size);
        case FLIGHT_LOG_RECORD_STATS: return SslogRecords_StatsDeserialize(
            &record->payload.stats, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ESTIMATOR: return SslogRecords_EstimatorDeserialize(
            &record->payload.estimator, buffer, payload_size);
        case FLIGHT_LOG_RECORD_SYSTEM_CONFIG: return SslogRecords_SystemConfigDeserialize(
            &record->payload.system_config, buffer, payload_size);
        case FLIGHT_LOG_RECORD_PURE_INS: return SslogRecords_PureInsDeserialize(
            &record->payload.pure_ins, buffer, payload_size);
        case FLIGHT_LOG_RECORD_KF6_DIAGNOSTIC: return SslogRecords_Kf6DiagnosticDeserialize(
            &record->payload.kf6_diagnostic, buffer, payload_size);
        case FLIGHT_LOG_RECORD_KF6_FULL_P: return SslogRecords_Kf6FullPDeserialize(
            &record->payload.kf6_full_p, buffer, payload_size);
        case FLIGHT_LOG_RECORD_POWER: return SslogRecords_PowerDeserialize(
            &record->payload.power, buffer, payload_size);
        case FLIGHT_LOG_RECORD_HEALTH: return SslogRecords_HealthDeserialize(
            &record->payload.health, buffer, payload_size);
        case FLIGHT_LOG_RECORD_TELEMETRY_DIAG: return SslogRecords_TelemetryDiagDeserialize(
            &record->payload.telemetry_diagnostic, buffer, payload_size);
        case FLIGHT_LOG_RECORD_INITIAL_STATE: return SslogRecords_InitialStateDeserialize(
            &record->payload.initial_state, buffer, payload_size);
        default: return 0U;
    }
}

static uint16_t SslogRecords_PayloadNavigationDeserialize(
    FlightLogRecord *record,
    const uint8_t *buffer, uint16_t payload_size)
{
    SILVERSTAR_ASSERT_OBJECT(record, FlightLogRecord, SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    switch ((uint32_t)record->record_type)
    {
        case FLIGHT_LOG_RECORD_SF6_STATE: return SslogRecords_Sf6StateDeserialize(
            &record->payload.sf6_state, buffer, payload_size);
        case FLIGHT_LOG_RECORD_SF6_MEASUREMENT: return SslogRecords_Sf6MeasurementDeserialize(
            &record->payload.sf6_measurement, buffer, payload_size);
        case FLIGHT_LOG_RECORD_MAG_CALIBRATION_IDENTITY: return
            SslogRecords_MagCalibrationIdentityDeserialize(
                &record->payload.mag_calibration_identity,
                buffer, payload_size);
        case FLIGHT_LOG_RECORD_MISSION_SNAPSHOT_IDENTITY: return
            SslogRecords_MissionSnapshotIdentityDeserialize(
                &record->payload.mission_snapshot_identity,
                buffer, payload_size);
        case FLIGHT_LOG_RECORD_ALIGNMENT_EVIDENCE: return
            SslogRecords_AlignmentEvidenceDeserialize(
                &record->payload.alignment_evidence, buffer, payload_size);
        case FLIGHT_LOG_RECORD_NAV_QUALITY: return SslogRecords_NavigationQualityDeserialize(
            &record->payload.navigation_quality, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ESKF15_BODY_INPUT: return SslogRecords_Eskf15BodyInputDeserialize(
            &record->payload.eskf15_body_input, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ESKF15_STATE: return SslogRecords_Eskf15StateDeserialize(
            &record->payload.eskf15_state, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ESKF15_FULL_P_PART: return SslogRecords_Eskf15CovariancePartDeserialize(
            &record->payload.eskf15_full_p_part, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ESKF15_INITIAL_STATE: return SslogRecords_Eskf15StateDeserialize(
            &record->payload.eskf15_initial_state, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ESKF15_INITIAL_P_PART: return SslogRecords_Eskf15CovariancePartDeserialize(
            &record->payload.eskf15_initial_p_part, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ESKF15_MEASUREMENT: return SslogRecords_Eskf15MeasurementDeserialize(
            &record->payload.eskf15_measurement, buffer, payload_size);
        default: return 0U;
    }
}

static uint16_t SslogRecords_PayloadDeserializeHigh(
    FlightLogRecord *record,
    const uint8_t *buffer,
    uint16_t payload_size)
{
    SILVERSTAR_ASSERT(record != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(buffer != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    if (record->record_type >= FLIGHT_LOG_RECORD_ESKF15_STATE)
    { return SslogRecords_PayloadNavigationDeserialize(record, buffer, payload_size); }
    switch ((uint32_t)record->record_type)
    {
        case FLIGHT_LOG_RECORD_GNSS_NATIVE: return SslogRecords_GnssNativeDeserialize(
            &record->payload.gnss_native, buffer, payload_size);
        case FLIGHT_LOG_RECORD_BARO_NATIVE: return SslogRecords_BaroNativeDeserialize(
            &record->payload.baro_native, buffer, payload_size);
        case FLIGHT_LOG_RECORD_MAG_NATIVE: return SslogRecords_MagNativeDeserialize(
            &record->payload.mag_native, buffer, payload_size);
        case FLIGHT_LOG_RECORD_INERTIAL_INCREMENT: return SslogRecords_InertialIncrementDeserialize(
            &record->payload.inertial_increment, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ESTIMATOR_STEP: return SslogRecords_EstimatorStepDeserialize(
            &record->payload.estimator_step, buffer, payload_size);
        case FLIGHT_LOG_RECORD_GNSS_RECOVERY: return SslogRecords_GnssRecoveryDeserialize(
            &record->payload.gnss_recovery, buffer, payload_size);
        case FLIGHT_LOG_RECORD_LANDING_DIAGNOSTIC: return SslogRecords_LandingDiagnosticDeserialize(
            &record->payload.landing_diagnostic, buffer, payload_size);
        case FLIGHT_LOG_RECORD_GNSS_MEASUREMENT: return SslogRecords_GnssMeasurementDeserialize(
            &record->payload.gnss_measurement, buffer, payload_size);
        case FLIGHT_LOG_RECORD_BARO_MEASUREMENT: return SslogRecords_BaroMeasurementDeserialize(
            &record->payload.baro_measurement, buffer, payload_size);
        case FLIGHT_LOG_RECORD_IMU_CORRECTED: return SslogRecords_ImuCorrectedDeserialize(
            &record->payload.imu_corrected, buffer, payload_size);
        case FLIGHT_LOG_RECORD_CALIBRATION_RESULT: return SslogRecords_CalibrationResultDeserialize(
            &record->payload.calibration_result, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ALIGNMENT_RESULT: return SslogRecords_AlignmentResultDeserialize(
            &record->payload.alignment_result, buffer, payload_size);
        case FLIGHT_LOG_RECORD_MISSION_CONFIG: return SslogRecords_MissionConfigDeserialize(
            &record->payload.mission_config, buffer, payload_size);
        case FLIGHT_LOG_RECORD_DEVICE_DESCRIPTOR: return SslogRecords_DeviceDescriptorDeserialize(
            &record->payload.device_descriptor, buffer, payload_size);
        case FLIGHT_LOG_RECORD_ALGORITHM_DESCRIPTOR: return SslogRecords_AlgorithmDescriptorDeserialize(
            &record->payload.algorithm_descriptor, buffer, payload_size);
        case FLIGHT_LOG_RECORD_LOG_STREAM_DESCRIPTOR: return SslogRecords_LogStreamDescriptorDeserialize(
            &record->payload.stream_descriptor, buffer, payload_size);
        case FLIGHT_LOG_RECORD_DECODER_PROFILE_DESCRIPTOR: return SslogRecords_DecoderProfileDescriptorDeserialize(
            &record->payload.decoder_profile_descriptor, buffer, payload_size);
        default: return 0U;
    }
}

uint16_t SslogRecords_PayloadDeserialize(FlightLogRecord *record,
    const uint8_t *buffer, uint16_t buffer_size)
{
    const SslogRecordMetadata *metadata;

    if ((record == NULL) || (buffer == NULL))
    {
        return 0U;
    }
    metadata = SslogRecords_MetadataGet(record->record_type);
    if ((metadata == NULL) || (buffer_size < metadata->payload_size))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT(metadata->payload_size != 0U,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    SILVERSTAR_ASSERT(metadata->payload_size <= buffer_size,
                      SILVERSTAR_ASSERT_MODULE_PROTOCOL,
                      SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    (void)memset(&record->payload, 0, sizeof(record->payload));
    if ((uint32_t)record->record_type <=
        (uint32_t)FLIGHT_LOG_RECORD_INITIAL_STATE)
    {
        return SslogRecords_PayloadDeserializeLow(
            record, buffer, metadata->payload_size);
    }
    return SslogRecords_PayloadDeserializeHigh(
        record, buffer, metadata->payload_size);
}
