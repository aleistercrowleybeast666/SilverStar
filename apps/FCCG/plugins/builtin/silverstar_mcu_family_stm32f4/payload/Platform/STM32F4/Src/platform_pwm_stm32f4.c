#include "platform_pwm.h"

#include <stddef.h>

#include "platform_stm32f4_resources.h"
#include "silverstar_assert.h"
#include "stm32f4xx_hal.h"

typedef struct
{
    TIM_HandleTypeDef *handle;
    uint32_t channel;
    uint32_t frequency_hz;
    uint16_t resolution_bits;
    uint16_t duty_permille;
    PlatformPwmMode mode;
    uint8_t active_high;
    uint8_t started;
    uint8_t loaded;
} PlatformPwmContext;

static PlatformPwmContext s_pwm[PLATFORM_PWM_COUNT];

static uint8_t PlatformPwm_ContextLoad(
    PlatformPwmId id, PlatformPwmContext *context)
{
    PlatformStm32f4PwmResource resource;

    if (PlatformStm32f4Resource_PwmGet(id, &resource) == 0U)
    {
        return 0U;
    }
    context->handle = (TIM_HandleTypeDef *)resource.handle;
    context->channel = resource.channel;
    context->frequency_hz = resource.frequency_hz;
    context->resolution_bits = resource.resolution_bits;
    context->mode = resource.mode;
    context->active_high = resource.active_high;
    context->loaded = 1U;
    return (context->handle != NULL) ? 1U : 0U;
}

static PlatformPwmContext *PlatformPwm_ContextGet(PlatformPwmId id)
{
    PlatformPwmContext *context;

    if ((uint32_t)id >= (uint32_t)PLATFORM_PWM_COUNT) { return NULL; }
    context = &s_pwm[id];
    if ((context->loaded == 0U) &&
        (PlatformPwm_ContextLoad(id, context) == 0U)) { return NULL; }
    return (context->handle != NULL) ? context : NULL;
}

static PlatformResult PlatformPwm_ResultMap(HAL_StatusTypeDef result)
{
    if (result == HAL_OK) { return PLATFORM_OK; }
    if (result == HAL_TIMEOUT) { return PLATFORM_TIMEOUT; }
    if (result == HAL_BUSY) { return PLATFORM_BUSY; }
    return PLATFORM_IO_ERROR;
}

