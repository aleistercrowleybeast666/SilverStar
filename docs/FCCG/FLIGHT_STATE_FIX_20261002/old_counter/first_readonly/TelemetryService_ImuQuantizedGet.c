static uint8_t TelemetryService_ImuQuantizedGet(
    AirCompactV0ImuQuantized *quantized)
{
    SystemCalibrationImuCorrection correction;
    SystemInertialSample sample;
    float corrected_accel_b_mps2[3];
    float corrected_gyro_b_radps[3];
    uint8_t index;

    if ((quantized == NULL) ||
        (SystemInertial_LatestGet(&sample) != SYSTEM_DEVICE_OK) ||
        ((sample.valid_mask & (SYSTEM_INERTIAL_VALID_ACCEL |
                               SYSTEM_INERTIAL_VALID_GYRO)) !=
         (SYSTEM_INERTIAL_VALID_ACCEL | SYSTEM_INERTIAL_VALID_GYRO)))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(quantized, AirCompactV0ImuQuantized,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if (SystemCalibration_ImuCorrectionGet(&correction) != SYSTEM_DEVICE_OK)
    {
        (void)memset(&correction, 0, sizeof(correction));
        correction.mode = SYSTEM_CALIBRATION_MODE_NOT_SELECTED;
        for (index = 0U; index < 3U; index++)
        {
            correction.accel_scale[index] = 1.0f;
            correction.gyro_scale[index] = 1.0f;
        }
    }
    if ((SystemCalibration_ImuCorrectionApply(
            sample.accel_b_mps2, sample.gyro_b_radps,
            &correction, corrected_accel_b_mps2,
            corrected_gyro_b_radps) != SYSTEM_DEVICE_OK) ||
        (Air_CompactV0ImuQuantize(corrected_accel_b_mps2,
            corrected_gyro_b_radps, quantized) != AIR_BUILD_OK))
    {
        return 0U;
    }
    s_diagnostics.quantization_saturation_count +=
        quantized->saturation_count;
    return 1U;
}
