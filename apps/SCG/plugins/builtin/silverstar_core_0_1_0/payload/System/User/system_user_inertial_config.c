#include "system_user_inertial_config.h"

static const SystemUserInertialConfig s_config =
{
    .primary_source =
    {
        .source_id = SYSTEM_USER_INERTIAL_PRIMARY_SOURCE_ID,
        .name = "primary_imu",
        .timestamp_quality = SYSTEM_INERTIAL_TIMESTAMP_SOFTWARE_ESTIMATED,
        .sensor_to_body =
        {
            { 1.0f, 0.0f, 0.0f },
            { 0.0f, 1.0f, 0.0f },
            { 0.0f, 0.0f, 1.0f }
        }
    },
    .source_correction =
    {
        .mode = SYSTEM_INERTIAL_CORRECTION_NONE,
        .accel_matrix =
        {
            { 1.0f, 0.0f, 0.0f },
            { 0.0f, 1.0f, 0.0f },
            { 0.0f, 0.0f, 1.0f }
        },
        .gyro_matrix =
        {
            { 1.0f, 0.0f, 0.0f },
            { 0.0f, 1.0f, 0.0f },
            { 0.0f, 0.0f, 1.0f }
        }
    },
    .time_sync =
    {
        .policy = SYSTEM_INERTIAL_SYNC_PASSTHROUGH,
        .master_source = SYSTEM_USER_INERTIAL_PRIMARY_SOURCE_ID,
        .max_skew_us = 0U,
        .stale_us = 0U
    },
    .source_fifo_depth = SYSTEM_USER_INERTIAL_SOURCE_FIFO_DEPTH
};

const SystemUserInertialConfig *SystemUserInertial_ConfigGet(void)
{
    return &s_config;
}
