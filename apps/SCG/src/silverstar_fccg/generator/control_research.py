"""One compile-time controller implementation; no runtime callback registry."""
import json

from silverstar_fccg.project.control_research import ControlResearchBinding_Require


def ControlResearchFiles_Render(model, catalog):
    binding = ControlResearchBinding_Require(model, catalog)
    kind = binding['plugin_id'].rsplit('.', 1)[1] if binding else None
    lines = ['#include "control_research.h"', '#include <stddef.h>', '']
    if kind:
        title = kind.capitalize()
        lines += [f'#include "control_{kind}_project.h"', '#include "platform_memory.h"',
            f'static PLATFORM_CPU_FAST_BSS Control{title}Config s_config;',
            'static PLATFORM_CPU_FAST_BSS uint8_t s_started;']
        if kind == 'pid':
            lines.append('static PLATFORM_CPU_FAST_BSS ControlPidContext s_context;')
    lines += ['', 'ControlResearchResult ControlResearchBackend_Start(float *limit)', '{',
        '    if (limit == NULL) { return ControlResearchResult_InvalidInput; }', '    *limit = 0.0f;']
    if kind:
        lines += [f'    if (Control{title}_ProjectConfigGet(&s_config) != CONTROL_{kind.upper()}_OK)',
            '    { return ControlResearchResult_BackendError; }',
            '    if ((s_config.output_limit <= 0.0f) || (s_config.output_limit > 1.0f))',
            '    { return ControlResearchResult_InvalidInput; }']
        if kind == 'pid':
            lines += ['    if (ControlPid_Start(&s_context, &s_config) != CONTROL_PID_OK)',
                '    { return ControlResearchResult_BackendError; }']
        lines += ['    *limit = s_config.output_limit * CONTROL_RESEARCH_TORQUE_REFERENCE_NM;',
            '    s_started = 1U;', '    return ControlResearchResult_Ok;']
    else:
        lines += ['    return ControlResearchResult_Disabled;']
    lines += ['}', '', 'ControlResearchResult ControlResearchBackend_Stop(void)', '{']
    if kind:
        lines += ['    s_started = 0U;']
        if kind == 'pid':
            lines += ['    if (ControlPid_Stop(&s_context) != CONTROL_PID_OK)',
                '    { return ControlResearchResult_BackendError; }']
    lines += ['    return ControlResearchResult_Ok;', '}', '',
        'ControlResearchResult ControlResearchBackend_Step(float angle_rad, float rate_radps, float *output)', '{',
        '    if (output == NULL) { return ControlResearchResult_InvalidInput; }', '    *output = 0.0f;']
    if kind:
        lines += ['    if (s_started != 1U) { return ControlResearchResult_Stopped; }']
        if kind == 'pid':
            lines += ['    (void)rate_radps;',
                '    if (ControlPid_Step(&s_context, &s_config, 0.0f, angle_rad, 0.01f, output) != CONTROL_PID_OK)']
        else:
            lines += ['    const float error[2] = {angle_rad, rate_radps};',
                '    if (ControlLqr_Step(&s_config, error, output) != CONTROL_LQR_OK)']
        lines += ['    { *output = 0.0f; return ControlResearchResult_BackendError; }',
            '    *output *= CONTROL_RESEARCH_TORQUE_REFERENCE_NM;',
            '    return ControlResearchResult_Ok;']
    else:
        lines += ['    (void)angle_rad;', '    (void)rate_radps;', '    return ControlResearchResult_Disabled;']
    lines += ['}', '']
    contract = {'schema_id': 'silverstar.control-research-runtime/1', 'enabled': binding is not None,
        'binding': binding, 'kind': kind, 'period_us': 10000, 'maximum_lateness_us': 2000,
        'maximum_input_age_us': 20000, 'maximum_input_skew_us': 10000,
        'input': 'ENU body+Z Hamilton wxyz q_nb; atan2(axis_x,axis_z) rad and calibrated body-Y gyro rad/s',
        'domain': 'planar body-Y small-angle: |pitch|<=0.35 rad; |qx|,|qz|<=0.01; |rate|<=20 rad/s',
        'reference_rad': 0, 'sink': 'one bounded latest body-Y torque request snapshot; no actuator driver',
        'output': {'quantity': 'requested_body_y_torque', 'axis': 'body-Y', 'unit': 'N*m',
            'nm_per_core_output_unit': 1.0, 'maximum_absolute_torque_nm': 1.0},
        'electrical_output': False, 'deployable': False,
        'failure': 'withdraw publication, stop once, latch failure, ordinary lifecycle FAULT; no restart in mission',
        'timing': 'nominal discrete 10 ms, <=2 ms polling lateness; no catch-up execution; hardware WCET unproven'}
    return {'Generated/Src/project_control_research.c': '\n'.join(lines),
            'Generated/control_research.json': json.dumps(contract, ensure_ascii=False, indent=2) + '\n'}
