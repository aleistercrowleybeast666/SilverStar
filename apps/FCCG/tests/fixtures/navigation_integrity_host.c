#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "navigation_integrity.h"

static NavigationIntegrityContext s_context;
static NavigationIntegrityDecision s_decision;
static NavigationIntegrityInput s_input;

static NavigationIntegrityConfig Integrity_ConfigGet(void)
{
    const NavigationIntegrityConfig config = {
        1U, 120000U, 2000000U, 5000000U, 1000000U,
        10.0f, 4.0f, 4.0f, 6.0f, 1.2f
    };
    return config;
}

static int Integrity_Reset(void)
{
    NavigationIntegrityConfig config = Integrity_ConfigGet();
    (void)memset(&s_input, 0, sizeof(s_input));
    s_input.epoch = 1U;
    s_input.source = 1U;
    s_input.hacc_m = 0.5f;
    s_input.sacc_mps = 0.2f;
    s_input.valid_group_mask = 5U;
    return NavigationIntegrity_Reset(&s_context, &config) == NAV_INTEGRITY_PROCESS_OK;
}

static int Integrity_Feed(uint32_t index, float east, float north,
                          float east_velocity, float north_velocity)
{
    s_input.timestamp_us = 1000000ULL + (uint64_t)index * 40000ULL;
    s_input.sequence = index + 1U;
    s_input.position_en[0] = east;
    s_input.position_en[1] = north;
    s_input.velocity_en[0] = east_velocity;
    s_input.velocity_en[1] = north_velocity;
    return NavigationIntegrity_Receive(&s_context, &s_input, &s_decision) ==
        NAV_INTEGRITY_PROCESS_OK;
}

static int Integrity_CleanCheck(void)
{
    uint32_t index;
    if (!Integrity_Reset()) { return 0; }
    for (index = 0U; index < 500U; index++)
    {
        if (!Integrity_Feed(index, 0.04f * (float)index, 0.0f, 1.0f, 0.0f) ||
            s_decision.state != NAV_INTEGRITY_NORMAL) { return 0; }
    }
    return s_decision.evidence_valid != 0U &&
           s_decision.closure_norm_m < 0.01f;
}

static int Integrity_DriftCheck(void)
{
    uint32_t index;
    uint8_t saw_suspect = 0U;
    if (!Integrity_Reset()) { return 0; }
    for (index = 0U; index < 500U; index++)
    {
        float bias = index > 20U ? 0.1f * (float)(index - 20U) : 0.0f;
        if (!Integrity_Feed(index, 0.04f * (float)index + bias,
                            0.0f, 1.0f, 0.0f)) { return 0; }
        if (s_decision.state == NAV_INTEGRITY_SUSPECT) { saw_suspect = 1U; }
    }
    return saw_suspect != 0U && s_decision.state == NAV_INTEGRITY_REJECTED &&
           (s_decision.admitted_group_mask & 1U) == 0U &&
           (s_decision.admitted_group_mask & 4U) != 0U;
}

static int Integrity_JumpCheck(void)
{
    uint32_t index;
    if (!Integrity_Reset()) { return 0; }
    for (index = 0U; index < 120U; index++)
    {
        float jump = index == 40U ? 20.0f : 0.0f;
        if (!Integrity_Feed(index, 0.04f * (float)index + jump,
                            0.0f, 1.0f, 0.0f) ||
            s_decision.state != NAV_INTEGRITY_NORMAL) { return 0; }
    }
    return 1;
}

static int Integrity_PositionGapCheck(void)
{
    uint32_t index;
    if (!Integrity_Reset()) { return 0; }
    for (index = 0U; index < 20U; index++)
    {
        s_input.valid_group_mask = (index >= 5U && index < 10U) ? 4U : 5U;
        if (!Integrity_Feed(index, 0.08f * (float)index, 0.0f, 2.0f, 0.0f))
        { return 0; }
        if (index == 9U && (s_context.anchor_valid == 0U ||
                            s_context.integrated_velocity_en[0] < 0.7f))
        { return 0; }
    }
    return s_decision.evidence_valid != 0U &&
           s_decision.closure_norm_m < 0.01f &&
           s_context.anchor_timestamp_us == 1000000ULL;
}

static int Integrity_ChainBreakCheck(void)
{
    if (!Integrity_Reset() || !Integrity_Feed(0U, 0.0f, 0.0f, 1.0f, 0.0f) ||
        !Integrity_Feed(1U, 0.04f, 0.0f, 1.0f, 0.0f)) { return 0; }
    s_input.sacc_mps = 2.0f;
    if (!Integrity_Feed(2U, 0.08f, 0.0f, 1.0f, 0.0f) ||
        s_decision.chain_reset == 0U || s_context.anchor_valid != 0U ||
        s_decision.state != NAV_INTEGRITY_NORMAL) { return 0; }
    s_input.sacc_mps = 0.2f;
    if (!Integrity_Feed(3U, 0.12f, 0.0f, 1.0f, 0.0f) ||
        s_context.anchor_valid == 0U) { return 0; }
    s_input.timestamp_us += 500000ULL;
    s_input.sequence++;
    if (NavigationIntegrity_Receive(&s_context, &s_input, &s_decision) !=
        NAV_INTEGRITY_PROCESS_OK) { return 0; }
    return s_decision.chain_reset != 0U && s_decision.evidence_valid == 0U;
}

