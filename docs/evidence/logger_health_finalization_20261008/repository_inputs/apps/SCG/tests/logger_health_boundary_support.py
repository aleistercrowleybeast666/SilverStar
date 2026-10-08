"""Host lifecycle proof: exact publisher body + real LoggerBus/health/policy.

No target I/O, no simulated durable acknowledgement and no full MCU scheduler.
"""
from pathlib import Path
import hashlib,json,os,re,subprocess

from estimator_health_support import function_get

CASES = ["flight", "recovery", "landed_grace", "draining_failure",
         "finalized_stops_publication", "full_queue_failure", "finalized_race_failure",
         "landing_and_grace_events", "new_epoch", "inactive", "draining_race_failure"]


def boundary_run(project: Path, output: Path, fixture: Path, source: Path | None = None) -> dict:
    output.mkdir(parents=True,exist_ok=True)
    owner=source or project/'APP/Src/estimator_task.c'
    body=function_get(owner.read_text(encoding='utf-8'),'Estimator_HealthEventsPublish')
    prelude='''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "test_common.h"
#include "estimator_task.h"
#include "logger_bus.h"
#include "system_user_config.h"
#include "system_lifecycle.h"
#include "system_navigation_health.h"
#include "platform_critical.h"
#include "silverstar_assert.h"
static struct { uint8_t mission_running; } s_estimator;
static EstimatorOutputSnapshot s_snapshot;
'''
    unit=output/'actual_health_boundary.c'
    unit.write_text(prelude+body+'\n'+fixture.read_text(encoding='utf-8'),encoding='utf-8')
    host=(project/'Tests/Host/run_tests.ps1').read_text(encoding='utf-8')
    includes=re.findall(r'"-I\$repoRoot\\([^"\r\n]+)"',host)
    profile=json.loads((project/'SilverStar.ssproject').read_text(encoding='utf-8'))['build']['target_profile']
    includes.insert(0,'Targets/'+profile+'/Inc')
    argv=['D:/msys64/ucrt64/bin/gcc.exe','-std=c11','-O2','-Wall','-Wextra','-Werror',
          '-ffunction-sections','-fdata-sections','-Wl,--gc-sections',
          '-Wl,--wrap=LoggerBus_FinalizationStateGet','-include',str(project/'Generated/Inc/project_flight_config.h')]
    argv+=['-I'+str(project/p.replace('\\','/')) for p in includes]
    sources=['APP/Src/logger_bus.c','Common/Src/common_spsc_queue.c',
             'System/Src/system_log_policy.c','System/Src/system_navigation_health.c',
             'System/Src/system_profile.c','System/Src/system_navigation_profile.c',
             'System/Src/system_estimator_profile.c','Generated/Src/project_metadata.c',
             'Generated/Src/project_log_config.c','Generated/Src/project_log_decoder_profile.c',
             'Protocol/SSLOG/Src/sslog_records.c','Protocol/SSLOG/Src/sslog_protocol.c']
    binary=output/'boundary.exe'
    argv += [str(project/p) for p in sources]+[str(unit),'-lm','-o',str(binary)]
    env=dict(os.environ,PATH='D:/msys64/ucrt64/bin;'+os.environ.get('PATH',''))
    result=subprocess.run(argv,capture_output=True,env=env,timeout=60)
    (output/'compile.log').write_bytes(result.stdout+result.stderr)
    evidence={'argv':argv,'compile_exit':result.returncode,'source':str(owner),
              'source_sha256':hashlib.sha256(owner.read_bytes()).hexdigest(),
              'publisher_body_sha256':hashlib.sha256(body.encode()).hexdigest(),
              'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),
              'scope':'Actual extracted publisher; linked real LoggerBus, queues, stream policy and health supervisor. Host fatal assertion and IRQ boundaries; close interleaving injected after a real state snapshot. No storage I/O or MCU timing proof.',
              'linked_sources':{p:hashlib.sha256((project/p).read_bytes()).hexdigest() for p in sources},'cases':[]}
    if result.returncode==0:
        for case,name in enumerate(CASES):
            result=subprocess.run([str(binary),str(case)],capture_output=True,env=env,timeout=10)
            (output/f'case_{case:02}.log').write_bytes(result.stdout+result.stderr)
            evidence['cases'].append({'case':case,'name':name,'exit':result.returncode,
                                      'stdout':result.stdout.decode(errors='replace'),
                                      'stderr':result.stderr.decode(errors='replace')})
    (output/'results.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    return evidence
