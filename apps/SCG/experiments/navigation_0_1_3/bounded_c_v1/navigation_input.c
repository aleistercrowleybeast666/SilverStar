#include "navigation_input.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

static uint8_t Input_IdentityEqual(const NavigationInputIdentity *a,
    const NavigationInputIdentity *b)
{
    return (uint8_t)((a->epoch == b->epoch) && (a->source == b->source) &&
        (a->calibration == b->calibration));
}

NavigationInputResult NavigationInput_Initialize(NavigationInputLedger *ledger,
    const NavigationInputIdentity *identity)
{
    NavigationInputLedger candidate;
    if ((ledger == NULL) || (identity == NULL))
    { return NavigationInputResult_InvalidInput; }
    (void)memset(&candidate, 0, sizeof(candidate));
    candidate.identity = *identity;
    *ledger = candidate;
    return NavigationInputResult_Ok;
}

NavigationInputResult NavigationInput_Check(const NavigationInputLedger *ledger,
    const NavigationInputEvent *event, uint64_t state_us)
{
    uint32_t difference;
    if ((ledger == NULL) || (event == NULL) || (ledger->seen > 1U) ||
        (event->timestamp_trusted > 1U))
    { return NavigationInputResult_InvalidInput; }
    if (Input_IdentityEqual(&ledger->identity, &event->identity) == 0U)
    { return NavigationInputResult_IdentityMismatch; }
    if (event->timestamp_trusted == 0U)
    { return NavigationInputResult_UntrustedTime; }
    if ((event->sample_us > event->receive_us) ||
        ((ledger->seen != 0U) && (ledger->last_sample_us > state_us)))
    { return NavigationInputResult_InvalidInput; }
    if (event->sample_us > state_us)
    { return NavigationInputResult_Future; }
    if (event->sample_us < state_us)
    { return NavigationInputResult_DelayedUnsupported; }
    if (ledger->seen != 0U)
    {
        difference = event->sequence - ledger->last_sequence;
        if (difference == 0U) { return NavigationInputResult_Duplicate; }
        if ((difference >= 0x80000000UL) ||
            (event->sample_us <= ledger->last_sample_us))
        { return NavigationInputResult_OutOfOrder; }
    }
    return NavigationInputResult_Ok;
}

NavigationInputResult NavigationInput_Consume(NavigationInputLedger *ledger,
    const NavigationInputEvent *event, uint64_t state_us)
{
    NavigationInputResult result = NavigationInput_Check(ledger, event, state_us);
    if (result != NavigationInputResult_Ok) { return result; }
    ledger->last_sample_us = event->sample_us;
    ledger->last_sequence = event->sequence;
    ledger->seen = 1U;
    return NavigationInputResult_Ok;
}

NavigationInputResult NavigationInput_Interval(uint64_t previous_us,
    uint64_t start_us, uint64_t end_us, float *dt_s)
{
    uint64_t delta;
    if ((dt_s == NULL) || (start_us != previous_us) || (end_us <= start_us))
    { return NavigationInputResult_InvalidInput; }
    delta = end_us - start_us;
    if (delta > 20000ULL) { return NavigationInputResult_InvalidInput; }
    *dt_s = (float)delta * 1.0e-6f;
    return NavigationInputResult_Ok;
}

static uint8_t Mag_MatrixPositive(const float matrix[9])
{
    float lower[9] = {0.0f};
    for (uint32_t row = 0U; row < 3U; row++)
    {
        for (uint32_t column = 0U; column < 3U; column++)
        {
            float a = matrix[row * 3U + column];
            float b = matrix[column * 3U + row];
            if (!isfinite(a) || !isfinite(b) || (a != b))
            { return 0U; }
        }
        for (uint32_t column = 0U; column <= row; column++)
        {
            float value = matrix[row * 3U + column];
            for (uint32_t k = 0U; k < column; k++)
            { value -= lower[row * 3U + k] * lower[column * 3U + k]; }
            if (!isfinite(value)) { return 0U; }
            if (row == column)
            {
                if (value <= 0.0f) { return 0U; }
                lower[row * 3U + column] = sqrtf(value);
            }
            else
            {
                value /= lower[column * 3U + column];
                if (!isfinite(value)) { return 0U; }
                lower[row * 3U + column] = value;
            }
        }
    }
    return 1U;
}

