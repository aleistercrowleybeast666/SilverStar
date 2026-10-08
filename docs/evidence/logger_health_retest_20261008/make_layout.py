"""Offline GDB symbol/type queries only; no target connection."""
from pathlib import Path
import hashlib
import json
import subprocess

out = Path(__file__).resolve().parent
elf = out / 'project/Flight_Controller/build/FCCG/SilverStar_F407/Release/auto/SilverStar_0_1_1.elf'
expressions = {
    'lifecycle': "'silverstar_flight_cycle.c'::s_lifecycle_state",
    'initialized': "'logger_bus.c'::s_initialized",
    'accepting': "'logger_bus.c'::s_accepting_records",
    'finalization': "'logger_bus.c'::s_finalization_state",
    'bus': "'logger_bus.c'::s_diagnostics",
    'task': "'logger_task.c'::s_diagnostics",
    'mission_id': "'logger_task.c'::s_logger.snapshot.mission_id",
    'calibration_generation': "'logger_task.c'::s_logger.snapshot.calibration_generation",
    'mag_hash': "'logger_task.c'::s_logger.snapshot.mag_calibration_set_hash",
    'snapshot_sequence': "'logger_task.c'::s_logger.snapshot.snapshot_sequence",
    'snapshot_ready': "'logger_task.c'::s_diagnostics.snapshot_ready",
    'session_active': "'logger_task.c'::s_logger.session_active",
    'session_finalized': "'logger_task.c'::s_logger.session_finalized",
    'path': "'log_sink_service.c'::s_sink.path",
    'sink_health': "'log_sink_service.c'::s_sink.health",
    'assert_fault': "'silverstar_assert.c'::s_assert_fault",
    'estimator_running': "'estimator_task.c'::s_estimator.mission_running",
    'nav_timestamp': "'estimator_task.c'::s_published_snapshot.timestamp_us",
    'nav_sequence': "'estimator_task.c'::s_published_snapshot.update_sequence",
    'nav_health_flags': "'estimator_task.c'::s_published_snapshot.health_flags",
    'monotonic_end_us': 's_estimator_task_timing.last_end_us',
    'health_groups': "'system_navigation_health.c'::s_groups",
    'previous_health_state': "'system_navigation_health.c'::s_previous_state",
}
for group in range(5):
    for member in ['last_successful_fusion_us', 'has_success', 'state', 'reason']:
        expressions[f'group{group}_{member}'] = f"'system_navigation_health.c'::s_groups[{group}].{member}"
commands = ['set pagination off', 'file ' + elf.as_posix()]
for key, expression in expressions.items():
    commands.append(f'printf "FIELD|{key}|%lu|%lu\\n", (unsigned long)&({expression}), (unsigned long)sizeof({expression})')
commands += ["ptype /o LoggerBusDiagnostics", "ptype /o LoggerTaskDiagnostics",
             "ptype /o SystemLogSinkHealth", "ptype /o 'silverstar_assert.c'::s_assert_fault", "quit"]
script = out / 'offline_layout.gdb'
script.write_text('\n'.join(commands) + '\n', encoding='utf-8')
argv = ['D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-gdb.exe', '-batch', '-nx', '-x', str(script)]
result = subprocess.run(argv, capture_output=True, timeout=30)
(out / 'offline_layout.log').write_bytes(result.stdout + result.stderr)
fields = {}
for line in result.stdout.decode(errors='replace').splitlines():
    if line.startswith('FIELD|'):
        _, key, address, size = line.split('|')
        fields[key] = dict(expression=expressions[key], address=int(address), bytes=int(size))
record = dict(argv=argv, exit_code=result.returncode, target_connection=False,
              elf=str(elf), elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(), fields=fields)
(out / 'diagnostic_layout.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
assert result.returncode == 0 and len(fields) == len(expressions), result.stderr.decode(errors='replace')
print('Offline ELF-derived fields: ' + str(len(fields)))
