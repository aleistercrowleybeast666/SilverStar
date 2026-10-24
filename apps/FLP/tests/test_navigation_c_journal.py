"""Compile current C replay/journal and consume its bytes through exact LogOpen."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.replay_execution import Replay_Execute
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest, ReplayFidelity
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.plugins.algorithms.navigation_reference_v1.recorded_journal import (
    RecordedJournal_Read, RecordedJournal_Execute)
from tests.synthetic_parameter_navigation import NavigationPair_Open

ROOT = Path(__file__).resolve().parents[3]
OWNER = ROOT / 'apps/SCG/plugins/builtin/silverstar_algorithm_augmented_common/payload/Algorithm/Estimator/Augmented'
FIXTURE = ROOT / 'apps/SCG/tests/fixtures/navigation_augmented_host'
MODELS = ('eskf20', 'inekf15', 'inekf20')


@pytest.fixture(scope='module', params=('O0', 'O2'))
def executable(request, tmp_path_factory):
    directory = tmp_path_factory.mktemp('cjournal-' + request.param)
    compiler = shutil.which('gcc')
    assert compiler, 'Host GCC required for current-source journal checks'
    sources = [OWNER / 'Src' / (name + '.c') for name in (
        'navigation_bounded', 'navigation_input', 'navigation_session', 'navigation_replay',
        'navigation_journal', 'navigation_mag_quality')]
    sources.append(FIXTURE / 'replay_journal.c')
    target = directory / ('journal.exe' if sys.platform == 'win32' else 'journal')
    command = [compiler, '-std=c11', '-' + request.param, '-Wall', '-Wextra', '-Werror', '-pedantic',
        '-I' + str(FIXTURE), '-I' + str(OWNER / 'Inc'),
        '-I' + str(ROOT / 'apps/SCG/plugins/builtin/silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG/Inc'),
        *map(str, sources), '-lm', '-o', str(target)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    (directory / 'build.json').write_text(json.dumps({'command': command,
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}, indent=2), encoding='utf-8')
    return target


def Parameters_Create(model):
    fixture = Path(__file__).parent / 'fixtures/navigation_augmented_actual_parameters_v1.json'
    group = copy.deepcopy(json.loads(fixture.read_text(encoding='utf-8'))['models'][model])
    for row in group['parameters']:
        name = row['id']
        if name.startswith('initial_variance_'):
            row['value'] = 0.25
        elif name.startswith(('initial_gyro_bias_', 'initial_accel_bias_')):
            row['value'] = 0.0
        elif '_density_' in name:
            row['value'] = float(np.float32(0.001))
        elif name in ('inclination_rad', 'declination_rad'):
            row['value'] = 0.0
        elif name.startswith('installation_q_'):
            row['value'] = 1.0 if name.endswith('_0') else 0.0
        elif name == 'position_nis_gate':
            row['value'] = 1000.0
    return group


@pytest.mark.parametrize('model', MODELS)
def test_current_c_replay_journal_exact_open_and_full_covariance(executable, tmp_path, model):
    output = tmp_path / 'journal.jsonl'
    run = subprocess.run([str(executable), str(MODELS.index(model)+1), str(output)], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    rows = [json.loads(line) for line in output.read_text(encoding='utf-8').splitlines()]
    assert rows[0]['quality'] == {'boundary_checks': 8, 'hardware_qualified': False}
    parts, final = [row for row in rows if 'record' in row], rows[-1]['final']
    opened = NavigationPair_Open(tmp_path / 'pair', flight_samples=15,
        journal_rows=parts, augmented_parameters=Parameters_Create(model))
    before = opened.dataset.source_path.read_bytes()
    journal = RecordedJournal_Read(opened.dataset, model)
    times, states, outcomes = RecordedJournal_Execute(journal, TaskContext())
    state = states[-1]
    position = state.position if model == 'eskf20' else state.group[:3, 4]
    velocity = state.velocity if model == 'eskf20' else state.group[:3, 3]
    rotation = state.rotation if model == 'eskf20' else state.group[:3, :3]
    np.testing.assert_allclose(position, final['position'], atol=2e-11, rtol=2e-11)
    np.testing.assert_allclose(velocity, final['velocity'], atol=2e-11, rtol=2e-11)
    np.testing.assert_allclose(rotation.ravel(), final['rotation'], atol=2e-11, rtol=2e-11)
    np.testing.assert_allclose(state.covariance.ravel(), final['covariance'], atol=2e-11, rtol=2e-11)
    assert times[-1] == 1020002 and any(row.get('result') == 6 for row in outcomes)
    plugin = builtin_registry().Algorithm_Get('silverstar.algorithm.estimator.' + model)
    result = Replay_Execute(plugin, opened.dataset,
        ReplayRequest(mode=ReplayMode.RECORDED_CONFIGURATION, input_source='navigation_journal'))
    assert result.fidelity == ReplayFidelity.APPROXIMATE
    assert result.diagnostics['firmware_equivalence'] == 'NOT_PROVEN'
    assert opened.dataset.source_path.read_bytes() == before
    for label, changed in (
        ('crc', copy.deepcopy(parts)), ('unsealed', [r for r in parts if r['record']['kind'] != 3]),
        ('missing_part', parts[1:]),
    ):
        if label == 'crc':
            changed[0]['record']['data'][0] ^= 1
        bad = NavigationPair_Open(tmp_path / label, flight_samples=15,
            journal_rows=changed, augmented_parameters=Parameters_Create(model))
        with pytest.raises(ValueError, match='navigation_journal_'):
            RecordedJournal_Read(bad.dataset, model)
