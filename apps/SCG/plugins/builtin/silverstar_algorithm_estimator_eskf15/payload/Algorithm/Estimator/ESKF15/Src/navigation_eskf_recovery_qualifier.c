#include "navigation_eskf_recovery_qualifier.h"
#include "navigation_eskf_recovery.h"
#include <math.h>
#include <stddef.h>
#include <string.h>

#define QUALIFIER_WEEK_MS 604800000U
#define QUALIFIER_WEEK_US 604800000000ULL

typedef struct
{
    const void *address;
    size_t size;
    uint8_t writable;
} QualifierRegion;

static uint8_t Qualifier_RegionsValid(const QualifierRegion region[5])
{
    for (uint8_t i = 0U; i < 5U; i++)
    {
        if (region[i].address == NULL) { return 0U; }
        for (uint8_t j = 0U; j < i; j++)
        {
            uintptr_t a = (uintptr_t)region[i].address, b = (uintptr_t)region[j].address;
            uint8_t overlap = (uint8_t)((a <= b) ?
                (b - a < region[i].size) : (a - b < region[j].size));
            if (overlap && (region[i].writable || region[j].writable)) { return 0U; }
        }
    }
    return 1U;
}

NavigationEskfRecoveryQualifierResult NavigationEskfRecoveryQualifier_ConfigValidate(
    const NavigationEskfRecoveryQualifierConfig *config)
{
    if ((config == NULL) || (config->maximum_interval_us == 0U) ||
        (config->maximum_interval_us > 500000ULL) ||
        (config->clock_jitter_us > config->maximum_interval_us) ||
        !isfinite(config->horizontal_acceleration_limit_mps2) ||
        (config->horizontal_acceleration_limit_mps2 <= 0.0f) ||
        !isfinite(config->vertical_acceleration_limit_mps2) ||
        (config->vertical_acceleration_limit_mps2 <= 0.0f) ||
        !isfinite(config->closure_sigma) || (config->closure_sigma <= 0.0f))
    { return NAV_ESKF_QUALIFIER_INVALID_ARGUMENT; }
    return NAV_ESKF_QUALIFIER_COMPLETE;
}

NavigationEskfRecoveryQualifierResult NavigationEskfRecoveryQualifier_Reset(
    NavigationEskfRecoveryQualifier *qualifier)
{
    if (qualifier == NULL) { return NAV_ESKF_QUALIFIER_INVALID_ARGUMENT; }
    memset(qualifier, 0, sizeof(*qualifier));
    return NAV_ESKF_QUALIFIER_COMPLETE;
}

static uint8_t Qualifier_StateValid(const NavigationEskfRecoveryQualifier *qualifier)
{
    uint64_t tow;
    if ((qualifier->initialized > 1U) || (qualifier->physical_mask > 15U) ||
        (qualifier->eligible_mask > 15U) ||
        (qualifier->clock_basis > (uint8_t)SYSTEM_GNSS_RECEIPT_CLOCK_NATIVE_ITOW)) { return 0U; }
    if (qualifier->initialized == 0U) { return 1U; }
    if ((qualifier->previous.source >= NAV_ESKF_RECOVERY_SOURCES) ||
        (qualifier->previous.sample.sequence == 0U) ||
        (qualifier->previous.sample.receive_timestamp_us == 0U) ||
        ((uint8_t)SystemGnssReceipt_ClockBasisGet(&qualifier->previous) != qualifier->clock_basis))
    { return 0U; }
    if (qualifier->clock_basis == (uint8_t)SYSTEM_GNSS_RECEIPT_CLOCK_NATIVE_ITOW)
    {
        tow = (uint64_t)qualifier->previous.native.time_of_week_ms * 1000ULL;
        return (uint8_t)(((qualifier->week_us % QUALIFIER_WEEK_US) == 0U) &&
            (qualifier->week_us <= UINT64_MAX - tow) &&
            (qualifier->native_us == qualifier->week_us + tow));
    }
    return (uint8_t)((qualifier->week_us == 0U) && (qualifier->native_us ==
        ((qualifier->clock_basis == (uint8_t)SYSTEM_GNSS_RECEIPT_CLOCK_MCU_SAMPLE) ?
         qualifier->previous.sample.sample_timestamp_us : 0U)));
}

