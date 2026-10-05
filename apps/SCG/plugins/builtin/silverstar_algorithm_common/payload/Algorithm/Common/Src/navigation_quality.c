#include "navigation_quality.h"
#include "silverstar_assert.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#define NAV_QUALITY_RECOMMENDED_SATELLITES 6U
#define NAV_QUALITY_SATELLITE_STEP 0.5f
#define NAV_QUALITY_MAX_SATELLITE_SCALE 4.0f

float NavigationQuality_SatelliteVarianceScale(uint8_t satellites, uint8_t count_valid)
{
    float deficit;
    if ((count_valid == 0U) || (satellites >= NAV_QUALITY_RECOMMENDED_SATELLITES))
    { return 1.0f; }
    deficit = (float)(NAV_QUALITY_RECOMMENDED_SATELLITES - satellites);
    return fminf(NAV_QUALITY_MAX_SATELLITE_SCALE,
                 1.0f + NAV_QUALITY_SATELLITE_STEP * deficit * deficit);
}

NavigationQualityResult NavigationWindow_Reset(NavigationWindowContext *context)
{
    if (context == NULL) { return NAV_QUALITY_INVALID; }
    memset(context, 0, sizeof(*context));
    context->variance_scale = 1.0f;
    return NAV_QUALITY_OK;
}

static uint8_t Window_ConfigValid(const NavigationWindowConfig *config)
{
    return (uint8_t)((config != NULL) && (config->length_us > 0U) &&
        (config->offset_us > 0U) && (config->offset_us < config->length_us) &&
        (config->maximum_gap_us > 0U) && (config->maximum_gap_us < config->offset_us) &&
        (config->ttl_us >= config->offset_us) && isfinite(config->error_threshold_m) &&
        (config->error_threshold_m > 0.0f) && isfinite(config->maximum_variance_scale) &&
        (config->maximum_variance_scale >= 1.0f) && (config->maximum_variance_scale <= 4.0f));
}

NavigationQualityResult NavigationWindow_ConfigValidate(const NavigationWindowConfig *config)
{
    return Window_ConfigValid(config) ? NAV_QUALITY_OK : NAV_QUALITY_INVALID;
}

static uint8_t Window_VectorValid(const float value[2])
{
    return (uint8_t)(isfinite(value[0]) && isfinite(value[1]));
}

static void Window_Anchor(NavigationWindowContext *context,
    const NavigationWindowConfig *config, const NavigationWindowSample *sample)
{
    uint32_t index;
    memset(context->window, 0, sizeof(context->window));
    context->previous = *sample;
    context->previous_valid = sample->velocity_valid;
    for (index = 0U; index < NAV_QUALITY_WINDOW_COUNT; index++)
    {
        context->window[index].start_us = sample->epoch_us + (uint64_t)index * config->offset_us;
    }
    context->window[0].started = 1U;
    context->window[0].start_position_valid = sample->position_valid;
    memcpy(context->window[0].position_en, sample->position_en, sizeof(sample->position_en));
}

static uint8_t Window_PositionAt(const NavigationWindowSample *previous,
    const NavigationWindowSample *sample, uint64_t timestamp_us, float position[2])
{
    uint32_t axis;
    float fraction;
    if (timestamp_us == sample->epoch_us)
    { memcpy(position, sample->position_en, sizeof(sample->position_en)); return sample->position_valid; }
    if (timestamp_us == previous->epoch_us)
    { memcpy(position, previous->position_en, sizeof(previous->position_en)); return previous->position_valid; }
    if ((previous->position_valid == 0U) || (sample->position_valid == 0U)) { return 0U; }
    fraction = (float)(timestamp_us - previous->epoch_us) / (float)(sample->epoch_us - previous->epoch_us);
    for (axis = 0U; axis < 2U; axis++)
    { position[axis] = previous->position_en[axis] + fraction * (sample->position_en[axis] - previous->position_en[axis]); }
    return 1U;
}

static void Window_Integrate(NavigationWindowState *window,
    const NavigationWindowSample *previous, const NavigationWindowSample *sample,
    uint64_t start_us, uint64_t end_us)
{
    float span = (float)(sample->epoch_us - previous->epoch_us);
    float left = (float)(start_us - previous->epoch_us) / span;
    float right = (float)(end_us - previous->epoch_us) / span;
    float dt_s = (float)(end_us - start_us) * 1.0e-6f;
    uint32_t axis;
    for (axis = 0U; axis < 2U; axis++)
    {
        float change = sample->velocity_en[axis] - previous->velocity_en[axis];
        window->integral_en[axis] += (previous->velocity_en[axis] + 0.5f * (left + right) * change) * dt_s;
    }
    window->covered_velocity_epochs++;
    if (sample->position_valid != 0U) { window->covered_position_epochs++; }
}

