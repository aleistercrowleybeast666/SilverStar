from pathlib import Path
import hashlib, json, subprocess, ctypes, os
root = Path(__file__).resolve().parents[2]
out = Path(__file__).parent
owner = root/'apps/FCCG/plugins/builtin/silverstar_algorithm_estimator_sf6/payload'
core = root/'apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload'
docs = root/'docs/FCCG/sf6_stage3_20261002'
ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
paths = [owner/'Algorithm/Estimator/SF6/Inc/navigation_sf6.h',
         owner/'Algorithm/Estimator/SF6/Src/navigation_sf6.c',
         owner/'Algorithm/Estimator/SF6/Src/navigation_sf6_backend.c']
text = ['# SF6 complete implementation review, second checkpoint\n',
        'This is software review input, not hardware validation, a stack proof, or completed critical-contract acceptance. Six gains are ordered vE/vN/vU/pE/pN/pU; all defaults are 0.2 and unbenchmarked.\n',
        'Predict uses the existing INS ENU delta velocity and trapezoidal position integration. Accepted measurements use the preceding completed IMU boundary; no fractional interpolation or chronological reapplication of intervening observations is implemented. Corrections are propagated affinely to all later stored boundaries. Across sources the current predict call applies GNSS groups 0,1,2,3 then barometer group 4. GNSS height is ellipsoid height relative to frozen GNSS origin; barometer height uses common altitude resolution minus frozen barometer origin. Both observe pU with the same gain_pu, without an extra hidden vertical gain. This arrival ordering is rate-dependent.\n',
        'Each group tracks strictly increasing measurement/receive times and forward half-range packet sequence; duplicate, old and future observations return ordinary errors. Packet duplicates are skipped before group dispatch. Trusted native timestamps bypass configured fallback delays; untrusted GNSS position/velocity and barometer use their own declared delays. Ring/history corruption is terminal failure. External nonfinite values or overflow return errors before partial state publication.\n',
        'Common health ABI receives placeholder finite statistics solely for admission/age tracking; SF6 snapshot covariance/NIS/R fields are NaN, wire statistics are unavailable (FFFF), and SF6_STATE has no covariance. This interface choice and source provenance require personal review. GNSS selector changes currently wait for mission reinitialization; this slice does not implement cold backup.\n']
for path in paths:
    data = path.read_bytes()
    text += [f'\n## {path.relative_to(root).as_posix()}\n\nSHA256 `{hashlib.sha256(data).hexdigest()}`\n\n```c\n',
             data.decode('utf-8').replace('\r\n','\n'), '\n```\n']
(docs/'FULL_IMPLEMENTATION_REVIEW.md').write_text(''.join(text),encoding='utf-8')
# Pre-fix/current terminal-fault proof uses the same actual assertions and tests.
old = out/'navigation_sf6_548b89f.c'
old.write_bytes(subprocess.check_output(['git','show','548b89f:apps/FCCG/plugins/builtin/silverstar_algorithm_estimator_sf6/payload/Algorithm/Estimator/SF6/Src/navigation_sf6.c'],cwd=root))
reports = []
for name, source in [('baseline548b89f',old),('current',paths[1])]:
    exe=out/(name+'_history_fault.exe')
    command=[r'D:\msys64\ucrt64\bin\gcc.exe','-std=c11','-Wall','-Wextra','-Werror','-Wconversion','-Wsign-conversion','-pedantic','-O2',
             '-I'+str(core/'Common/Inc'),'-I'+str(core/'Tests/Host'),'-I'+str(owner/'Algorithm/Estimator/SF6/Inc'),
             str(core/'Common/Src/silverstar_assert.c'),str(source),str(owner/'Tests/Host/test_navigation_sf6.c'),'-lm','-o',str(exe)]
    built=subprocess.run(command,capture_output=True,env=dict(os.environ,TEMP=str(out),TMP=str(out)))
    (out/(name+'_history_compile.log')).write_bytes(built.stdout+built.stderr)
    report=dict(name=name,command=command,compile_exit=built.returncode,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    if built.returncode==0:
        for case,args in [('normal',[]),('history',['history'])]:
            result=subprocess.run([str(exe),*args],capture_output=True,timeout=10)
            (out/(name+'_'+case+'.log')).write_bytes(result.stdout+result.stderr)
            report[case+'_exit']=result.returncode
        report['executable_sha256']=hashlib.sha256(exe.read_bytes()).hexdigest()
    reports.append(report)
(out/'history_fault_proof.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
print(json.dumps(reports,indent=2))