static uint8_t Mag_CorrectionValid(const NavigationMagCorrection *correction)
{
    if (!isfinite(correction->reference_uT) || (correction->reference_uT <= 0.0f) ||
        !isfinite(correction->minimum_norm_ratio) || !isfinite(correction->maximum_norm_ratio) ||
        (correction->minimum_norm_ratio <= 0.0f) ||
        (correction->maximum_norm_ratio <= correction->minimum_norm_ratio))
    { return 0U; }
    for (uint32_t i = 0U; i < 3U; i++)
    { if (!isfinite(correction->bias_uT[i])) { return 0U; } }
    return Mag_MatrixPositive(correction->soft_iron);
}

static NavigationInputResult Mag_VectorBuild(const float input[3],
    const NavigationMagCorrection *correction, float output[3])
{
    float norm_squared = 0.0f;
    float ratio;
    for (uint32_t row = 0U; row < 3U; row++)
    {
        float value = 0.0f;
        for (uint32_t column = 0U; column < 3U; column++)
        { value += correction->soft_iron[row * 3U + column] *
            (input[column] - correction->bias_uT[column]); }
        if (!isfinite(value)) { return NavigationInputResult_NumericError; }
        output[row] = value;
        norm_squared += value * value;
    }
    if (!isfinite(norm_squared)) { return NavigationInputResult_NumericError; }
    ratio = sqrtf(norm_squared) / correction->reference_uT;
    if (!isfinite(ratio)) { return NavigationInputResult_NumericError; }
    if ((ratio < correction->minimum_norm_ratio) || (ratio > correction->maximum_norm_ratio))
    { return NavigationInputResult_FieldRejected; }
    return NavigationInputResult_Ok;
}

static NavigationInputResult Mag_CovarianceBuild(const float input[9],
    const float soft[9], float output[9])
{
    for (uint32_t row = 0U; row < 3U; row++)
    {
        for (uint32_t column = 0U; column <= row; column++)
        {
            float value = 0.0f;
            for (uint32_t i = 0U; i < 3U; i++)
            {
                for (uint32_t j = 0U; j < 3U; j++)
                { value += soft[row * 3U + i] * input[i * 3U + j] * soft[column * 3U + j]; }
            }
            if (!isfinite(value)) { return NavigationInputResult_NumericError; }
            output[row * 3U + column] = value;
            output[column * 3U + row] = value;
        }
    }
    if (Mag_MatrixPositive(output) == 0U) { return NavigationInputResult_NumericError; }
    return NavigationInputResult_Ok;
}

NavigationInputResult NavigationMag_Prepare(const float sensor_uT[3],
    const float covariance_uT2[9], NavigationMagStage stage,
    const NavigationMagCorrection *correction, NavigationMagPrepared *output)
{
    NavigationMagPrepared candidate;
    NavigationInputResult result;
    if ((sensor_uT == NULL) || (covariance_uT2 == NULL) ||
        (correction == NULL) || (output == NULL))
    { return NavigationInputResult_InvalidInput; }
    if (stage != NavigationMagStage_SensorPhysical)
    { return NavigationInputResult_WrongCorrectionStage; }
    if ((Mag_CorrectionValid(correction) == 0U) || (Mag_MatrixPositive(covariance_uT2) == 0U))
    { return NavigationInputResult_InvalidInput; }
    for (uint32_t i = 0U; i < 3U; i++)
    { if (!isfinite(sensor_uT[i])) { return NavigationInputResult_InvalidInput; } }
    (void)memset(&candidate, 0, sizeof(candidate));
    result = Mag_VectorBuild(sensor_uT, correction, candidate.sensor_uT);
    if (result != NavigationInputResult_Ok) { return result; }
    result = Mag_CovarianceBuild(covariance_uT2, correction->soft_iron, candidate.covariance_uT2);
    if (result != NavigationInputResult_Ok) { return result; }
    candidate.stage = NavigationMagStage_SensorHardSoftCorrected;
    *output = candidate;
    return NavigationInputResult_Ok;
}
