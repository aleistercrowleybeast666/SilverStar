#include "navigation_eskf.h"
#include "silverstar_assert.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#define ESKF_SMALL_ANGLE 1.0e-3f
#define ESKF_SYMMETRY_TOLERANCE 2.0e-5f
#define ESKF_TIME_TOLERANCE_S 2.0e-6f

static void Eskf_Cross(const float a[3], const float b[3], float out[3])
{
    out[0] = a[1] * b[2] - a[2] * b[1];
    out[1] = a[2] * b[0] - a[0] * b[2];
    out[2] = a[0] * b[1] - a[1] * b[0];
}

static float Eskf_Norm(const float *a, uint32_t count)
{
    float squared = 0.0f;
    uint32_t i;
    if ((a == NULL) || (count > NAV_ESKF_DIM)) { return NAN; }
    for (i = 0U; i < count; i++) { squared += a[i] * a[i]; }
    return sqrtf(squared);
}

static void Eskf_Skew(const float v[3], float out[3][3])
{
    memset(out, 0, 9U * sizeof(float));
    out[0][1] = -v[2]; out[0][2] = v[1];
    out[1][0] = v[2]; out[1][2] = -v[0];
    out[2][0] = -v[1]; out[2][1] = v[0];
}

static void Eskf_Rotation(const float q[4], float r[3][3])
{
    const float w = q[0], x = q[1], y = q[2], z = q[3];
    r[0][0] = 1.0f - 2.0f * (y*y + z*z);
    r[0][1] = 2.0f * (x*y - w*z); r[0][2] = 2.0f * (x*z + w*y);
    r[1][0] = 2.0f * (x*y + w*z);
    r[1][1] = 1.0f - 2.0f * (x*x + z*z); r[1][2] = 2.0f * (y*z - w*x);
    r[2][0] = 2.0f * (x*z - w*y); r[2][1] = 2.0f * (y*z + w*x);
    r[2][2] = 1.0f - 2.0f * (x*x + y*y);
}

static NavigationEskfResult Eskf_QuaternionInject(
    const float q[4], const float theta[3], float output[4])
{
    float angle = Eskf_Norm(theta, 3U);
    float factor = (angle < ESKF_SMALL_ANGLE) ?
        0.5f - angle * angle / 48.0f : sinf(0.5f * angle) / angle;
    float d[4] = {cosf(0.5f * angle), factor * theta[0],
                  factor * theta[1], factor * theta[2]};
    float norm;
    uint32_t i;
    output[0] = q[0]*d[0] - q[1]*d[1] - q[2]*d[2] - q[3]*d[3];
    output[1] = q[0]*d[1] + q[1]*d[0] + q[2]*d[3] - q[3]*d[2];
    output[2] = q[0]*d[2] - q[1]*d[3] + q[2]*d[0] + q[3]*d[1];
    output[3] = q[0]*d[3] + q[1]*d[2] - q[2]*d[1] + q[3]*d[0];
    norm = Eskf_Norm(output, 4U);
    if (!isfinite(norm) || (norm < ESKF_SMALL_ANGLE)) { return NAV_ESKF_NUMERIC_ERROR; }
    for (i = 0U; i < 4U; i++) { output[i] /= norm; }
    return NAV_ESKF_OK;
}

static void Eskf_StateRead(const NavigationEskfState *state, float x[16])
{
    memcpy(x, state->position, 3U * sizeof(float));
    memcpy(x + 3, state->velocity, 3U * sizeof(float));
    memcpy(x + 6, state->quaternion, 4U * sizeof(float));
    memcpy(x + 10, state->gyro_bias, 3U * sizeof(float));
    memcpy(x + 13, state->accel_bias, 3U * sizeof(float));
}

static void Eskf_StateCommit(NavigationEskfState *state, const float x[16])
{
    memcpy(state->position, x, 3U * sizeof(float));
    memcpy(state->velocity, x + 3, 3U * sizeof(float));
    memcpy(state->quaternion, x + 6, 4U * sizeof(float));
    memcpy(state->gyro_bias, x + 10, 3U * sizeof(float));
    memcpy(state->accel_bias, x + 13, 3U * sizeof(float));
}