static uint8_t Qualifier_PhysicalMask(const SystemGnssSample *sample, const float position[3])
{
    const uint32_t required[4] = {
        SYSTEM_GNSS_FIELD_POSITION | SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY,
        SYSTEM_GNSS_FIELD_HEIGHT | SYSTEM_GNSS_FIELD_VERTICAL_ACCURACY,
        SYSTEM_GNSS_FIELD_VELOCITY_HORIZONTAL | SYSTEM_GNSS_FIELD_SPEED_ACCURACY,
        SYSTEM_GNSS_FIELD_VELOCITY_VERTICAL | SYSTEM_GNSS_FIELD_SPEED_ACCURACY};
    uint32_t fields = sample->supported_fields & sample->valid_fields;
    uint8_t mask = sample->physical_valid_group_mask;
    if ((mask > 15U) || (sample->online != 1U) || (sample->fix_ok != 1U) ||
        (sample->fix_type < 2U) || (sample->fix_type > 4U) ||
        ((fields & (SYSTEM_GNSS_FIELD_FIX_TYPE | SYSTEM_GNSS_FIELD_FIX_OK)) !=
         (SYSTEM_GNSS_FIELD_FIX_TYPE | SYSTEM_GNSS_FIELD_FIX_OK))) { return 0U; }
    for (uint8_t group = 0U; group < 4U; group++)
    { if ((fields & required[group]) != required[group]) { mask &= (uint8_t)~(1U << group); } }
    if (!isfinite(position[0]) || !isfinite(position[1]) ||
        !isfinite(sample->horizontal_accuracy_m) || (sample->horizontal_accuracy_m <= 0.0f))
    { mask &= (uint8_t)~1U; }
    if (!isfinite(position[2]) || !isfinite(sample->vertical_accuracy_m) ||
        (sample->vertical_accuracy_m <= 0.0f) || (sample->fix_type < 3U)) { mask &= (uint8_t)~2U; }
    if (!isfinite(sample->speed_accuracy_mps) || (sample->speed_accuracy_mps <= 0.0f))
    { mask &= (uint8_t)~12U; }
    if (!isfinite(sample->velocity_enu_mps[0]) || !isfinite(sample->velocity_enu_mps[1]) ||
        ((sample->velocity_valid_mask & 3U) != 3U)) { mask &= (uint8_t)~4U; }
    if (!isfinite(sample->velocity_enu_mps[2]) ||
        ((sample->velocity_valid_mask & 4U) == 0U) || (sample->fix_type < 3U)) { mask &= (uint8_t)~8U; }
    return mask;
}

static NavigationEskfRecoveryQualifierResult Qualifier_NativeGet(
    const NavigationEskfRecoveryQualifier *qualifier, const SystemGnssReceiptSnapshot *receipt,
    NavigationEskfRecoveryQualifierOutput *output, uint64_t *week_us)
{
    *week_us = 0U;
    output->clock_basis = (uint8_t)SystemGnssReceipt_ClockBasisGet(receipt);
    output->time_proven = (uint8_t)(output->clock_basis != (uint8_t)SYSTEM_GNSS_RECEIPT_CLOCK_UNPROVEN);
    if (output->clock_basis == (uint8_t)SYSTEM_GNSS_RECEIPT_CLOCK_MCU_SAMPLE)
    { output->native_us = receipt->sample.sample_timestamp_us; return NAV_ESKF_QUALIFIER_COMPLETE; }
    if (output->clock_basis != (uint8_t)SYSTEM_GNSS_RECEIPT_CLOCK_NATIVE_ITOW)
    { output->reasons |= NAV_ESKF_QUALIFIER_REASON_CLOCK; return NAV_ESKF_QUALIFIER_COMPLETE; }
    if (qualifier->initialized && (receipt->source == qualifier->previous.source) &&
        (qualifier->clock_basis == output->clock_basis))
    {
        uint32_t before = qualifier->previous.native.time_of_week_ms;
        uint32_t now = receipt->native.time_of_week_ms;
        *week_us = qualifier->week_us;
        if ((now < before) && (before - now > QUALIFIER_WEEK_MS / 2U))
        {
            if (*week_us > UINT64_MAX - QUALIFIER_WEEK_US) { return NAV_ESKF_QUALIFIER_BAD_STATE; }
            *week_us += QUALIFIER_WEEK_US;
        }
        else if (now < before) { *week_us = 0U; }
    }
    uint64_t tow = (uint64_t)receipt->native.time_of_week_ms * 1000ULL;
    if (*week_us > UINT64_MAX - tow) { return NAV_ESKF_QUALIFIER_BAD_STATE; }
    output->native_us = *week_us + tow;
    return NAV_ESKF_QUALIFIER_COMPLETE;
}

