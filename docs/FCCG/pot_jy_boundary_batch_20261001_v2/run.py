from pathlib import Path
import ctypes, datetime, hashlib, json, os, re, shlex, subprocess, sys, time

r = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(r / 'apps/FCCG/src'))
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.model import ProjectModel_Load
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope

ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
o = r / 'docs/FCCG/pot_jy_boundary_batch_20261001_v2'
o.mkdir(exist_ok=True)
work = r / '.work/JyBoundarySafety_9065ae0_20261001_v2'
assert not work.exists(), work
work.mkdir()
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=r, text=True).strip()
dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=r, text=True)
core = r / 'apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload'
jy = r / 'apps/FCCG/plugins/builtin/silverstar_device_imu_jy901b/payload/Devices/IMU/JY901B'
owner = jy / 'Src/jy901b_device.c'
owner_relative = owner.relative_to(r).as_posix()
(o / 'source_snapshot.diff').write_bytes(subprocess.check_output(['git', 'diff', '--binary'], cwd=r))
untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=r, text=True).splitlines()
snapshot = {str(p.relative_to(r)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [owner, r/'apps/FCCG/tests/test_jy901b_boundary_host.py', r/'apps/FCCG/tests/fixtures/jy901b_boundary_host.c']}
make = 'D:/msys64/ucrt64/bin/mingw32-make.exe'
arm = Path('D:/Arm GNU Toolchain/14.3 rel1/bin')
env = os.environ.copy()
env['PATH'] = str(arm) + ';D:/msys64/ucrt64/bin;' + env['PATH']
record = {'head': head, 'dirty_before_checks': dirty, 'source_sha256': snapshot,
          'timestamp_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'results': [], 'limitations': ['Synthetic host fixtures are not hardware validation',
          'Flight strict PoT remains FAIL', 'Task/library/MSP/ISR stack bounds require separate proof'],
          'tools': {name: subprocess.check_output(command, text=True, env=env)
                    for name, command in [('arm', [str(arm/'arm-none-eabi-gcc.exe'), '--version']),
                                          ('host', ['gcc', '--version']), ('make', [make, '--version']),
                                          ('python', [sys.executable, '--version'])]}}
