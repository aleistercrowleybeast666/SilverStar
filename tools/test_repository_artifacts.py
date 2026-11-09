"""Real Git index cases for the changed-artifact guard."""
import json
from pathlib import Path
import subprocess
import sys

SCRIPT = Path(__file__).with_name('check_repository_artifacts.py')


def Git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True, check=True)


def Check(root, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=root,
                          capture_output=True, text=True)


def test_changed_blobs_preserve_historical_products_but_reject_new_ones(tmp_path):
    Git(tmp_path, 'init')
    (tmp_path / 'historical.zip').write_bytes(b'x' * (3 * 1024 * 1024))
    Git(tmp_path, 'add', '.')
    Git(tmp_path, '-c', 'user.name=Artifact test', '-c', 'user.email=test@example.invalid',
        'commit', '-m', 'Existing history')
    base = Git(tmp_path, 'rev-parse', 'HEAD').stdout.decode().strip()
    source = tmp_path / 'apps/SCG/src/silverstar_fccg/build/runner.py'
    source.parent.mkdir(parents=True)
    source.write_text('SOURCE = True\n', encoding='utf8')
    Git(tmp_path, 'add', '.')
    assert Check(tmp_path, '--staged').returncode == 0
    Git(tmp_path, '-c', 'user.name=Artifact test', '-c', 'user.email=test@example.invalid',
        'commit', '-m', 'Only source changed')
    assert Check(tmp_path, '--base', base).returncode == 0
    (tmp_path / 'accidental.txt').write_bytes(b'x' * (3 * 1024 * 1024))
    Git(tmp_path, 'add', '.')
    result = Check(tmp_path, '--staged')
    assert result.returncode == 1 and 'accidental.txt' in result.stdout
    assert 'historical.zip' not in result.stdout


def test_fixture_exception_does_not_exempt_workspace_or_size(tmp_path):
    Git(tmp_path, 'init')
    (tmp_path / 'tools').mkdir()
    (tmp_path / 'tools/repository_artifacts.json').write_text(json.dumps([
        {'path': 'tests/fixtures/*', 'reason': 'Small recorded format regression input'}]), encoding='utf8')
    fixture = tmp_path / 'tests/fixtures/tiny.bin'
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(b'format-test')
    Git(tmp_path, 'add', '.')
    assert Check(tmp_path, '--staged').returncode == 0
    cache = fixture.parent / '.work/run.bin'
    cache.parent.mkdir()
    cache.write_bytes(b'generated')
    Git(tmp_path, 'add', '.')
    result = Check(tmp_path, '--staged')
    assert result.returncode == 1 and 'temporary workspace' in result.stdout
    fixture.write_bytes(b'x' * (3 * 1024 * 1024))
    Git(tmp_path, 'add', '.')
    assert 'blob exceeds' in Check(tmp_path, '--staged').stdout
