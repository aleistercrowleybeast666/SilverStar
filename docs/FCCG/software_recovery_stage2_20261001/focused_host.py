from pathlib import Path
import subprocess, json, shutil
root = Path(__file__).resolve().parents[2]
out = Path(__file__).parent
project = out / 'candidate_a_v4/Flight_Controller'
core = root / 'apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload'
radio = root / 'apps/FCCG/plugins/builtin/silverstar_device_telemetry_sx1281/payload'
build = out / 'focused-host'
build.mkdir(exist_ok=True)
includes = [radio / 'Devices/Telemetry/SX1281/Inc', project / 'Tests/Host', project / 'Generated/Inc',
            *sorted(p for p in project.rglob('Inc') if 'build' not in p.parts),
            project / 'Middlewares/Third_Party/SX1280lib', project / 'System/User']
base = ['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
        '-include', str(project / 'Generated/Inc/project_flight_config.h'),
        *['-I' + str(p) for p in includes]]
groups = {
 'telemetry': [core / 'Tests/Host/test_telemetry.c', core / 'Modules/Src/telemetry_service.c',
               project / 'System/Calibration/Src/system_calibration_correction.c',
               project / 'Protocol/Src/air_protocol.c', project / 'Common/Src/silverstar_assert.c'],
 'sx1281_device': [core / 'Tests/Host/test_sx1281_device.c',
               project / 'Generated/Src/project_resources.c',
               radio / 'Devices/Telemetry/SX1281/Src/sx1281_device.c',
               project / 'Common/Src/silverstar_assert.c'],
}
report = []
for mode in ['pre', 'post']:
 for name, inputs in groups.items():
    sources = list(inputs)
    if mode == 'pre':
        old = build / (name + '_old.c')
        source = inputs[1 if name == 'telemetry' else 2].relative_to(root).as_posix()
        old.write_bytes(subprocess.check_output(['git', 'show', '10e0857:' + source], cwd=root))
        sources[1 if name == 'telemetry' else 2] = old
    exe = build / (name + '_' + mode + '.exe')
    cmd = base + [str(p) for p in sources] + ['-lm', '-o', str(exe)]
    c = subprocess.run(cmd, capture_output=True, text=True)
    (build / (name + '_' + mode + '_compile.log')).write_text(c.stdout+c.stderr)
    if c.returncode:
        print(name, mode, 'COMPILE FAIL', c.stderr[-3500:], flush=True)
        report.append(dict(name=name,mode=mode,command=cmd,compile_exit=c.returncode))
        continue
    r = subprocess.run([str(exe)], capture_output=True, text=True)
    (build / (name + '_' + mode + '_run.log')).write_text(r.stdout+r.stderr)
    report.append(dict(name=name,mode=mode,command=cmd,compile_exit=0,run_exit=r.returncode))
    print(name, mode, r.returncode, (r.stdout+r.stderr)[-2000:], flush=True)
(build / 'results.json').write_text(json.dumps(report, indent=2))
