from pathlib import Path
import ctypes, datetime, hashlib, json, os, re, shlex, subprocess, sys, time

r = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(r / 'apps/FCCG/src'))
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.model import ProjectModel_Load
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope

ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
o = r / 'docs/FCCG/pot_rule5_utf8_gate_20261001_v2'
o.mkdir(exist_ok=True)
work = r / '.work/Rule5UTF8_9065ae0_20261001_v2'
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
snapshot_paths = [owner, r/'apps/FCCG/tests/test_jy901b_boundary_host.py', r/'apps/FCCG/tests/fixtures/jy901b_boundary_host.c', core/'Tools/check_power_of_ten.ps1', core/'Common/Inc/silverstar_assert.h', r/'apps/FCCG/tests/test_power_of_ten_checker_paths.py', r/'AGENTS.md', r/'docs/FCCG/platform/details/CODING_STANDARD.md']
snapshot = {str(p.relative_to(r)): hashlib.sha256(p.read_bytes()).hexdigest() for p in snapshot_paths}
make = 'D:/msys64/ucrt64/bin/mingw32-make.exe'
arm = Path('D:/Arm GNU Toolchain/14.3 rel1/bin')
env = os.environ.copy()
env['PATH'] = str(arm) + ';D:/msys64/ucrt64/bin;' + env['PATH']
record = {'head': head, 'dirty_before_checks': dirty, 'source_sha256': snapshot,
          'timestamp_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'results': [], 'limitations': ['Synthetic host fixtures are not hardware validation',
          'Rule 5 uses separate target average >=2 after user 06:31 UTC revision; syntactic eligibility is not semantic certification', 'Task/library/MSP/ISR stack bounds require separate proof'],
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

dest = work/'after'
model = ProjectModel_Load(source)
TargetGeneration_Apply(model, catalog, WorkspacePolicy(r/'apps/FCCG'), dest, TargetScope.ALL)
record['configuration_sha256'] = hashlib.sha256((dest/'SilverStar.ssproject').read_bytes()).hexdigest()
record['checker_sha256'] = hashlib.sha256((dest/'Flight_Controller/Tools/check_power_of_ten.ps1').read_bytes()).hexdigest()
assert record['checker_sha256'] == hashlib.sha256((core/'Tools/check_power_of_ten.ps1').read_bytes()).hexdigest()
reference = r/'.work/JyRule5Average_9065ae0_20261001_v1/after'
def firmware_tree(base):
    return {p.relative_to(base).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in base.rglob('*') if p.is_file() and p.suffix in ('.c','.h','.ld') and 'build' not in p.relative_to(base).parts}
current = firmware_tree(dest)
previous = firmware_tree(reference)
record['firmware_source_tree_sha256'] = current
record['firmware_reference_record'] = 'docs/FCCG/pot_jy_rule5_average_batch_20261001_v1/result.json'
record['firmware_tree_identical_to_reference'] = current == previous
save()
assert current == previous, [key for key in current.keys()|previous.keys() if current.get(key)!=previous.get(key)]
for kind,target in [('flight','Flight_Controller'),('ground','Ground_Station')]:
    run('after_'+kind+'_power10',[make,'CONFIG=Release','power10-check'],dest/target)
run('after_pytest',[sys.executable,'-m','pytest','apps/FCCG/tests/test_jy901b_boundary_host.py','apps/FCCG/tests/test_source_selector_contract_host.py','apps/FCCG/tests/test_device_startup_fsm.py','apps/FCCG/tests/test_neo_m9n_startup.py','apps/FCCG/tests/test_jy901b_startup.py','apps/FCCG/tests/test_power_of_ten_checker_paths.py','-q','--basetemp='+str(work/'pytest'),'-o','cache_dir='+str(work/'pytest_cache')])
run('after_flight_architecture',[make,'CONFIG=Release','architecture-check'],dest/'Flight_Controller')
record['scope_note'] = 'Checker-only UTF8 coverage correction. Full firmware host/ARM/analyzer runs belong to the referenced completed v1 snapshot; exact .c/.h/.ld tree hashes match. No composite full-suite run is claimed.'
assert all(hashlib.sha256((r/path).read_bytes()).hexdigest() == digest for path,digest in snapshot.items())
record['completed_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat();save()
print('COMPLETE',flush=True)
