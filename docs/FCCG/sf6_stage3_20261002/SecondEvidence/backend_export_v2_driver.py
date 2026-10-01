from pathlib import Path
import subprocess, re, json, os
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent
P=OUT/'SF6_v6/Flight_Controller'
OWNER=ROOT/'apps/FCCG/plugins/builtin/silverstar_algorithm_estimator_sf6/payload'
runner=(P/'Tests/Host/run_tests.ps1').read_text(encoding='utf-8')
includes=['-include',str(P/'Generated/Inc/project_flight_config.h')]
for suffix in re.findall(r'"-I\$repoRoot([^"\r\n]+)"',runner.split('function Invoke-HostCompiler')[0]):
    includes.append('-I'+str(P/suffix.lstrip('\\').replace('\\','/')))
sources=[P/rel for rel in ['Tests/Host/host_platform_mock.c','APP/Src/logger_bus.c',
 'Common/Src/common_spsc_queue.c','Common/Src/silverstar_assert.c','System/Src/system_log_policy.c',
 'System/Src/system_profile.c','System/Src/system_navigation_profile.c','System/Src/system_estimator_profile.c',
 'Generated/Src/project_metadata.c','Generated/Src/project_log_decoder_profile.c','Generated/Src/project_log_config.c',
 'Algorithm/Common/Src/geodesy_local.c','Algorithm/Common/Src/attitude_frame.c',
 'Algorithm/INS/Coning2Sculling2/Src/ins_mechanization.c','APP/Src/estimator_bus.c',
 'System/Src/system_navigation_health.c','System/Src/system_gnss_quality.c','System/Src/system_barometer.c',
 'System/Src/system_time.c','Protocol/SSLOG/Src/sslog_records.c','Protocol/SSLOG/Src/sslog_protocol.c']]
sources += [OWNER/'Tests/Host/test_sf6_backend.c',OWNER/'Algorithm/Estimator/SF6/Src/navigation_sf6.c',OWNER/'Algorithm/Estimator/SF6/Src/navigation_sf6_backend.c']
export='--export' in __import__('sys').argv
exe=OUT/('backend_export_v2.exe' if export else 'backend_probe.exe')
command=[r'D:\msys64\ucrt64\bin\gcc.exe','-std=c11','-Wall','-Wextra','-Werror','-pedantic','-O2','-flto',
 '-ffunction-sections','-fdata-sections','-Wl,--gc-sections',
 '-DSYSTEM_BUILD_FUSION_ALGORITHM=SYSTEM_FUSION_SF6','-DSYSTEM_BUILD_ESTIMATOR_ENABLED=0U']
if export: command+=['-DTEST_SF6_BACKEND_EXPORT=1']
command+=includes+[str(p) for p in sources]+['-lm','-o',str(exe)]
prefix='backend_export_v2' if export else 'backend_probe'
env=dict(os.environ,TEMP=str(OUT),TMP=str(OUT))
with (OUT/(prefix+'_compile.log')).open('wb') as log:
 code=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,env=env).returncode
report=dict(command=command,compile_exit=code)
if code==0:
 args=[str(exe)]
 if export:
  log_file=OUT/'SF6_ACTUAL_BACKEND_v2.BIN'
  if log_file.exists(): raise SystemExit('export path must be fresh')
  args.append(str(log_file))
 with (OUT/(prefix+'_run.log')).open('wb') as log:
  report['run_exit']=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,timeout=60,env=env).returncode
(OUT/(prefix+'_results.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
print(report['compile_exit'],report.get('run_exit'))
