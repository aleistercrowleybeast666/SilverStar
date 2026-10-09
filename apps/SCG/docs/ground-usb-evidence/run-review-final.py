from pathlib import Path
import os, subprocess, sys
root = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path(__file__).resolve().parent
repo = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else root.parent / 'ground-usb-worktree'
env = os.environ.copy()
env['PYTHONIOENCODING'] = 'utf-8'
env['PYTHONPATH'] = str(repo / 'apps/SCG/src')
env['PATH'] = 'D:/Arm GNU Toolchain/14.3 rel1/bin;D:/msys64/ucrt64/bin;' + env['PATH']
def run(command, cwd, log):
    with (root / log).open('w', encoding='utf8') as stream:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT)
    print(log, 'exit', result.returncode, flush=True)
    if result.returncode: raise SystemExit(result.returncode)
if sys.argv[1] == 'build':
    run([sys.executable, '-B', str(root/'generate-ground.py')], repo, 'generation-review-final-macros.log')
    for case in ('f103-usb', 'f103-uart', 'f407-usb'):
        run(['D:/msys64/ucrt64/bin/mingw32-make.exe', '-B', '-j2', 'all', 'architecture-check', 'host-tests', 'artifact-check', 'power10-check', 'static-analysis'], root/('generated-'+case)/'Ground_Station', case+'-review-final-macros.log')
else:
    tests = repo/'apps/SCG/tests'
    paths = sorted({*tests.glob('test_ground_*.py'), *tests.glob('test_f103_ground*.py'), *tests.glob('test_cubemx*.py'), tests/'test_round2_targets.py'})
    gui_files = {'test_ground_board_recovery.py', 'test_ground_radio_editor.py', 'test_ground_activity_configuration.py'}
    paths = [str(path) for path in paths if path.is_file() and path.name not in gui_files]
    run([sys.executable, '-B', '-m', 'pytest', *paths, '-q', '-k', 'not test_one_bmi088_plugin_resolves_mixed_interfaces_without_duplicate_sources', '--basetemp=C:/Users/chdxm/AppData/Local/Temp/usbfinalbackend9', '-o', 'cache_dir='+str(root/'pytest-cache-final')], repo, 'review-regressions-backend-final.log')
