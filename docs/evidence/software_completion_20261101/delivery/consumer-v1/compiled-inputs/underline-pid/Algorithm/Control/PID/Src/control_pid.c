#include "control_pid.h"
#include <math.h>
#include <stddef.h>
#include <string.h>

static uint8_t ControlPid_ConfigValid(const ControlPidConfig *config)
{
    if (config == NULL) { return 0U; }
    return (uint8_t)(isfinite(config->kp) && isfinite(config->ki) &&
        isfinite(config->kd) && isfinite(config->derivative_tau_s) &&
        isfinite(config->integral_limit) && isfinite(config->output_limit) &&
        isfinite(config->sample_period_s) && (config->kp >= 0.0f) &&
        (config->ki >= 0.0f) && (config->kd >= 0.0f) &&
        (config->derivative_tau_s >= 0.0f) && (config->integral_limit >= 0.0f) &&
        (config->output_limit > 0.0f) && (config->sample_period_s > 0.0f));
}

static float ControlPid_Limit(float value, float limit)
{
    return fminf(limit, fmaxf(-limit, value));
}

ControlPidResult ControlPid_Start(ControlPidContext *context, const ControlPidConfig *config)
{
    if ((context == NULL) || (ControlPid_ConfigValid(config) == 0U))
    { return CONTROL_PID_INVALID_INPUT; }
    memset(context, 0, sizeof(*context));
    context->started = 1U;
    return CONTROL_PID_OK;
}

ControlPidResult ControlPid_Stop(ControlPidContext *context)
{
    if (context == NULL) { return CONTROL_PID_INVALID_INPUT; }
    memset(context, 0, sizeof(*context));
    return CONTROL_PID_OK;
}

ControlPidResult ControlPid_Step(ControlPidContext *context, const ControlPidConfig *config,
    float reference, float measurement, float dt_s, float *output)
{
    float error, candidate_integral, derivative, raw, alpha;
    if (output == NULL) { return CONTROL_PID_INVALID_INPUT; }
    *output = 0.0f;
    if ((context == NULL) || (ControlPid_ConfigValid(config) == 0U) ||
        !isfinite(reference) || !isfinite(measurement) || !isfinite(dt_s) ||
        (fabsf(dt_s - config->sample_period_s) > config->sample_period_s * 1.0e-4f))
    { return CONTROL_PID_INVALID_INPUT; }
    if (context->started != 1U) { return CONTROL_PID_STOPPED; }
    if (!isfinite(context->integral) || !isfinite(context->derivative) ||
        !isfinite(context->previous_measurement) || (context->has_previous > 1U) ||
        (fabsf(context->integral) > config->integral_limit))
    { context->started = 0U; return CONTROL_PID_NUMERIC_ERROR; }
    error = reference - measurement;
    alpha = dt_s / (config->derivative_tau_s + dt_s);
    derivative = (context->has_previous != 0U) ?
        context->derivative + alpha * ((measurement - context->previous_measurement) /
        dt_s - context->derivative) : 0.0f;
    candidate_integral = context->integral + config->ki * error * dt_s;
    if (!isfinite(candidate_integral))
    { context->started = 0U; return CONTROL_PID_NUMERIC_ERROR; }
    candidate_integral = ControlPid_Limit(candidate_integral, config->integral_limit);
    raw = config->kp * error + candidate_integral - config->kd * derivative;
    if (!isfinite(error) || !isfinite(derivative) || !isfinite(raw))
    { context->started = 0U; return CONTROL_PID_NUMERIC_ERROR; }
    /* Conditional integration: do not integrate further into saturation. */
    if (((raw > config->output_limit) && (error > 0.0f)) ||
        ((raw < -config->output_limit) && (error < 0.0f)))
    { raw = config->kp * error + context->integral - config->kd * derivative; }
    else { context->integral = candidate_integral; }
    if (!isfinite(raw)) { context->started = 0U; return CONTROL_PID_NUMERIC_ERROR; }
    context->derivative = derivative;
    context->previous_measurement = measurement;
    context->has_previous = 1U;
    *output = ControlPid_Limit(raw, config->output_limit);
    return CONTROL_PID_OK;
}
