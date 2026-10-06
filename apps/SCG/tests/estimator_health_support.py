"""Narrow Host orchestration proof using unchanged extracted application bodies."""
from pathlib import Path
import hashlib,json,re,subprocess,os

def function_get(text: str, name: str) -> str:
    match=re.search(r"(?:static\s+)?[A-Za-z_][A-Za-z_0-9 *]*\s+"+re.escape(name)+r"\s*\([^;]*?\)\s*\{",text)
    if match is None: raise ValueError(name)
    depth=1
    for end in range(match.end(),len(text)):
        depth+=(text[end]=='{')-(text[end]=='}')
        if depth==0:return text[match.start():end+1]
    raise ValueError("unclosed "+name)

def health_run(project: Path, output: Path, fixture: Path) -> dict:
    output.mkdir(parents=True,exist_ok=True)
    app=(project/'APP/Src/estimator_task.c').read_text()
    ins=(project/'APP/Src/ins_task.c').read_text()
    def typedef_get(name):
        end=app.index('} '+name+';')+len('} '+name+';')
        start=app.rfind('typedef struct',0,end)
        return app[start:end]
    source='''#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "test_common.h"
#include "estimator_task.h"
#include "estimator_bus.h"
#include "imu_sample_bus.h"
#include "logger_bus.h"
#include "estimator_barometer_pending.h"
#include "geodesy_local.h"
#include "navigation_kf_replay.h"
#include "ins_mechanization.h"
#include "attitude_frame.h"
#include "system_user_config.h"
#include "system_navigation_health.h"
#include "system_estimator_profile.h"
#include "system_estimator_diagnostics.h"
#include "system_gnss_if.h"
#include "platform_critical.h"
#include "silverstar_assert.h"
#define ESTIMATOR_GNSS_ORIGIN_WINDOW_SIZE SYSTEM_BUILD_GNSS_ORIGIN_STORAGE_SAMPLES
#define ESTIMATOR_BARO_ORIGIN_WINDOW_SIZE SYSTEM_ESTIMATOR_BARO_ORIGIN_WINDOW_SAMPLES
'''
    source+='\n'.join(typedef_get(n) for n in ['EstimatorGnssOriginSample','EstimatorBarometerOriginSample','EstimatorGnssOriginWindow','EstimatorBarometerOriginWindow','EstimatorRuntime'])
    source+='''
static EstimatorRuntime s_estimator;
static EstimatorOutputSnapshot s_snapshot, s_published_snapshot;
static NavigationReplayContext s_replay;
static NavigationReplayStorage s_replay_storage;
static uint32_t s_replay_epoch;
static EstimatorPreparationSnapshot s_preparation;
static uint32_t s_bus_overflow;
static uint8_t s_measurement_fault;
static void Estimator_DiagnosticsPublish(uint64_t time) { (void)time; }
static void Estimator_LogPush(uint64_t time) { (void)time; }
static void Estimator_BarometerDiagnosticsPublish(void) { }
void EstimatorBus_StatsGet(EstimatorBusStats *stats) { memset(stats,0,sizeof(*stats)); stats->prediction_overflow_count=s_bus_overflow; }
void ImuSampleBus_StatsGet(ImuSampleBusStats *stats) { memset(stats,0,sizeof(*stats)); }
uint32_t LoggerBus_OverflowCountGet(void) { return 0U; }
PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }
SystemLifecycleState SystemLifecycle_GetState(void) { return SYSTEM_STATE_FLIGHT; }
static void Estimator_PredictionLogPush(const SystemInertialIncrement *p, uint32_t op, NavigationReplayResult result, uint8_t attitude) { (void)p;(void)op;(void)result;(void)attitude; }
static void Estimator_GnssUpdate(uint64_t time) {
 if(s_measurement_fault) {
  const float delta[3]={0};
  (void)NavigationReplay_Predict(&s_replay,&s_estimator.kf,time+1U,delta,0.005f);
 }
}
static void Estimator_BarometerUpdate(uint64_t time) { (void)time; }
'''
    source+='#include "system_lifecycle.h"\n'
    # Lifecycle type must precede its stub.
    source=source.replace('#include "system_user_config.h"','#include "system_lifecycle.h"\n#include "system_user_config.h"')
    names=['EstimatorTask_IrqLock','EstimatorTask_IrqUnlock','EstimatorTask_SnapshotCommit','Estimator_OperationNext',
           'Estimator_CoreHealthFlagsMap','Estimator_FaultSnapshotPublish','Estimator_ReplayFaultStop',
           'Estimator_SnapshotPublish','Estimator_AccelerationPublish','Estimator_PredictionApply','Estimator_KfPredictionApply',
           'Estimator_PredictionProcess','EstimatorTask_RollbackMissionStart','Estimator_GetLatestSnapshot']
    extracted={}
    for name in names:
        try:body=function_get(app,name)
        except ValueError:
            if name in {'Estimator_CoreHealthFlagsMap','Estimator_FaultSnapshotPublish','Estimator_ReplayFaultStop','Estimator_KfPredictionApply'}:continue
            raise
        extracted[name]=hashlib.sha256(body.encode()).hexdigest();source+='\n'+body+'\n'
    body=function_get(ins,'InsTask_NavigationDiagnosticsApply');extracted['InsTask_NavigationDiagnosticsApply']=hashlib.sha256(body.encode()).hexdigest();source+='\n'+body+'\n'
    body=function_get((project/'APP/Src/diagnostic_log.c').read_text(),'DiagnosticLog_StatsRecordBuild');extracted['DiagnosticLog_StatsRecordBuild']=hashlib.sha256(body.encode()).hexdigest();source+='\n'+body+'\n'+fixture.read_text()
    unit=output/'actual_app_health.c';unit.write_text(source)
    script=(project/'Tests/Host/run_tests.ps1').read_text();includes=re.findall(r'"-I\$repoRoot\\([^"\n]+)"',script)
    argv=['D:/msys64/ucrt64/bin/gcc.exe','-std=c11','-O2','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-include',str(project/'Generated/Inc/project_flight_config.h')]
    argv+=['-I'+str(project/q.replace('\\','/')) for q in includes]
    argv += ['-I'+str(project/'Platform/Inc')]
    argv += [str(project/q) for q in ['Algorithm/Estimator/KF6/Src/navigation_kf.c','Algorithm/Estimator/KF6/Src/navigation_kf_replay.c','Algorithm/Common/Src/attitude_frame.c','Algorithm/INS/Coning2Sculling2/Src/ins_mechanization.c','APP/Src/estimator_barometer_pending.c','System/Src/system_navigation_health.c','System/Src/system_time.c','Common/Src/silverstar_assert.c']]
    # Real clock/health helpers need only this Host hardware boundary.
    source=unit.read_text()+'''\n#include "platform_time.h"
PlatformResult PlatformTime_Init(void) { return PLATFORM_OK; }
uint64_t PlatformTime_Us(void) { return 1000000ULL; }
''';unit.write_text(source)
    argv += [str(unit),'-lm','-o',str(output/'health.exe')]
    env=dict(os.environ,PATH='D:/msys64/ucrt64/bin;'+os.environ.get('PATH',''))
    result=subprocess.run(argv,capture_output=True,text=True,env=env,timeout=60)
    (output/'compile.log').write_text(result.stdout+result.stderr)
    evidence={'argv':argv,'compile_exit':result.returncode,'extracted_body_hashes':extracted,'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),'scope':'Actual extracted application bodies, linked actual KF6/replay/attitude/mechanization; Host locks/sensor absence/log sinks. No full task scheduler or MCU proof.','cases':[]}
    (output/'results.json').write_text(json.dumps(evidence,indent=2))
    if result.returncode:return evidence
    for case in range(23):
        result=subprocess.run([str(output/'health.exe'),str(case)],capture_output=True,text=True,env=env,timeout=10)
        evidence['cases'].append({'case':case,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        (output/f'case_{case:02}.log').write_text(result.stdout+result.stderr)
    (output/'results.json').write_text(json.dumps(evidence,indent=2));return evidence
