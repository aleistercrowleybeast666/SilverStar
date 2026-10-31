"""Actual owner bodies; deterministic Host boundaries, not MCU timing evidence."""
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess

from estimator_health_support import function_get
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve


def test_scope_stop_invalidates_published_navigation_before_owner_runs(tmp_path, workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create('Scope publication')
    project = tmp_path / 'project'
    service.Project_Save(model, project, confirm_dangerous=True)
    graph = SourceGraph_Resolve(model, service.catalog)
    sources = {name: (project / 'APP/Src' / name).read_text(encoding='utf-8')
               for name in ('ins_task.c', 'estimator_task.c')}
    header = r'''
#include <stdio.h>
#include <string.h>
#include "ins_task.h"
#include "estimator_task.h"
#include "ins_mechanization.h"
#include "platform_critical.h"
#include "system_mission_process.h"
#undef SYSTEM_FUSION_ALGORITHM
#define SYSTEM_FUSION_ALGORITHM SYSTEM_FUSION_NONE
static uint8_t s_stopped, s_mission_running;
static InsOutputSnapshot s_output, s_published_output;
static EstimatorOutputSnapshot s_published_snapshot;
static union { InsInertialContext inertial; InsMechanizationContext pure_ins; } s_navigation_input;
uint8_t SystemMissionProcess_InsStoppedGet(void) { return s_stopped; }
uint8_t SystemMissionProcess_EstimatorStoppedGet(void) { return s_stopped; }
PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState value) { (void)value; }
static void InsTask_DiagnosticsPublish(void) { }
'''
    names = {'ins_task.c': ('InsTask_IrqLock', 'InsTask_IrqUnlock',
                           'InsTask_MissionScopeStop', 'Ins_GetLatestSnapshot'),
             'estimator_task.c': ('EstimatorTask_IrqLock', 'EstimatorTask_IrqUnlock',
                                  'Estimator_GetLatestSnapshot')}
    bodies = '\n'.join(function_get(sources[file], name) for file, values in names.items() for name in values)
    main = r'''
int main(void) {
    InsOutputSnapshot ins = {0}; EstimatorOutputSnapshot estimator = {0};
    s_mission_running = 1U;
    s_output.ins_valid = 1U; s_output.alignment_valid = 1U; s_output.mission_running = 1U;
    s_output.timestamp_us = 123456ULL; s_published_output = s_output;
    s_published_snapshot.initialized = 1U; s_published_snapshot.mission_running = 1U;
    if (!Ins_GetLatestSnapshot(&ins) || !Estimator_GetLatestSnapshot(&estimator)) { return 2; }
    s_stopped = 1U;
    if (Ins_GetLatestSnapshot(&ins) || Estimator_GetLatestSnapshot(&estimator) ||
        ins.ins_valid || ins.alignment_valid || ins.mission_running ||
        estimator.initialized || estimator.mission_running) {
        puts("scope publication violated"); return 3;
    }
    if (s_mission_running != 1U) { return 4; } /* Reader never mutates its task owner. */
    InsTask_MissionScopeStop();
    if (s_mission_running || s_published_output.ins_valid || s_published_output.alignment_valid ||
        s_published_output.mission_running || s_published_output.timestamp_us != 123456ULL) { return 5; }
    InsTask_MissionScopeStop();
    if (s_mission_running) { return 6; }
    puts("scope publication and owner stop passed"); return 0;
}
'''
    baseline = bodies
    for name, file in (('Ins_GetLatestSnapshot', 'ins_task.c'), ('Estimator_GetLatestSnapshot', 'estimator_task.c')):
        previous = subprocess.check_output(['git', 'show',
            'aaef99f82f0d33617ae82353b0ac760123d56cc0:apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/' + file],
            text=True, encoding='utf-8', cwd=workspace_root.parents[1])
        baseline = baseline.replace(function_get(sources[file], name), function_get(previous, name))
    compiler = shutil.which('gcc')
    assert compiler, 'Real Host GCC is required'
    receipt = {'scope': 'Unmodified extracted getters/INS stop; real mechanization reset; Host atomic flag/lock/diagnostic boundary. No task scheduling or MCU timing proof.', 'runs': []}
    for label, body in (('before', baseline), ('after', bodies)):
        unit = tmp_path / (label + '.c'); unit.write_text(header + body + main, encoding='utf-8')
        executable = tmp_path / (label + '.exe')
        command = [compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
            '-include', str(project / 'Generated/Inc/project_flight_config.h'),
            *['-I' + str(project / item) for item in graph.include_dirs],
            str(unit), str(project / 'Algorithm/INS/Coning2Sculling2/Src/ins_mechanization.c'),
            str(project / 'Algorithm/Common/Src/attitude_frame.c'), str(project / 'Common/Src/silverstar_assert.c'),
            '-lm', '-o', str(executable)]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=90)
        (tmp_path / (label + '-compile.log')).write_text(compiled.stdout + compiled.stderr, encoding='utf-8')
        assert compiled.returncode == 0, compiled.stderr
        run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
        receipt['runs'].append(dict(label=label, command=command, source_sha256=hashlib.sha256(unit.read_bytes()).hexdigest(),
            compile_exit=compiled.returncode, exit=run.returncode, stdout=run.stdout, stderr=run.stderr))
        (tmp_path / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        assert run.returncode == (3 if label == 'before' else 0), run.stdout + run.stderr


def test_estimator_owner_stop_resets_once_and_drains_with_existing_bound(tmp_path, workspace_root):
    """Actual dispatch/abort bodies, instrumented bus and algorithm boundaries."""
    path = workspace_root / 'plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/estimator_task.c'
    source = path.read_text(encoding='utf-8')
    cap = re.search(r'^#define ESTIMATOR_MAX_PREDICTIONS_PER_CYCLE \d+U$', source, re.M).group(0)
    header = r'''
#include <stdint.h>
#include <stdio.h>
#define SYSTEM_BUILD_NAVIGATION_BACKEND_ENABLED 1U
#define SYSTEM_BUILD_ESTIMATOR_ENABLED 1U
#define SILVERSTAR_PROTOCOL_LOGGING_ENABLED 1U
#define ESTIMATOR_BUS_RESULT_OK 0U
#define ESTIMATOR_HEALTH_PREDICTION_QUEUE_OVERFLOW 1U
typedef struct { uint32_t value; } SystemInertialIncrement;
static struct { uint8_t mission_running, initialized; int kf, pending_barometer; } s_estimator;
static struct { uint8_t initialized; uint32_t generation; } s_preparation;
static struct { uint8_t initialized, mission_running; uint32_t health_flags; } s_snapshot;
static struct { uint32_t sequence, last_prediction_count, max_prediction_count, prediction_cap_count; } s_estimator_task_timing;
static uint32_t queued, popped, processed, backend_resets, kf_resets, fusion_resets, publications, logs, pending_resets, origin_resets;
static uint8_t stopped;
static uint8_t Estimator_NavigationBackendSelected(void) { return 1U; }
static void SystemNavigationBackend_Reset(void) { backend_resets++; }
static void NavigationKf_Reset(int *kf) { *kf=0; kf_resets++; }
static void Estimator_FusionReset(void) { fusion_resets++; }
static void Estimator_SnapshotPublish(uint64_t time) { (void)time; publications++; }
static void Estimator_LogPush(uint64_t time) { (void)time; logs++; }
static void EstimatorBarometerPending_Reset(int *pending) { *pending=0; pending_resets++; }
static void Estimator_OriginWindowReset(void) { origin_resets++; }
static uint8_t SystemMissionProcess_EstimatorStoppedGet(void) { return stopped; }
static uint8_t EstimatorBus_PredictionPop(SystemInertialIncrement *value) {
    if (!queued) { return 1U; } queued--; popped++; value->value=popped; return 0U;
}
static void Estimator_PredictionProcess(const SystemInertialIncrement *value) { (void)value; processed++; }
'''
    bodies = '\n'.join(function_get(source, name) for name in
                       ('EstimatorTask_AbortMission', 'Estimator_PredictionsProcessCycle'))
    main = r'''
int main(void) {
    s_estimator.mission_running=1U; s_estimator.initialized=1U;
    s_snapshot.initialized=1U; s_snapshot.mission_running=1U; s_preparation.initialized=1U;
    queued=3U; Estimator_PredictionsProcessCycle();
    if (processed!=3U || backend_resets || popped!=3U) { return 2; }
    stopped=1U; queued=ESTIMATOR_MAX_PREDICTIONS_PER_CYCLE+7U;
    Estimator_PredictionsProcessCycle();
    if (processed!=3U || queued!=7U || s_estimator.mission_running || s_estimator.initialized ||
        s_snapshot.initialized || s_snapshot.mission_running || s_preparation.initialized ||
        s_preparation.generation!=1U || backend_resets!=1U || kf_resets!=1U || fusion_resets!=1U ||
        pending_resets!=1U || origin_resets!=1U || publications!=1U || logs!=1U) { return 3; }
    if (s_estimator_task_timing.last_prediction_count!=ESTIMATOR_MAX_PREDICTIONS_PER_CYCLE ||
        s_estimator_task_timing.prediction_cap_count!=1U || !s_snapshot.health_flags) { return 4; }
    Estimator_PredictionsProcessCycle(); Estimator_PredictionsProcessCycle();
    if (queued || backend_resets!=1U || processed!=3U || s_preparation.generation!=1U ||
        s_estimator_task_timing.prediction_cap_count!=1U) { return 5; }
    puts("actual owner stop resets once; drain remains bounded"); return 0;
}
'''
    compiler = shutil.which('gcc')
    assert compiler, 'Real Host GCC is required'
    unit = tmp_path / 'bounded_stop.c'
    unit.write_text(header + cap + '\n' + bodies + main, encoding='utf-8')
    executable = tmp_path / 'bounded_stop.exe'
    command = [compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', str(unit), '-o', str(executable)]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert compiled.returncode == 0, compiled.stderr
    run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
    (tmp_path / 'receipt.json').write_text(json.dumps(dict(
        scope='Unmodified extracted estimator dispatch and AbortMission; instrumented bus/algorithm calls, not MCU scheduling or numerical reset proof.',
        owner_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), command=command,
        compile_exit=compiled.returncode, exit=run.returncode, stdout=run.stdout, stderr=run.stderr), indent=2), encoding='utf-8')
    assert run.returncode == 0, run.stdout + run.stderr