static int Integrity_RecoveryCheck(uint8_t break_chain)
{
    uint32_t index;
    if (!Integrity_Reset()) { return 0; }
    for (index = 0U; index < 230U; index++)
    {
        float bias = index == 0U ? 0.0f : 20.0f;
        if (!Integrity_Feed(index, 0.04f * (float)index + bias,
                            0.0f, 1.0f, 0.0f)) { return 0; }
    }
    if (s_decision.state != NAV_INTEGRITY_REJECTED) { return 0; }
    if (break_chain != 0U)
    {
        s_input.valid_group_mask = 1U;
        if (!Integrity_Feed(index, 0.04f * (float)index + 20.0f,
                            0.0f, 1.0f, 0.0f)) { return 0; }
        index++;
        s_input.valid_group_mask = 5U;
    }
    for (; index < 300U; index++)
    {
        float bias = break_chain != 0U ? 20.0f : 0.0f;
        if (!Integrity_Feed(index, 0.04f * (float)index + bias,
                            0.0f, 1.0f, 0.0f)) { return 0; }
    }
    return break_chain != 0U ?
        s_decision.state == NAV_INTEGRITY_REJECTED :
        s_decision.state == NAV_INTEGRITY_NORMAL;
}

static int Integrity_DynamicsCheck(void)
{
    uint32_t index;
    float east = 0.0f;
    float north = 0.0f;
    float previous_east_velocity = 0.0f;
    float previous_north_velocity = 0.0f;
    if (!Integrity_Reset()) { return 0; }
    for (index = 0U; index < 500U; index++)
    {
        float time_s = 0.04f * (float)index;
        float east_velocity = 2.0f + 3.0f * time_s + 0.5f * sinf(time_s);
        float north_velocity = 1.0f + 2.0f * time_s + cosf(time_s);
        if (index != 0U)
        {
            east += 0.02f * (previous_east_velocity + east_velocity);
            north += 0.02f * (previous_north_velocity + north_velocity);
        }
        if (!Integrity_Feed(index, east, north,
                            east_velocity, north_velocity) ||
            s_decision.state != NAV_INTEGRITY_NORMAL) { return 0; }
        previous_east_velocity = east_velocity;
        previous_north_velocity = north_velocity;
    }
    return s_decision.closure_norm_m < 0.02f;
}

static int Integrity_TraceEmit(void)
{
    uint32_t index;
    if (!Integrity_Reset()) { return 1; }
    for (index = 0U; index < 600U; index++)
    {
        float bias = (index >= 20U && index < 330U) ?
            0.1f * (float)(index - 20U) : 0.0f;
        s_input.valid_group_mask =
            (index >= 50U && index < 56U) ? 4U : 5U;
        s_input.sacc_mps = (index == 550U) ? 2.0f : 0.2f;
        if (!Integrity_Feed(index, 0.04f * (float)index + bias,
                            0.0f, 1.0f, 0.0f)) { return 2; }
        if (printf("%llu,%u,%u,%u,%u,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%u,%u,%.9g,%.9g,%u,%u,%u\n",
                   (unsigned long long)s_input.timestamp_us, s_input.epoch,
                   s_input.sequence, s_input.source, s_input.valid_group_mask,
                   s_input.position_en[0], s_input.position_en[1],
                   s_input.velocity_en[0], s_input.velocity_en[1],
                   s_input.hacc_m, s_input.sacc_mps,
                   (unsigned)s_decision.state,
                   (unsigned)s_decision.admitted_group_mask,
                   s_decision.position_r_scale,
                   s_decision.closure_norm_m,
                   (unsigned)s_decision.chain_reset,
                   (unsigned)s_decision.reason,
                   (unsigned)s_decision.evidence_valid) < 0)
        { return 3; }
    }
    return 0;
}

int main(int argc, char **argv)
{
    if ((argc == 2) && (strcmp(argv[1], "trace") == 0))
    { return Integrity_TraceEmit(); }
    if (!Integrity_CleanCheck()) { return 1; }
    if (!Integrity_DriftCheck()) { return 2; }
    if (!Integrity_JumpCheck()) { return 3; }
    if (!Integrity_PositionGapCheck()) { return 4; }
    if (!Integrity_ChainBreakCheck()) { return 5; }
    if (!Integrity_RecoveryCheck(0U)) { return 6; }
    if (!Integrity_RecoveryCheck(1U)) { return 7; }
    if (!Integrity_DynamicsCheck()) { return 8; }
    (void)printf("navigation_integrity_host: 8 scenarios, 0 failures, context=%u bytes\n",
                 (unsigned)sizeof(NavigationIntegrityContext));
    return 0;
}