static uint8_t Qualifier_PairTimeValid(const NavigationEskfRecoveryQualifier *qualifier,
    const NavigationEskfRecoveryQualifierConfig *config, const SystemGnssReceiptSnapshot *receipt,
    NavigationEskfRecoveryQualifierOutput *output, float *dt_s)
{
    uint64_t native_delta, receive_delta, jitter;
    if (!qualifier->initialized || (receipt->source != qualifier->previous.source) ||
        (output->clock_basis != qualifier->clock_basis))
    { output->reasons |= NAV_ESKF_QUALIFIER_REASON_BASELINE; return 0U; }
    if (!output->time_proven || (output->native_us <= qualifier->native_us))
    { output->reasons |= NAV_ESKF_QUALIFIER_REASON_CLOCK; return 0U; }
    native_delta = output->native_us - qualifier->native_us;
    receive_delta = receipt->sample.receive_timestamp_us - qualifier->previous.sample.receive_timestamp_us;
    if ((native_delta > config->maximum_interval_us) || (receive_delta > config->maximum_interval_us))
    { output->reasons |= NAV_ESKF_QUALIFIER_REASON_INTERVAL; return 0U; }
    jitter = (native_delta > receive_delta) ? native_delta - receive_delta : receive_delta - native_delta;
    if (jitter > config->clock_jitter_us)
    { output->reasons |= NAV_ESKF_QUALIFIER_REASON_JITTER; return 0U; }
    *dt_s = (float)native_delta * 1.0e-6f;
    return 1U;
}

static uint8_t Qualifier_GroupCoherent(const NavigationEskfRecoveryQualifier *qualifier,
    const NavigationEskfRecoveryQualifierConfig *config, const SystemGnssSample *sample,
    const float position[3], uint8_t vertical, float dt_s)
{
    const SystemGnssSample *previous = &qualifier->previous.sample;
    uint8_t first = vertical ? 2U : 0U, count = vertical ? 1U : 2U;
    float limit = vertical ? config->vertical_acceleration_limit_mps2 : config->horizontal_acceleration_limit_mps2;
    float speed_variance = previous->speed_accuracy_mps * previous->speed_accuracy_mps +
        sample->speed_accuracy_mps * sample->speed_accuracy_mps;
    float speed_bound = limit * dt_s + config->closure_sigma * sqrtf(speed_variance);
    float velocity2 = 0.0f, closure2 = 0.0f;
    for (uint8_t axis = 0U; axis < 2U; axis++)
    {
        if (axis >= count) { break; }
        uint8_t index = (uint8_t)(first + axis);
        float dv = sample->velocity_enu_mps[index] - previous->velocity_enu_mps[index];
        float closure = position[index] - qualifier->position_enu_m[index] -
            0.5f * (sample->velocity_enu_mps[index] + previous->velocity_enu_mps[index]) * dt_s;
        velocity2 += dv * dv; closure2 += closure * closure;
    }
    if (!isfinite(speed_bound) || !isfinite(velocity2) || (sqrtf(velocity2) > speed_bound)) { return 0U; }
    float before = vertical ? previous->vertical_accuracy_m : previous->horizontal_accuracy_m;
    float now = vertical ? sample->vertical_accuracy_m : sample->horizontal_accuracy_m;
    float closure_bound = config->closure_sigma * sqrtf(before * before + now * now +
        0.25f * dt_s * dt_s * speed_variance) + 0.5f * limit * dt_s * dt_s;
    uint8_t result = 1U;
    if (isfinite(closure_bound) && isfinite(closure2) && (sqrtf(closure2) <= closure_bound)) { result |= 2U; }
    return result;
}

static void Qualifier_Capture(NavigationEskfRecoveryQualifier *qualifier,
    const SystemGnssReceiptSnapshot *receipt, const float position[3],
    const NavigationEskfRecoveryQualifierOutput *output, uint64_t week_us)
{
    qualifier->previous = *receipt;
    memcpy(qualifier->position_enu_m, position, sizeof(qualifier->position_enu_m));
    qualifier->physical_mask = output->physical_mask;
    qualifier->eligible_mask = output->physical_mask & receipt->sample.valid_group_mask & 15U;
    qualifier->clock_basis = output->clock_basis; qualifier->native_us = output->native_us;
    qualifier->week_us = week_us; qualifier->initialized = 1U;
}