static void Window_Complete(NavigationWindowContext *context,
    NavigationWindowState *window, const NavigationWindowConfig *config,
    const NavigationWindowSample *sample, uint64_t end_us)
{
    float position[2] = {0.0f, 0.0f};
    uint8_t valid = Window_PositionAt(&context->previous, sample, end_us, position);
    uint32_t axis;
    SILVERSTAR_ASSERT_OBJECT(context, NavigationWindowContext, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(window, NavigationWindowState, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if ((valid != 0U) && (window->start_position_valid != 0U))
    {
        for (axis = 0U; axis < 2U; axis++)
        { context->closure_en[axis] = position[axis] - window->position_en[axis] - window->integral_en[axis]; }
        context->closure_norm_m = hypotf(context->closure_en[0], context->closure_en[1]);
        context->variance_scale = fminf(config->maximum_variance_scale,
            fmaxf(1.0f, context->closure_norm_m * context->closure_norm_m /
                         (config->error_threshold_m * config->error_threshold_m)));
        context->completed_us = end_us;
        context->completed_start_us = window->start_us;
        context->completed_covered_us = (uint32_t)(end_us - window->start_us);
        context->completed_position_epochs = window->covered_position_epochs;
        context->completed_velocity_epochs = window->covered_velocity_epochs;
        context->completed_window_index = (uint8_t)(window - context->window);
        context->evidence_valid = 1U;
        context->completed_count++;
    }
    else { context->unavailable_count++; }
    memset(window, 0, sizeof(*window));
    window->start_us = end_us;
    window->started = 1U;
    window->start_position_valid = valid;
    memcpy(window->position_en, position, sizeof(position));
}

static void Window_Advance(NavigationWindowContext *context, uint32_t index,
    const NavigationWindowConfig *config, const NavigationWindowSample *sample)
{
    NavigationWindowState *window = &context->window[index];
    uint64_t left = context->previous.epoch_us;
    uint64_t end_us = window->start_us + config->length_us;
    SILVERSTAR_ASSERT_OBJECT(context, NavigationWindowContext, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT(index < NAV_QUALITY_WINDOW_COUNT, SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if (sample->epoch_us < window->start_us) { return; }
    if (window->started == 0U)
    {
        window->start_position_valid = Window_PositionAt(&context->previous, sample,
            window->start_us, window->position_en);
        window->started = 1U;
        left = window->start_us;
    }
    if (sample->epoch_us < end_us)
    { Window_Integrate(window, &context->previous, sample, left, sample->epoch_us); }
    else
    {
        Window_Integrate(window, &context->previous, sample, left, end_us);
        Window_Complete(context, window, config, sample, end_us);
        if (sample->epoch_us > end_us)
        { Window_Integrate(window, &context->previous, sample, end_us, sample->epoch_us); }
    }
}

NavigationQualityResult NavigationWindow_Receive(NavigationWindowContext *context,
    const NavigationWindowConfig *config, const NavigationWindowSample *sample)
{
    NavigationWindowSample checked;
    uint32_t index;
    if ((context == NULL) || (sample == NULL) || (Window_ConfigValid(config) == 0U))
    { return NAV_QUALITY_INVALID; }
    SILVERSTAR_ASSERT_OBJECT(context, NavigationWindowContext, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(sample, NavigationWindowSample, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    checked = *sample;
    checked.position_valid = (uint8_t)(checked.position_valid && Window_VectorValid(checked.position_en));
    checked.velocity_valid = (uint8_t)(checked.velocity_valid && Window_VectorValid(checked.velocity_en));
    if ((context->previous_valid != 0U) && (sample->source == context->previous.source) &&
        (sample->generation == context->previous.generation) &&
        ((sample->epoch_us <= context->previous.epoch_us) || (sample->sequence == context->previous.sequence)))
    { return NAV_QUALITY_DUPLICATE; }
    if (context->previous_valid == 0U)
    { Window_Anchor(context, config, &checked); return NAV_QUALITY_OK; }
    if ((checked.velocity_valid == 0U) || (sample->source != context->previous.source) ||
        (sample->generation != context->previous.generation) ||
        (sample->epoch_us <= context->previous.epoch_us) ||
        (sample->epoch_us - context->previous.epoch_us > config->maximum_gap_us) ||
        (sample->sequence != context->previous.sequence + 1U))
    {
        Window_Anchor(context, config, &checked);
        context->evidence_valid = 0U;
        context->variance_scale = 1.0f;
        return NAV_QUALITY_DISCONTINUITY;
    }
    for (index = 0U; index < NAV_QUALITY_WINDOW_COUNT; index++)
    { Window_Advance(context, index, config, &checked); }
    context->previous = checked;
    return NAV_QUALITY_OK;
}

float NavigationWindow_VarianceScale(const NavigationWindowContext *context,
    const NavigationWindowConfig *config, uint64_t epoch_us)
{
    if ((context == NULL) || (Window_ConfigValid(config) == 0U) ||
        (context->evidence_valid == 0U) || (epoch_us < context->completed_us) ||
        (epoch_us - context->completed_us > config->ttl_us)) { return 1.0f; }
    return context->variance_scale;
}
