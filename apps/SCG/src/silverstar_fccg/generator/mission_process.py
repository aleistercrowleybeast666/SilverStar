"""Frozen bounded phase table. The MCU owns evaluation and transition timestamps."""
import json
import zlib

from silverstar_fccg.project.mission_process import MissionProcessFirmware_Require, SIGNALS, EVENTS


def MissionProcessFiles_Render(model, catalog):
    process = MissionProcessFirmware_Require(model, catalog)
    stages = process['stages']
    hashes = [zlib.crc32(stage['stage_id'].encode('ascii')) for stage in stages]
    if len(set(hashes)) != len(hashes):
        raise ValueError('mission_process_stage_hash_collision')
    recovery_hash = next((identity for stage, identity in zip(stages, hashes)
                          if stage['action']['kind'] == 'request_recovery'), 0)
    from silverstar_fccg.project.mission_functions import Functions_Derive
    functions = Functions_Derive(model, catalog)['functions']
    boundaries = ('system_prepare', 'mission_start', 'stage_enter', 'stage_exit', 'system_landed', 'lifecycle_end')
    ranges = []
    dependency_mask = 0
    for field, identity in (('category', 'telemetry'), ('category', 'recording'),
                            ('output', 'navigation.pure_ins'), ('output', 'navigation.estimate'),
                            ('output', 'control.research.command')):
        function = next((row for row in functions if row[field] == identity), None)
        values = []
        for key, default in (('start', 'system_prepare'), ('stop', 'lifecycle_end')):
            bound = function[key] if function else {'kind': default, 'stage_id': ''}
            index = next((i for i, row in enumerate(stages) if row['stage_id'] == bound['stage_id']), 0)
            values.extend((boundaries.index(bound['kind']), index))
        dependencies = sum(1 << {'ins': 2, 'estimator': 3}[identity]
            for identity in function['depends_on'] if identity in ('ins', 'estimator')) if function else 0
        values.append(dependencies)
        if identity in ('telemetry', 'recording'): dependency_mask |= dependencies
        ranges.append('    {' + ', '.join(str(value) + 'U' for value in values) + '},')
    header = ('#ifndef __PROJECT_MISSION_PROCESS_H\n#define __PROJECT_MISSION_PROCESS_H\n'
              '#include "system_mission_process.h"\n'
              f'#define PROJECT_MISSION_STAGE_COUNT {len(stages)}U\n'
              f'#define PROJECT_MISSION_MAXIMUM_GAP_US {process["maximum_gap_ms"] * 1000}ULL\n'
              f'#define PROJECT_MISSION_PHASE_AUTHORITY {int(model.mission_process is not None)}U\n'
              f'#define PROJECT_MISSION_RECOVERY_STAGE_HASH {recovery_hash}UL\n'
              f'#define PROJECT_MISSION_FUNCTION_DEPENDENCIES {dependency_mask}U\n'
              f'#define PROJECT_MISSION_CONTROL_ENABLED {int(any(row["output"] == "control.research.command" for row in functions))}U\n'
              '#endif /* __PROJECT_MISSION_PROCESS_H */\n')
    rows = []
    for stage, identity in zip(stages, hashes):
        condition = stage['condition']; signal = list(SIGNALS).index(condition['signal'])
        event = 1 << EVENTS.index(condition['value']) if signal == 0 else 0
        threshold = 0.0 if signal == 0 else float(condition['value'])
        rows.append(f'    {{{identity}UL, {stage["hold_ms"]}UL, {event}UL, {threshold:.9e}f, {signal}U, {int(condition["operator"] == "<=")}U}},')
    source = ('#include "project_mission_process.h"\n#include <stddef.h>\n\n'
              'static const SystemMissionStageConfig s_stages[PROJECT_MISSION_STAGE_COUNT] =\n{\n' + '\n'.join(rows) + '\n};\n\n'
              'uint8_t ProjectMissionStage_CountGet(void)\n{ return PROJECT_MISSION_STAGE_COUNT; }\n\n'
              'SystemMissionProcessResult ProjectMissionStage_ConfigGet(uint8_t index, SystemMissionStageConfig *stage)\n'
              '{\n    if ((stage == NULL) || (index >= PROJECT_MISSION_STAGE_COUNT))\n'
              '    { return SystemMissionProcessResult_Invalid; }\n'
              '    *stage = s_stages[index];\n    return SystemMissionProcessResult_Entered;\n}\n')
    source += ('\nstatic const SystemMissionFunctionConfig s_functions[5] =\n{\n' + '\n'.join(ranges) + '\n};\n'
               'SystemMissionProcessResult ProjectMissionFunction_ConfigGet(uint8_t index, SystemMissionFunctionConfig *config)\n'
               '{\n    if ((config == NULL) || (index >= 5U)) { return SystemMissionProcessResult_Invalid; }\n'
               '    *config = s_functions[index];\n    return SystemMissionProcessResult_Entered;\n}\n')
    document = {'schema': 'silverstar.mission-process-generated/1', 'process': process,
                'stage_id_hash_algorithm': 'crc32-ieee-ascii',
                'stage_ids': dict(zip([stage['stage_id'] for stage in stages], hashes)),
                'continuous_functions': functions,
                'acceleration_source': 'calibrated specific-force magnitude / 9.80665 m/s^2; fresh canonical IMU only'}
    return {'Generated/Inc/project_mission_process.h': header,
            'Generated/Src/project_mission_process.c': source,
            'Generated/mission_process.json': json.dumps(document, ensure_ascii=False, indent=2) + '\n'}
