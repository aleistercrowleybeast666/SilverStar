#include "mag_rotation.h"
#include <math.h>
#include <stddef.h>
#include <string.h>

#define MAG_ROTATION_WINDOW 40U
#define MAG_ROTATION_MIN_DT_US 20000ULL
#define MAG_ROTATION_MAX_DT_US 150000ULL
#define MAG_ROTATION_MAX_STEP_RAD 0.16f
#define MAG_ROTATION_PACK_SCALE 722.66313f

static float Rotation_Dot(const float a[3], const float b[3])
{
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

static void Rotation_Cross(const float a[3], const float b[3], float c[3])
{
    c[0] = a[1] * b[2] - a[2] * b[1];
    c[1] = a[2] * b[0] - a[0] * b[2];
    c[2] = a[0] * b[1] - a[1] * b[0];
}

void MagRotation_VectorRotate(const float q[4], const float input[3], float output[3])
{
    float cross[3], second[3];
    if (q == NULL || input == NULL || output == NULL)
    {
        return;
    }
    Rotation_Cross(&q[1], input, cross);
    Rotation_Cross(&q[1], cross, second);
    for (uint8_t i = 0U; i < 3U; i++)
    {
        output[i] = input[i] + 2.0f * (q[0] * cross[i] + second[i]);
    }
}

void MagRotation_Reset(MagRotationFit *fit)
{
    if (fit == NULL)
    {
        return;
    }
    (void)memset(fit, 0, sizeof(*fit));
    fit->q[0] = 1.0f;
    fit->relative_rms = NAN;
}

static void Rotation_WindowReset(MagRotationFit *fit)
{
    (void)memset(fit->h, 0, sizeof(fit->h));
    (void)memset(fit->gradient, 0, sizeof(fit->gradient));
    fit->residual_sum = 0.0f;
    fit->energy = 0.0f;
    fit->pairs = 0U;
}

static void Rotation_Accumulate(MagRotationFit *fit, const float m[3], const float rate[3],
                                const float derivative[3])
{
    float j[3][3], observed[3], residual[3];
    const float inverse[4] = {fit->q[0], -fit->q[1], -fit->q[2], -fit->q[3]};
    float w[3];
    MagRotation_VectorRotate(inverse, rate, w);
    Rotation_Cross(m, derivative, observed);
    const float along = Rotation_Dot(m, w);
    for (uint8_t i = 0U; i < 3U; i++)
    {
        residual[i] = w[i] - m[i] * along + observed[i];
    }
    for (uint8_t k = 0U; k < 3U; k++)
    {
        float axis[3] = {0.0f, 0.0f, 0.0f}, cross[3];
        axis[k] = 1.0f;
        Rotation_Cross(w, axis, cross);
        float projection = Rotation_Dot(m, cross);
        for (uint8_t i = 0U; i < 3U; i++)
        {
            j[k][i] = cross[i] - m[i] * projection;
        }
    }
    for (uint8_t k = 0U; k < 3U; k++)
    {
        fit->gradient[k] += Rotation_Dot(j[k], residual);
        for (uint8_t l = 0U; l < 3U; l++)
        {
            fit->h[k][l] += Rotation_Dot(j[k], j[l]);
        }
    }
    fit->residual_sum += Rotation_Dot(residual, residual);
    fit->energy += Rotation_Dot(w, w) - along * along;
    fit->pairs++;
}

static MagRotationResult Rotation_CandidateUpdate(MagRotationFit *fit, float delta[3])
{
    float cross[3], next[4];
    float norm = sqrtf(Rotation_Dot(delta, delta));
    if (!isfinite(norm))
    {
        return MagRotationResult_Disturbed;
    }
    float gain = (norm > MAG_ROTATION_MAX_STEP_RAD) ? MAG_ROTATION_MAX_STEP_RAD / norm : 1.0f;
    for (uint8_t i = 0U; i < 3U; i++)
    {
        delta[i] *= 0.5f * gain;
    }
    Rotation_Cross(&fit->q[1], delta, cross);
    next[0] = fit->q[0] - Rotation_Dot(&fit->q[1], delta);
    for (uint8_t i = 0U; i < 3U; i++)
    {
        next[i + 1U] = fit->q[i + 1U] + fit->q[0] * delta[i] + cross[i];
    }
    norm = sqrtf(next[0] * next[0] + Rotation_Dot(&next[1], &next[1]));
    if (!isfinite(norm) || norm < 0.5f || next[0] / norm < 0.9238795f)
    {
        return MagRotationResult_Disturbed;
    }
    for (uint8_t i = 0U; i < 4U; i++)
    {
        fit->q[i] = next[i] / norm;
    }
    fit->validation = 1U;
    return MagRotationResult_Candidate;
}

static MagRotationResult Rotation_WindowFinish(MagRotationFit *fit)
{
    float cofactor[3][3], delta[3];
    Rotation_Cross(fit->h[1], fit->h[2], cofactor[0]);
    Rotation_Cross(fit->h[2], fit->h[0], cofactor[1]);
    Rotation_Cross(fit->h[0], fit->h[1], cofactor[2]);
    float determinant = Rotation_Dot(fit->h[0], cofactor[0]);
    float scale = (fit->h[0][0] + fit->h[1][1] + fit->h[2][2]) / 3.0f;
    if (!isfinite(determinant) || scale < 1.0f || determinant < 0.025f * scale * scale * scale ||
        fit->energy < 1.0f)
    {
        fit->good_windows = 0U;
        fit->validation = 0U;
        fit->relative_rms = NAN;
        return MagRotationResult_Unobservable;
    }
    fit->relative_rms = sqrtf(fit->residual_sum / fit->energy);
    if (fit->validation != 0U)
    {
        fit->validation = 0U;
        if (!isfinite(fit->relative_rms) || fit->relative_rms > 0.09f)
        {
            fit->good_windows = 0U;
            return MagRotationResult_Disturbed;
        }
        if (fit->good_windows < 2U)
        {
            fit->good_windows++;
        }
        return fit->good_windows == 2U ? MagRotationResult_Accepted : MagRotationResult_Candidate;
    }
    for (uint8_t i = 0U; i < 3U; i++)
    {
        delta[i] = -Rotation_Dot(cofactor[i], fit->gradient) / determinant;
    }
    return Rotation_CandidateUpdate(fit, delta);
}

/* Differentiate the two normalized magnetic observations at their midpoint.
 * Opposing/abrupt directions do not define a reliable local tangent. */
static uint8_t Rotation_TangentGet(const float current[3], const float previous[3], float dt,
                                   float mid[3], float derivative[3])
{
    for (uint8_t i = 0U; i < 3U; i++)
    {
        mid[i] = current[i] + previous[i];
        derivative[i] = (current[i] - previous[i]) / dt;
    }
    float norm = sqrtf(Rotation_Dot(mid, mid));
    if (norm < 1.8f)
    {
        return 0U;
    }
    for (uint8_t i = 0U; i < 3U; i++)
    {
        mid[i] /= norm;
    }
    return 1U;
}

static void Rotation_PreviousStore(MagRotationFit *fit, uint64_t time_us, float magnitude,
                                   const float direction[3])
{
    (void)memcpy(fit->previous, direction, sizeof(fit->previous));
    fit->previous_us = time_us;
    fit->previous_magnitude = magnitude;
}

MagRotationResult MagRotation_Step(MagRotationFit *fit, uint64_t time_us, const float field[3],
                                   const float average_gyro[3])
{
    float m[3], mid[3], derivative[3];
    if (fit == NULL || field == NULL || average_gyro == NULL)
    {
        return MagRotationResult_WrongSource;
    }
    fit->last_window_pairs = 0U;
    float magnitude = sqrtf(Rotation_Dot(field, field));
    float speed_squared = Rotation_Dot(average_gyro, average_gyro);
    if (!isfinite(magnitude) || magnitude < 10.0f || magnitude > 100.0f ||
        !isfinite(speed_squared) || speed_squared > 9.0f)
    {
        MagRotation_Reset(fit);
        return MagRotationResult_Disturbed;
    }
    for (uint8_t i = 0U; i < 3U; i++)
    {
        m[i] = field[i] / magnitude;
    }
    if (fit->previous_us == 0U)
    {
        if (time_us == 0U)
        {
            return MagRotationResult_Stale;
        }
        Rotation_PreviousStore(fit, time_us, magnitude, m);
        return MagRotationResult_Waiting;
    }
    if (time_us <= fit->previous_us || time_us - fit->previous_us < MAG_ROTATION_MIN_DT_US ||
        time_us - fit->previous_us > MAG_ROTATION_MAX_DT_US)
    {
        MagRotation_Reset(fit);
        return MagRotationResult_Stale;
    }
    if (fabsf(magnitude - fit->previous_magnitude) > 0.12f * magnitude)
    {
        MagRotation_Reset(fit);
        return MagRotationResult_Disturbed;
    }
    float dt = (float)(time_us - fit->previous_us) * 0.000001f;
    if (!Rotation_TangentGet(m, fit->previous, dt, mid, derivative))
    {
        MagRotation_Reset(fit);
        return MagRotationResult_Disturbed;
    }
    Rotation_PreviousStore(fit, time_us, magnitude, m);
    Rotation_Accumulate(fit, mid, average_gyro, derivative);
    if (fit->pairs < MAG_ROTATION_WINDOW)
    {
        return MagRotationResult_Training;
    }
    fit->last_window_pairs = (uint8_t)fit->pairs;
    MagRotationResult result = Rotation_WindowFinish(fit);
    Rotation_WindowReset(fit);
    return result;
}

uint32_t MagRotation_Encode(const float q[4])
{
    uint8_t largest = 0U, shift = 0U;
    if (q == NULL)
    {
        return 0U;
    }
    for (uint8_t i = 1U; i < 4U; i++)
    {
        if (fabsf(q[i]) > fabsf(q[largest]))
        {
            largest = i;
        }
    }
    uint32_t packed = (uint32_t)largest << 30U;
    for (uint8_t i = 0U; i < 4U; i++)
    {
        if (i != largest)
        {
            float value = (q[largest] < 0.0f ? -q[i] : q[i]) * MAG_ROTATION_PACK_SCALE;
            int32_t integer = (int32_t)roundf(fminf(511.0f, fmaxf(-511.0f, value)));
            packed |= ((uint32_t)integer & 1023U) << shift;
            shift = (uint8_t)(shift + 10U);
        }
    }
    return packed;
}

void MagRotation_Decode(uint32_t packed, float q[4])
{
    uint8_t largest = (uint8_t)(packed >> 30U), shift = 0U;
    float sum = 0.0f;
    if (q == NULL)
    {
        return;
    }
    for (uint8_t i = 0U; i < 4U; i++)
    {
        if (i != largest)
        {
            int32_t integer = (int32_t)((packed >> shift) & 1023U);
            if (integer >= 512)
            {
                integer -= 1024;
            }
            q[i] = (float)integer / MAG_ROTATION_PACK_SCALE;
            sum += q[i] * q[i];
            shift = (uint8_t)(shift + 10U);
        }
    }
    q[largest] = sqrtf(fmaxf(0.0f, 1.0f - sum));
}