NavigationEskfRecoveryQualifierResult NavigationEskfRecoveryQualifier_Receive(
    NavigationEskfRecoveryQualifier *qualifier, const NavigationEskfRecoveryQualifierConfig *config,
    const SystemGnssReceiptSnapshot *receipt, const float position_enu_m[3],
    uint64_t present_us, NavigationEskfRecoveryQualifierOutput *output)
{
    const QualifierRegion region[5] = {{qualifier, sizeof(*qualifier), 1U},
        {config, sizeof(*config), 0U}, {receipt, sizeof(*receipt), 0U},
        {position_enu_m, 3U * sizeof(float), 0U}, {output, sizeof(*output), 1U}};
    NavigationEskfRecoveryQualifierOutput candidate = {0};
    NavigationEskfRecoveryQualifierResult result;
    uint64_t week_us; float dt_s = 0.0f;
    if (!Qualifier_RegionsValid(region) ||
        (NavigationEskfRecoveryQualifier_ConfigValidate(config) != NAV_ESKF_QUALIFIER_COMPLETE))
    { return NAV_ESKF_QUALIFIER_INVALID_ARGUMENT; }
    if (!Qualifier_StateValid(qualifier)) { return NAV_ESKF_QUALIFIER_BAD_STATE; }
    if ((receipt->source >= NAV_ESKF_RECOVERY_SOURCES) || (receipt->sample.sequence == 0U) ||
        (receipt->sample.receive_timestamp_us == 0U) || (receipt->sample.receive_timestamp_us > present_us) ||
        (present_us - receipt->sample.receive_timestamp_us > 500000ULL))
    { candidate.reasons = NAV_ESKF_QUALIFIER_REASON_STALE; *output = candidate; return NAV_ESKF_QUALIFIER_INELIGIBLE; }
    if (qualifier->initialized && (receipt->source == qualifier->previous.source))
    {
        uint32_t delta = receipt->sample.sequence - qualifier->previous.sample.sequence;
        if (delta == 0U) { return NAV_ESKF_QUALIFIER_DUPLICATE; }
        if ((delta >= UINT32_C(0x80000000)) ||
            (receipt->sample.receive_timestamp_us <= qualifier->previous.sample.receive_timestamp_us))
        { return NAV_ESKF_QUALIFIER_DISCONTINUITY; }
    }
    candidate.physical_mask = Qualifier_PhysicalMask(&receipt->sample, position_enu_m);
    result = Qualifier_NativeGet(qualifier, receipt, &candidate, &week_us);
    if (result != NAV_ESKF_QUALIFIER_COMPLETE) { return result; }
    if (Qualifier_PairTimeValid(qualifier, config, receipt, &candidate, &dt_s))
    {
        uint8_t eligible = candidate.physical_mask & receipt->sample.valid_group_mask & qualifier->eligible_mask;
        for (uint8_t vertical = 0U; vertical < 2U; vertical++)
        {
            uint8_t velocity_bit = (uint8_t)(4U << vertical), position_bit = (uint8_t)(1U << vertical);
            if ((eligible & velocity_bit) == 0U) { continue; }
            uint8_t coherent = Qualifier_GroupCoherent(qualifier, config, &receipt->sample, position_enu_m, vertical, dt_s);
            if ((coherent & 1U) != 0U) { candidate.coherent_mask |= velocity_bit; }
            if (((eligible & position_bit) != 0U) && ((coherent & 2U) != 0U)) { candidate.coherent_mask |= position_bit; }
        }
    }
    if ((candidate.physical_mask != 15U) || ((receipt->sample.valid_group_mask & 15U) != 15U))
    { candidate.reasons |= NAV_ESKF_QUALIFIER_REASON_PHYSICAL; }
    if ((candidate.coherent_mask != 15U) && (candidate.reasons == 0U))
    { candidate.reasons |= NAV_ESKF_QUALIFIER_REASON_COHERENCE; }
    Qualifier_Capture(qualifier, receipt, position_enu_m, &candidate, week_us); *output = candidate;
    if (candidate.time_proven == 0U) { return NAV_ESKF_QUALIFIER_INELIGIBLE; }
    if ((candidate.reasons & NAV_ESKF_QUALIFIER_REASON_BASELINE) != 0U) { return NAV_ESKF_QUALIFIER_BASELINE; }
    return candidate.coherent_mask ? NAV_ESKF_QUALIFIER_COMPLETE : NAV_ESKF_QUALIFIER_INELIGIBLE;
}