def save():
    (o/'result.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
def run(name, command, cwd=r, timeout=1800):
    print('BEGIN', name, flush=True)
    log = o / (name + '.log')
    started = time.monotonic()
    with log.open('w', encoding='utf-8') as f:
        p = subprocess.Popen(command, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT)
        record['running'] = {'name': name, 'pid': p.pid}; save()
        try: code = p.wait(timeout)
        except subprocess.TimeoutExpired:
            p.terminate(); code = p.wait(15)
            record['timeout'] = name
    record.pop('running', None)
    record['results'].append({'name': name, 'command': command, 'cwd': str(cwd),
                             'exit_code': code, 'seconds': time.monotonic()-started,
                             'log': str(log.relative_to(r)), 'sha256': hashlib.sha256(log.read_bytes()).hexdigest()})
    save(); print('DONE', name, code, flush=True)
    return code

catalog = PluginCatalog(r/'apps/FCCG/plugins/builtin', r/'apps/FCCG/plugins/installed'); catalog.Scan()
source = r/'.work/SelectorSafety_70ce20d_20261001_v1/after/SilverStar.ssproject'
record['input_configuration'] = str(source)
record['input_configuration_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
for stage in ['baseline', 'after']:
    dest = work/stage
    model = ProjectModel_Load(source)
    TargetGeneration_Apply(model, catalog, WorkspacePolicy(r/'apps/FCCG'), dest, TargetScope.ALL)
    assert not list(dest.rglob('*.elf'))
    flight = dest/'Flight_Controller'; ground = dest/'Ground_Station'
    if stage == 'baseline':
        (flight/'Devices/IMU/JY901B/Src/jy901b_device.c').write_bytes(subprocess.check_output(['git', 'show', head+':'+owner_relative], cwd=r))
    else:
        assert (flight/'Devices/IMU/JY901B/Src/jy901b_device.c').read_bytes() == owner.read_bytes()
    record[stage+'_configuration_sha256'] = hashlib.sha256((dest/'SilverStar.ssproject').read_bytes()).hexdigest()
    record[stage+'_checker_sha256'] = hashlib.sha256((flight/'Tools/check_power_of_ten.ps1').read_bytes()).hexdigest()
    run(stage+'_flight_power10', [make, 'CONFIG=Release', 'power10-check'], flight)
    run(stage+'_ground_power10', [make, 'power10-check'], ground)
    if stage == 'baseline':
        fixture = core/'Tests/Host/Fixtures/MultiInstance'
        includes = [flight/'Devices/IMU/JY901B/Src', fixture/'Inc',
                    r/'apps/FCCG/plugins/builtin/silverstar_platform_api/payload/Platform/Inc',
                    core/'System/Inc', core/'Interfaces/Inc', core/'Common/Inc',
                    core/'Tests/Host', jy/'Inc', jy/'Adapter/Inc']
        cmd = ['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic']
        for path in includes: cmd += ['-I', str(path)]
        exe = work/'baseline_boundary.exe'
        cmd += [str(core/'Tests/Host/host_platform_mock.c'),str(fixture/'multi_instance_resources.c'),
                str(core/'Common/Src/silverstar_assert.c'),str(r/'apps/FCCG/tests/fixtures/jy901b_boundary_host.c'), '-lm', '-o', str(exe)]
        assert run('baseline_boundary_compile', cmd) == 0
        cases = [('time',s) for s in ['normal','cross_ms','no_frame','timeout','wrap_to_zero','wrap_elapsed']]
        cases += [('readback',s) for s in ['only_quat','missing_acc','missing_gyro','missing_pressure','missing_quat','complete','complete_extra','already_complete']]
        cases += [('receive',s) for s in ['normal','stop_fail','restart_fail','tx_fail','tx_fail_restart_fail','baud_normal','baud_stop_fail','baud_restart_fail']]
        for group, case in cases: run('baseline_boundary_'+group+'_'+case, [str(exe), group, case])
        continue
    run('after_pytest', [sys.executable, '-m', 'pytest', 'apps/FCCG/tests/test_jy901b_boundary_host.py', 'apps/FCCG/tests/test_source_selector_contract_host.py',
        'apps/FCCG/tests/test_device_startup_fsm.py', 'apps/FCCG/tests/test_neo_m9n_startup.py',
        'apps/FCCG/tests/test_jy901b_startup.py', 'apps/FCCG/tests/test_power_of_ten_checker_paths.py',
        '-q', '--basetemp='+str(work/'pytest'), '-o', 'cache_dir='+str(work/'pytest_cache')])
    run('after_ground_arm', [make, '-j2', 'all'], ground)
    run('after_flight_arm', [make, '-j2', 'CONFIG=Release', 'GCC_PATH='+arm.as_posix(), 'all'], flight)
    run('after_flight_host', [make, 'CONFIG=Release', 'HOST_CC=D:/msys64/ucrt64/bin/gcc.exe', 'host-tests'], flight)
    run('after_flight_static', [make, '-j2', 'CONFIG=Release', 'GCC_PATH='+arm.as_posix(), 'static-analysis'], flight)
    analysis = work/'analyzer'; analysis.mkdir()
    canary = analysis/'double_free.c'
    canary.write_text('#include <stdlib.h>\nvoid Test_Analyzer(int flag) { void *p=malloc(4); if(flag!=0) free(p); free(p); }\n')
    run('analyzer_negative', [str(arm/'arm-none-eabi-gcc.exe'), '-std=c11', '-fanalyzer', '-Werror=analyzer-double-free', '-c', str(canary), '-o', str(analysis/'negative.o')])
    text = (ground/'Makefile').read_text().replace('\\\n', ' ')
    graph = json.loads((ground/'Generated/ground_source_graph.json').read_text())
    def flags(key): return shlex.split(re.search(r'(?m)^'+key+r' := ([^\n]+)', text).group(1))
    sources = [s for s in graph['sources'] if s.startswith(('Common/', 'Devices/', 'Generated/', 'Ground/', 'Platform/'))]
    for i, file in enumerate(sources):
        run('after_ground_analyze_'+str(i), [str(arm/'arm-none-eabi-gcc.exe'), *flags('CFLAGS'), *flags('FIRST_PARTY_WARNINGS'), '-fanalyzer', '-c', file, '-o', str(analysis/('ground_'+str(i)+'.o'))], ground)
    run('after_flight_architecture', [make, 'CONFIG=Release', 'architecture-check'], flight)
    run('after_flight_artifact', [make, 'CONFIG=Release', 'GCC_PATH='+arm.as_posix(), 'artifact-check'], flight)
    run('after_flight_stack', [make, 'CONFIG=Release', 'GCC_PATH='+arm.as_posix(), 'stack-report'], flight)
    run('after_flight_sources', [make, 'list-sources'], flight)
    record['artifacts'] = [{'file': str(p.relative_to(r)), 'bytes': p.stat().st_size,
        'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in dest.rglob('*')
        if p.is_file() and p.suffix in ['.elf', '.map', '.bin', '.hex', '.ssdecoder']]
    record['after_source_graph_sha256'] = hashlib.sha256((flight/'Generated/source_graph.json').read_bytes()).hexdigest() if (flight/'Generated/source_graph.json').exists() else None
    save()
assert record['baseline_checker_sha256'] == record['after_checker_sha256']
assert all(hashlib.sha256((r/path).read_bytes()).hexdigest() == digest for path,digest in snapshot.items())
record['completed_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat(); save()
print('COMPLETE', flush=True)