static PlatformResult PlatformPwm_OutputModeSet(
    PlatformPwmContext *context, uint32_t mode)
{
    if ((context == NULL) || (context->handle == NULL) ||
        (context->handle->Instance == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(context, PlatformPwmContext,
                             SILVERSTAR_ASSERT_MODULE_PLATFORM);
    SILVERSTAR_ASSERT_OBJECT(context->handle, TIM_HandleTypeDef,
                             SILVERSTAR_ASSERT_MODULE_PLATFORM);
    switch (context->channel)
    {
        case TIM_CHANNEL_1:
            MODIFY_REG(context->handle->Instance->CCMR1,
                       TIM_CCMR1_OC1M, mode);
            break;
        case TIM_CHANNEL_2:
            MODIFY_REG(context->handle->Instance->CCMR1,
                       TIM_CCMR1_OC2M, mode << 8U);
            break;
        case TIM_CHANNEL_3:
            MODIFY_REG(context->handle->Instance->CCMR2,
                       TIM_CCMR2_OC3M, mode);
            break;
        case TIM_CHANNEL_4:
            MODIFY_REG(context->handle->Instance->CCMR2,
                       TIM_CCMR2_OC4M, mode << 8U);
            break;
        default:
            return PLATFORM_UNSUPPORTED;
    }
    return PLATFORM_OK;
}

static PlatformResult PlatformPwm_IntermediateGet(
    const PlatformPwmContext *context,
    uint64_t period_counts,
    uint64_t active_counts,
    uint32_t *configured_mode,
    uint32_t *compare)
{
    if ((context == NULL) || (configured_mode == NULL) || (compare == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(context, PlatformPwmContext,
                             SILVERSTAR_ASSERT_MODULE_PLATFORM);
    if (context->mode == PLATFORM_PWM_MODE_1)
    {
        *configured_mode = TIM_OCMODE_PWM1;
        *compare = (uint32_t)active_counts;
    }
    else if (context->mode == PLATFORM_PWM_MODE_2)
    {
        *configured_mode = TIM_OCMODE_PWM2;
        *compare = (uint32_t)(period_counts - active_counts);
    }
    else
    {
        return PLATFORM_UNSUPPORTED;
    }
    return PLATFORM_OK;
}

static PlatformResult PlatformPwm_DutyApply(
    PlatformPwmContext *context, uint16_t duty_permille)
{
    uint64_t period_counts;
    uint64_t active_counts;
    uint32_t compare;
    uint32_t configured_mode;
    PlatformResult result;

    if ((context == NULL) || (context->handle == NULL) ||
        (duty_permille > PLATFORM_PWM_DUTY_PERMILLE_MAX))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(context, PlatformPwmContext,
                             SILVERSTAR_ASSERT_MODULE_PLATFORM);
    SILVERSTAR_ASSERT_OBJECT(context->handle, TIM_HandleTypeDef,
                             SILVERSTAR_ASSERT_MODULE_PLATFORM);
    period_counts = (uint64_t)context->handle->Init.Period + 1ULL;
    if (duty_permille == 0U)
    {
        result = PlatformPwm_OutputModeSet(
            context, TIM_OCMODE_FORCED_INACTIVE);
        if (result != PLATFORM_OK) { return result; }
        __HAL_TIM_SET_COMPARE(context->handle, context->channel, 0U);
    }
    else if (duty_permille == PLATFORM_PWM_DUTY_PERMILLE_MAX)
    {
        result = PlatformPwm_OutputModeSet(
            context, TIM_OCMODE_FORCED_ACTIVE);
        if (result != PLATFORM_OK) { return result; }
        __HAL_TIM_SET_COMPARE(
            context->handle, context->channel, context->handle->Init.Period);
    }
    else
    {
        active_counts = (period_counts * duty_permille) /
                        PLATFORM_PWM_DUTY_PERMILLE_MAX;
        if ((active_counts == 0ULL) || (active_counts >= period_counts))
        {
            return PLATFORM_UNSUPPORTED;
        }
        result = PlatformPwm_IntermediateGet(
            context, period_counts, active_counts, &configured_mode, &compare);
        if (result != PLATFORM_OK) { return result; }
        result = PlatformPwm_OutputModeSet(context, configured_mode);
        if (result != PLATFORM_OK) { return result; }
        __HAL_TIM_SET_COMPARE(context->handle, context->channel, compare);
    }
    context->duty_permille = duty_permille;
    return PLATFORM_OK;
}

PlatformResult PlatformPwm_Start(PlatformPwmId id)
{
    PlatformPwmContext *context = PlatformPwm_ContextGet(id);
    HAL_StatusTypeDef result;
    PlatformResult apply_result;

    if (context == NULL) { return PLATFORM_INVALID_ARGUMENT; }
    apply_result = PlatformPwm_DutyApply(context, context->duty_permille);
    if (apply_result != PLATFORM_OK) { return apply_result; }
    result = HAL_TIM_PWM_Start(context->handle, context->channel);
    if (result == HAL_OK) { context->started = 1U; }
    return PlatformPwm_ResultMap(result);
}

PlatformResult PlatformPwm_Stop(PlatformPwmId id)
{
    PlatformPwmContext *context = PlatformPwm_ContextGet(id);
    HAL_StatusTypeDef result;

    if (context == NULL) { return PLATFORM_INVALID_ARGUMENT; }
    if (PlatformPwm_DutyApply(context, 0U) != PLATFORM_OK)
    {
        return PLATFORM_UNSUPPORTED;
    }
    result = HAL_TIM_PWM_Stop(context->handle, context->channel);
    if (result == HAL_OK) { context->started = 0U; }
    return PlatformPwm_ResultMap(result);
}

PlatformResult PlatformPwm_DutyPermilleSet(
    PlatformPwmId id,
    uint16_t duty_permille)
{
    PlatformPwmContext *context = PlatformPwm_ContextGet(id);
    if ((context == NULL) ||
        (duty_permille > PLATFORM_PWM_DUTY_PERMILLE_MAX))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    return PlatformPwm_DutyApply(context, duty_permille);
}

PlatformResult PlatformPwm_SafeInactiveSet(PlatformPwmId id)
{
    PlatformPwmContext *context = PlatformPwm_ContextGet(id);

    if (context == NULL) { return PLATFORM_INVALID_ARGUMENT; }
    return PlatformPwm_Stop(id);
}

PlatformResult PlatformPwm_DiagnosticsGet(
    PlatformPwmId id,
    PlatformPwmDiagnostics *diagnostics)
{
    PlatformPwmContext *context = PlatformPwm_ContextGet(id);

    if ((context == NULL) || (diagnostics == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    diagnostics->frequency_hz = context->frequency_hz;
    diagnostics->resolution_bits = context->resolution_bits;
    diagnostics->active_high = context->active_high;
    diagnostics->started = context->started;
    diagnostics->duty_permille = context->duty_permille;
    return PLATFORM_OK;
}