/* Cholesky only diagnoses; it never changes the covariance to obtain a pass. */
static NavigationEskfResult Eskf_CovarianceValidate(
    const float p[NAV_ESKF_DIM][NAV_ESKF_DIM], float l[NAV_ESKF_DIM][NAV_ESKF_DIM])
{
    SILVERSTAR_ASSERT_OBJECT(p, float, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(l, float, SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    uint32_t i, j, k;
    memset(l, 0, NAV_ESKF_DIM * NAV_ESKF_DIM * sizeof(float));
    for (i = 0U; i < NAV_ESKF_DIM; i++)
    {
        for (j = 0U; j <= i; j++)
        {
            float sum = p[i][j];
            if (!isfinite(sum) || !isfinite(p[j][i]) ||
                (fabsf(sum - p[j][i]) > ESKF_SYMMETRY_TOLERANCE *
                 (1.0f + fabsf(sum)))) { return NAV_ESKF_NUMERIC_ERROR; }
            for (k = 0U; k < j; k++) { sum -= l[i][k] * l[j][k]; }
            if (i == j)
            {
                if (!isfinite(sum) || (sum <= 0.0f)) { return NAV_ESKF_NUMERIC_ERROR; }
                l[i][j] = sqrtf(sum);
            }
            else { l[i][j] = sum / l[j][j]; }
        }
    }
    return NAV_ESKF_OK;
}

NavigationEskfResult NavigationEskf_ConfigValidate(const NavigationEskfConfig *config)
{
    uint32_t i;
    if ((config == NULL) || !isfinite(config->gravity_mps2) ||
        (config->gravity_mps2 < 1.0f) || (config->gravity_mps2 > 20.0f) ||
        !isfinite(config->maximum_r_scale) || (config->maximum_r_scale < 1.0f) ||
        (config->maximum_r_scale > 4.0f)) { return NAV_ESKF_INVALID_INPUT; }
    if (!isfinite(config->gyro_noise_density) || (config->gyro_noise_density <= 0.0f) ||
        !isfinite(config->accel_noise_density) || (config->accel_noise_density <= 0.0f) ||
        !isfinite(config->gyro_bias_rw) || (config->gyro_bias_rw <= 0.0f) ||
        !isfinite(config->accel_bias_rw) || (config->accel_bias_rw <= 0.0f))
    { return NAV_ESKF_INVALID_INPUT; }
    for (i = 0U; i < 2U; i++)
    {
        if (!isfinite(config->nis_soft[i]) || !isfinite(config->nis_hard[i]) ||
            (config->nis_soft[i] <= 0.0f) || (config->nis_hard[i] <= config->nis_soft[i]))
        { return NAV_ESKF_INVALID_INPUT; }
    }
    return NAV_ESKF_OK;
}

NavigationEskfResult NavigationEskf_Initialize(
    NavigationEskfState *state, NavigationEskfWorkspace *workspace,
    const float nominal[16], const float covariance[NAV_ESKF_DIM][NAV_ESKF_DIM],
    uint64_t timestamp_us, uint32_t source, uint32_t generation)
{
    uint32_t i;
    float qnorm;
    if ((state == NULL) || (workspace == NULL) || (nominal == NULL) || (covariance == NULL))
    { return NAV_ESKF_INVALID_INPUT; }
    SILVERSTAR_ASSERT_OBJECT(state, NavigationEskfState, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(workspace, NavigationEskfWorkspace, SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    for (i = 0U; i < 16U; i++)
    { if (!isfinite(nominal[i])) { return NAV_ESKF_INVALID_INPUT; } }
    qnorm = Eskf_Norm(nominal + 6, 4U);
    if ((fabsf(qnorm - 1.0f) > 0.001f) ||
        (Eskf_Norm(nominal + 10, 3U) > NAV_ESKF_MAX_GYRO_BIAS_RADPS) ||
        (Eskf_Norm(nominal + 13, 3U) > NAV_ESKF_MAX_ACCEL_BIAS_MPS2))
    { return NAV_ESKF_INVALID_INPUT; }
    /* The backend initializes with covariance in workspace->f. Snapshot both
     * inputs before F becomes Cholesky scratch; scratch aliases stay valid. */
    memmove(workspace->candidate_x, nominal, sizeof(workspace->candidate_x));
    memmove(workspace->candidate_p, covariance, sizeof(workspace->candidate_p));
    if (Eskf_CovarianceValidate(
            (const float (*)[NAV_ESKF_DIM])workspace->candidate_p,
            workspace->f) != NAV_ESKF_OK)
    { return NAV_ESKF_NUMERIC_ERROR; }
    Eskf_StateCommit(state, workspace->candidate_x);
    memcpy(state->covariance, workspace->candidate_p, sizeof(state->covariance));
    state->timestamp_us = timestamp_us;
    state->source = source;
    state->generation = generation;
    state->initialized = 1U;
    return NAV_ESKF_OK;
}

static NavigationEskfResult Eskf_BodyValidate(
    const NavigationEskfState *state, const NavigationEskfBodyInput *input)
{
    SILVERSTAR_ASSERT_OBJECT(state, NavigationEskfState, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(input, NavigationEskfBodyInput, SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    uint32_t i, j;
    if ((state->initialized == 0U) || !isfinite(input->dt_s) ||
        (input->dt_s <= 0.0f) || (input->dt_s > NAV_ESKF_MAX_DT_S) ||
        ((input->quality_flags & 0x72U) != 0U) || (input->start_us != state->timestamp_us) ||
        (input->end_us <= input->start_us) || (input->source != state->source) ||
        (input->generation != state->generation)) { return NAV_ESKF_INVALID_INPUT; }
    if (fabsf((float)(input->end_us - input->start_us) * 1.0e-6f - input->dt_s) >
        ESKF_TIME_TOLERANCE_S) { return NAV_ESKF_INVALID_INPUT; }
    for (i = 0U; i < 2U; i++)
    {
        for (j = 0U; j < 3U; j++)
        {
            if (!isfinite(input->gyro_radps[i][j]) || !isfinite(input->accel_mps2[i][j]))
            { return NAV_ESKF_INVALID_INPUT; }
        }
    }
    return NAV_ESKF_OK;
}

static void Eskf_BodyIntegrate(const NavigationEskfState *state,
    const NavigationEskfBodyInput *input, float theta[3], float dv[3])
{
    SILVERSTAR_ASSERT_OBJECT(state, NavigationEskfState, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(input, NavigationEskfBodyInput, SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    float a[3], b[3], c[3], d[3], tsum[3], vsum[3];
    float coning[3], turn[3], scull1[3], scull2[3];
    uint32_t i;
    for (i = 0U; i < 3U; i++)
    {
        a[i] = (input->gyro_radps[0][i] - state->gyro_bias[i]) * input->dt_s * 0.5f;
        b[i] = (input->gyro_radps[1][i] - state->gyro_bias[i]) * input->dt_s * 0.5f;
        c[i] = (input->accel_mps2[0][i] - state->accel_bias[i]) * input->dt_s * 0.5f;
        d[i] = (input->accel_mps2[1][i] - state->accel_bias[i]) * input->dt_s * 0.5f;
        tsum[i] = a[i] + b[i]; vsum[i] = c[i] + d[i];
    }
    Eskf_Cross(a, b, coning); Eskf_Cross(tsum, vsum, turn);
    Eskf_Cross(a, d, scull1); Eskf_Cross(c, b, scull2);
    for (i = 0U; i < 3U; i++)
    {
        theta[i] = tsum[i] + (2.0f / 3.0f) * coning[i];
        dv[i] = vsum[i] + 0.5f * turn[i] + (2.0f / 3.0f) * (scull1[i] + scull2[i]);
    }
}

static void Eskf_Linearize(const NavigationEskfState *state,
    NavigationEskfWorkspace *work, const NavigationEskfBodyInput *input,
    const float rotation[3][3])
{
    SILVERSTAR_ASSERT_OBJECT(work, NavigationEskfWorkspace, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(input, NavigationEskfBodyInput, SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    float accel[3] = {0.0f}, gyro[3] = {0.0f}, sa[3][3], sw[3][3];
    uint32_t i, j, k;
    memset(work->f, 0, sizeof(work->f));
    for (i = 0U; i < 3U; i++)
    {
        accel[i] = 0.5f * (input->accel_mps2[0][i] + input->accel_mps2[1][i]) - state->accel_bias[i];
        gyro[i] = 0.5f * (input->gyro_radps[0][i] + input->gyro_radps[1][i]) - state->gyro_bias[i];
        work->f[i][3U+i] = 1.0f;
        work->f[6U+i][9U+i] = -1.0f;
    }
    Eskf_Skew(accel, sa); Eskf_Skew(gyro, sw);
    for (i = 0U; i < 3U; i++)
    {
        for (j = 0U; j < 3U; j++)
        {
            for (k = 0U; k < 3U; k++) { work->f[3U+i][6U+j] -= rotation[i][k] * sa[k][j]; }
            work->f[3U+i][12U+j] = -rotation[i][j];
            work->f[6U+i][6U+j] = -sw[i][j];
        }
    }
}

static void Eskf_TransitionBuild(NavigationEskfWorkspace *work, float dt)
{
    uint32_t i, j, k;
    for (i = 0U; i < NAV_ESKF_DIM; i++)
    {
        for (j = 0U; j < NAV_ESKF_DIM; j++)
        {
            float square = 0.0f;
            for (k = 0U; k < NAV_ESKF_DIM; k++) { square += work->f[i][k] * work->f[k][j]; }
            work->transition[i][j] = ((i == j) ? 1.0f : 0.0f) +
                dt * work->f[i][j] + 0.5f * dt * dt * square;
        }
    }
}

static void Eskf_Congruence(NavigationEskfWorkspace *work,
    const float p[NAV_ESKF_DIM][NAV_ESKF_DIM])
{
    SILVERSTAR_ASSERT_OBJECT(work, NavigationEskfWorkspace, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(p, float, SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    uint32_t i, j, k;
    for (i = 0U; i < NAV_ESKF_DIM; i++)
    {
        for (j = 0U; j < NAV_ESKF_DIM; j++)
        {
            float sum = 0.0f;
            for (k = 0U; k < NAV_ESKF_DIM; k++) { sum += work->transition[i][k] * p[k][j]; }
            work->product_row[j] = sum;
        }
        /* P and transition stay unchanged. Consume this row before reusing
         * it; every dot product retains the original k iteration order. */
        for (j = 0U; j <= i; j++)
        {
            float sum = 0.0f;
            for (k = 0U; k < NAV_ESKF_DIM; k++) { sum += work->product_row[k] * work->transition[j][k]; }
            work->candidate_p[i][j] = sum;
            work->candidate_p[j][i] = sum;
        }
    }
}

static void Eskf_NoiseAdd(NavigationEskfWorkspace *work,
    const NavigationEskfConfig *config, float dt, float quality_scale)
{
    SILVERSTAR_ASSERT_OBJECT(work, NavigationEskfWorkspace, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(config, NavigationEskfConfig, SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    float spectral[NAV_ESKF_DIM] = {0.0f};
    uint32_t i, j, k;
    for (i = 0U; i < 3U; i++)
    {
        spectral[3U+i] = config->accel_noise_density * config->accel_noise_density * quality_scale;
        spectral[6U+i] = config->gyro_noise_density * config->gyro_noise_density * quality_scale;
        spectral[9U+i] = config->gyro_bias_rw * config->gyro_bias_rw * quality_scale;
        spectral[12U+i] = config->accel_bias_rw * config->accel_bias_rw * quality_scale;
    }
    /* Positive-weight Simpson integration of (I+Ft) W (I+Ft)' expanded exactly. */
    for (i = 0U; i < NAV_ESKF_DIM; i++)
    {
        for (j = 0U; j <= i; j++)
        {
            float quadratic = 0.0f;
            float value;
            for (k = 0U; k < NAV_ESKF_DIM; k++)
            { quadratic += work->f[i][k] * spectral[k] * work->f[j][k]; }
            value = ((i == j) ? dt * spectral[i] : 0.0f) +
                0.5f * dt * dt * (work->f[i][j] * spectral[j] + spectral[i] * work->f[j][i]) +
                dt * dt * dt * quadratic / 3.0f;
            work->candidate_p[i][j] += value;
            work->candidate_p[j][i] = work->candidate_p[i][j];
        }
    }
}

NavigationEskfResult NavigationEskf_Predict(NavigationEskfState *state,
    NavigationEskfWorkspace *work, const NavigationEskfConfig *config,
    const NavigationEskfBodyInput *input)
{
    float theta[3], dv[3], r[3][3];
    uint32_t i, j;
    if ((state == NULL) || (work == NULL) || (input == NULL) ||
        (NavigationEskf_ConfigValidate(config) != NAV_ESKF_OK)) { return NAV_ESKF_INVALID_INPUT; }
    SILVERSTAR_ASSERT_OBJECT(state, NavigationEskfState, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(work, NavigationEskfWorkspace, SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    if (Eskf_BodyValidate(state, input) != NAV_ESKF_OK) { return NAV_ESKF_INVALID_INPUT; }
    Eskf_StateRead(state, work->candidate_x);
    Eskf_BodyIntegrate(state, input, theta, dv);
    Eskf_Rotation(state->quaternion, r);
    for (i = 0U; i < 3U; i++)
    {
        float change = (i == 2U) ? -config->gravity_mps2 * input->dt_s : 0.0f;
        for (j = 0U; j < 3U; j++) { change += r[i][j] * dv[j]; }
        work->candidate_x[i] += state->velocity[i] * input->dt_s + 0.5f * change * input->dt_s;
        work->candidate_x[3U+i] += change;
        if (!isfinite(work->candidate_x[i]) || !isfinite(work->candidate_x[3U+i]))
        { return NAV_ESKF_NUMERIC_ERROR; }
    }
    if (Eskf_QuaternionInject(state->quaternion, theta, work->candidate_x + 6) != NAV_ESKF_OK)
    { return NAV_ESKF_NUMERIC_ERROR; }
    Eskf_Linearize(state, work, input, (const float (*)[3])r);
    Eskf_TransitionBuild(work, input->dt_s);
    Eskf_Congruence(work, (const float (*)[NAV_ESKF_DIM])state->covariance);
    Eskf_NoiseAdd(work, config, input->dt_s, (input->quality_flags & 0x05U) ? 4.0f : 1.0f);
    /* Linearization F is dead after NoiseAdd; candidate P is still separate. */
    if (Eskf_CovarianceValidate((const float (*)[NAV_ESKF_DIM])work->candidate_p, work->f) != NAV_ESKF_OK)
    { return NAV_ESKF_NUMERIC_ERROR; }
    Eskf_StateCommit(state, work->candidate_x);
    memcpy(state->covariance, work->candidate_p, sizeof(state->covariance));
    state->timestamp_us = input->end_us;
    return NAV_ESKF_OK;
}

static NavigationEskfResult Eskf_MeasurementLinearize(
    const NavigationEskfState *state, NavigationEskfWorkspace *work,
    const NavigationEskfMeasurement *measurement, NavigationEskfOutcome *outcome)
{
    SILVERSTAR_ASSERT_OBJECT(measurement, NavigationEskfMeasurement, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(outcome, NavigationEskfOutcome, SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    float r[3][3], lever_skew[3][3], offset[3], omega[3], offset_skew[3][3];
    uint32_t row, axis, i, k;
    if ((measurement->group >= 5U) || (measurement->physically_valid == 0U) ||
        (state->initialized == 0U)) { return NAV_ESKF_INVALID_INPUT; }
    outcome->dimension = ((measurement->group == 0U) || (measurement->group == 2U)) ? 2U : 1U;
    for (i = 0U; i < 3U; i++)
    {
        if (!isfinite(measurement->lever_arm_b_m[i]) || !isfinite(measurement->angular_rate_b_radps[i]))
        { return NAV_ESKF_INVALID_INPUT; }
        omega[i] = measurement->angular_rate_b_radps[i] - state->gyro_bias[i];
    }
    Eskf_Rotation(state->quaternion, r);
    Eskf_Skew(measurement->lever_arm_b_m, lever_skew);
    if ((measurement->group == 2U) || (measurement->group == 3U))
    { Eskf_Cross(omega, measurement->lever_arm_b_m, offset); }
    else { memcpy(offset, measurement->lever_arm_b_m, sizeof(offset)); }
    if (measurement->group == 4U) { memset(offset, 0, sizeof(offset)); }
    Eskf_Skew(offset, offset_skew);
    memset(work->h, 0, sizeof(work->h));
    for (row = 0U; row < outcome->dimension; row++)
    {
        float prediction;
        axis = (outcome->dimension == 1U) ? 2U : row;
        i = axis + (((measurement->group == 2U) || (measurement->group == 3U)) ? 3U : 0U);
        prediction = (i < 3U) ? state->position[axis] : state->velocity[axis];
        work->h[row][i] = 1.0f;
        if (!isfinite(measurement->observation[row]) || !isfinite(measurement->variance[row]) ||
            (measurement->variance[row] <= 0.0f)) { return NAV_ESKF_INVALID_INPUT; }
        for (i = 0U; i < 3U; i++)
        {
            prediction += r[axis][i] * offset[i];
            for (k = 0U; k < 3U; k++)
            {
                work->h[row][6U+i] -= r[axis][k] * offset_skew[k][i];
                if ((measurement->group == 2U) || (measurement->group == 3U))
                { work->h[row][9U+i] += r[axis][k] * lever_skew[k][i]; }
            }
        }
        outcome->innovation[row] = measurement->observation[row] - prediction;
        outcome->effective_variance[row] = measurement->variance[row];
    }
    return NAV_ESKF_OK;
}

static NavigationEskfResult Eskf_InnovationSolve(const NavigationEskfState *state,
    NavigationEskfWorkspace *work, NavigationEskfOutcome *outcome)
{
    SILVERSTAR_ASSERT_OBJECT(work, NavigationEskfWorkspace, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(outcome, NavigationEskfOutcome, SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    float s[2][2] = {{0.0f}}, inverse[2][2] = {{0.0f}};
    uint32_t i, j, a, b;
    float determinant;
    if ((outcome->dimension < 1U) || (outcome->dimension > NAV_ESKF_OBSERVATIONS))
    { return NAV_ESKF_INVALID_INPUT; }
    for (i = 0U; i < NAV_ESKF_DIM; i++)
    {
        for (a = 0U; a < outcome->dimension; a++)
        {
            work->gain[i][a] = 0.0f;
            for (j = 0U; j < NAV_ESKF_DIM; j++)
            { work->gain[i][a] += state->covariance[i][j] * work->h[a][j]; }
        }
    }
    for (a = 0U; a < outcome->dimension; a++)
    {
        for (b = 0U; b < outcome->dimension; b++)
        {
            s[a][b] = (a == b) ? outcome->effective_variance[a] : 0.0f;
            for (i = 0U; i < NAV_ESKF_DIM; i++) { s[a][b] += work->h[a][i] * work->gain[i][b]; }
        }
    }
    determinant = (outcome->dimension == 1U) ? s[0][0] : s[0][0]*s[1][1] - s[0][1]*s[1][0];
    if (!isfinite(determinant) || (determinant <= 0.0f) || (s[0][0] <= 0.0f))
    { return NAV_ESKF_NUMERIC_ERROR; }
    inverse[0][0] = (outcome->dimension == 1U) ? 1.0f / determinant : s[1][1] / determinant;
    if (outcome->dimension == 2U)
    {
        inverse[1][1] = s[0][0] / determinant;
        inverse[0][1] = -s[0][1] / determinant; inverse[1][0] = -s[1][0] / determinant;
    }
    outcome->nis = 0.0f;
    for (a = 0U; a < outcome->dimension; a++)
    { for (b = 0U; b < outcome->dimension; b++)
      { outcome->nis += outcome->innovation[a] * inverse[a][b] * outcome->innovation[b]; } }
    for (i = 0U; i < NAV_ESKF_DIM; i++)
    {
        float old[2] = {work->gain[i][0], work->gain[i][1]};
        for (a = 0U; a < outcome->dimension; a++)
        {
            work->gain[i][a] = 0.0f;
            for (b = 0U; b < outcome->dimension; b++) { work->gain[i][a] += old[b] * inverse[b][a]; }
        }
    }
    return isfinite(outcome->nis) ? NAV_ESKF_OK : NAV_ESKF_NUMERIC_ERROR;
}

static NavigationEskfResult Eskf_CorrectionBuild(const NavigationEskfState *state,
    NavigationEskfWorkspace *work, NavigationEskfOutcome *outcome)
{
    SILVERSTAR_ASSERT_OBJECT(state, NavigationEskfState, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(outcome, NavigationEskfOutcome, SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    uint32_t i, a;
    outcome->gain_norm = 0.0f;
    for (i = 0U; i < NAV_ESKF_DIM; i++)
    {
        work->correction[i] = 0.0f;
        for (a = 0U; a < outcome->dimension; a++)
        {
            work->correction[i] += work->gain[i][a] * outcome->innovation[a];
            outcome->gain_norm += work->gain[i][a] * work->gain[i][a];
        }
    }
    outcome->gain_norm = sqrtf(outcome->gain_norm);
    if (Eskf_Norm(work->correction + 6, 3U) > NAV_ESKF_MAX_INJECTION_RAD)
    { return NAV_ESKF_MODEL_MISMATCH; }
    Eskf_StateRead(state, work->candidate_x);
    for (i = 0U; i < 3U; i++)
    {
        work->candidate_x[i] += work->correction[i];
        work->candidate_x[3U+i] += work->correction[3U+i];
        work->candidate_x[10U+i] += work->correction[9U+i];
        work->candidate_x[13U+i] += work->correction[12U+i];
    }
    if ((Eskf_Norm(work->candidate_x + 10, 3U) > NAV_ESKF_MAX_GYRO_BIAS_RADPS) ||
        (Eskf_Norm(work->candidate_x + 13, 3U) > NAV_ESKF_MAX_ACCEL_BIAS_MPS2))
    { return NAV_ESKF_MODEL_MISMATCH; }
    return Eskf_QuaternionInject(state->quaternion, work->correction + 6, work->candidate_x + 6);
}

static void Eskf_JosephBuild(const NavigationEskfState *state,
    NavigationEskfWorkspace *work, const NavigationEskfOutcome *outcome)
{
    SILVERSTAR_ASSERT_OBJECT(work, NavigationEskfWorkspace, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(outcome, NavigationEskfOutcome, SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    uint32_t i, j, a;
    for (i = 0U; i < NAV_ESKF_DIM; i++)
    {
        for (j = 0U; j < NAV_ESKF_DIM; j++)
        {
            work->transition[i][j] = (i == j) ? 1.0f : 0.0f;
            for (a = 0U; a < outcome->dimension; a++)
            { work->transition[i][j] -= work->gain[i][a] * work->h[a][j]; }
        }
    }
    Eskf_Congruence(work, (const float (*)[NAV_ESKF_DIM])state->covariance);
    for (i = 0U; i < NAV_ESKF_DIM; i++)
    {
        for (j = 0U; j <= i; j++)
        {
            for (a = 0U; a < outcome->dimension; a++)
            { work->candidate_p[i][j] += work->gain[i][a] * outcome->effective_variance[a] * work->gain[j][a]; }
            work->candidate_p[j][i] = work->candidate_p[i][j];
        }
    }
}

static void Eskf_ResetJacobianBuild(NavigationEskfWorkspace *work)
{
    SILVERSTAR_ASSERT_OBJECT(work, NavigationEskfWorkspace, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT(Eskf_Norm(work->correction + 6, 3U) <= NAV_ESKF_MAX_INJECTION_RAD, SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);

    float skew[3][3], angle = Eskf_Norm(work->correction + 6, 3U);
    float a, b;
    uint32_t i, j, k;
    if (angle < ESKF_SMALL_ANGLE)
    { a = 0.5f - angle * angle / 24.0f; b = 1.0f / 6.0f - angle * angle / 120.0f; }
    else
    { a = (1.0f - cosf(angle)) / (angle * angle); b = (angle - sinf(angle)) / (angle * angle * angle); }
    Eskf_Skew(work->correction + 6, skew);
    memset(work->transition, 0, sizeof(work->transition));
    for (i = 0U; i < NAV_ESKF_DIM; i++) { work->transition[i][i] = 1.0f; }
    for (i = 0U; i < 3U; i++)
    {
        for (j = 0U; j < 3U; j++)
        {
            float square = 0.0f;
            for (k = 0U; k < 3U; k++) { square += skew[i][k] * skew[k][j]; }
            work->transition[6U+i][6U+j] += -a * skew[i][j] + b * square;
        }
    }
    memcpy(work->f, work->candidate_p, sizeof(work->f));
    Eskf_Congruence(work, (const float (*)[NAV_ESKF_DIM])work->f);
}

NavigationEskfResult NavigationEskf_Update(NavigationEskfState *state,
    NavigationEskfWorkspace *work, const NavigationEskfConfig *config,
    const NavigationEskfMeasurement *measurement, NavigationEskfOutcome *outcome)
{
    NavigationEskfResult result;
    uint32_t i;
    if (outcome == NULL) { return NAV_ESKF_INVALID_INPUT; }
    memset(outcome, 0, sizeof(*outcome));
    outcome->result = NAV_ESKF_INVALID_INPUT; outcome->r_scale = 1.0f;
    if ((state == NULL) || (work == NULL) || (measurement == NULL) ||
        (NavigationEskf_ConfigValidate(config) != NAV_ESKF_OK)) { return outcome->result; }
    SILVERSTAR_ASSERT_OBJECT(state, NavigationEskfState, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(work, NavigationEskfWorkspace, SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    result = Eskf_MeasurementLinearize(state, work, measurement, outcome);
    if (result != NAV_ESKF_OK) { outcome->result = result; return result; }
    result = Eskf_InnovationSolve(state, work, outcome);
    if (result != NAV_ESKF_OK) { outcome->result = result; return result; }
    if (outcome->nis > config->nis_hard[outcome->dimension - 1U])
    { outcome->result = NAV_ESKF_REJECTED_NIS; return outcome->result; }
    if (outcome->nis > config->nis_soft[outcome->dimension - 1U])
    {
        outcome->r_scale = fminf(config->maximum_r_scale,
            outcome->nis / config->nis_soft[outcome->dimension - 1U]);
        for (i = 0U; i < outcome->dimension; i++) { outcome->effective_variance[i] *= outcome->r_scale; }
        result = Eskf_InnovationSolve(state, work, outcome);
        if (result != NAV_ESKF_OK) { outcome->result = result; return result; }
    }
    result = Eskf_CorrectionBuild(state, work, outcome);
    if (result != NAV_ESKF_OK) { outcome->result = result; return result; }
    if (!isfinite(outcome->gain_norm) || (outcome->gain_norm <= 0.0f))
    { outcome->result = NAV_ESKF_NUMERIC_ERROR; return outcome->result; }
    Eskf_JosephBuild(state, work, outcome);
    Eskf_ResetJacobianBuild(work);
    /* Reset congruence has consumed the original P copy in F. */
    result = Eskf_CovarianceValidate((const float (*)[NAV_ESKF_DIM])work->candidate_p, work->f);
    if (result != NAV_ESKF_OK) { outcome->result = result; return result; }
    for (i = 0U; i < 16U; i++)
    { if (!isfinite(work->candidate_x[i])) { outcome->result = NAV_ESKF_NUMERIC_ERROR; return outcome->result; } }
    Eskf_StateCommit(state, work->candidate_x);
    memcpy(state->covariance, work->candidate_p, sizeof(state->covariance));
    outcome->result = (outcome->r_scale > 1.0f) ? NAV_ESKF_SOFT_WEIGHTED : NAV_ESKF_OK;
    return outcome->result;
}
