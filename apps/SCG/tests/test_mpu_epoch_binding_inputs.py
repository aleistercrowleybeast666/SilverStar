"""Frozen normal-generated F103RE/RF inputs; no complete ELF/hardware claim."""
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest
from test_stack_budget import stacks

ROOT = Path(__file__).resolve().parents[3]
SOURCE = 'System/Src/system_imu_epoch.c'
FIXTURES = Path(__file__).parent / 'fixtures/mpu_epoch_binding_f103'


@pytest.fixture(params=('SilverStar_F103RE', 'SilverStar_F103RF'))
def recorded_inputs(request):
    name = 'inputs_ret6.json' if request.param == 'SilverStar_F103RE' else 'inputs.json'
    data = json.loads((FIXTURES / name).read_text(encoding='utf8'))
    assert data['target'] == request.param
    return data


def _Fixture(tmp_path, data):
    assert data['source'] == SOURCE
    text = data['dependency']
    names = text.split(':', 1)[1].replace('\\\n', ' ').split('\n', 1)[0].split()
    assert set(names + [SOURCE]) == set(data['inputs'])
    for name, entry in data['inputs'].items():
        target = tmp_path / name
        target.resolve().relative_to(tmp_path.resolve())
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = entry['text'].encode('utf8')
        assert hashlib.sha256(raw).hexdigest() == entry['sha256']
        target.write_bytes(raw)
    build = tmp_path / 'build'
    target = build / Path(SOURCE).with_suffix('.d')
    target.parent.mkdir(parents=True)
    target.write_text(text, encoding='utf8', newline='\n')
    assert stacks.BindingSources_Verify(tmp_path, [SOURCE], build) == data['proof']
    return build


def test_f103_exact_published_compiler_inputs_are_accepted(tmp_path, recorded_inputs):
    _Fixture(tmp_path, recorded_inputs)


@pytest.mark.parametrize('path', [SOURCE, 'Interfaces/Inc/system_imu_epoch_if.h'])
def test_epoch_reviewed_input_mutation_rejected(tmp_path, path, recorded_inputs):
    build = _Fixture(tmp_path, recorded_inputs)
    target = tmp_path / path
    target.write_text(target.read_text() + '\n/* unreviewed complete-input mutation */\n')
    with pytest.raises(ValueError, match='Changed'):
        stacks.BindingSources_Verify(tmp_path, [SOURCE], build)


def test_epoch_unknown_dependency_rejected(tmp_path, recorded_inputs):
    build = _Fixture(tmp_path, recorded_inputs)
    target = build / Path(SOURCE).with_suffix('.d')
    text = target.read_text()
    colon = text.index(':')
    target.write_text(text[:colon + 1] + ' unknown.inc ' + text[colon + 1:])
    (tmp_path / 'unknown.inc').write_text('void Unreviewed_Input(void) {}\n')
    with pytest.raises(ValueError, match='Changed compiled callback dependency graph'):
        stacks.BindingSources_Verify(tmp_path, [SOURCE], build)


def test_f103_current_unreviewed_generated_header_remains_rejected(tmp_path, recorded_inputs):
    build = _Fixture(tmp_path, recorded_inputs)
    header = recorded_inputs['current_generated_flight_header']
    raw = header['text'].encode('utf8')
    assert hashlib.sha256(raw).hexdigest() == header['sha256']
    (tmp_path / 'Generated/Inc/project_flight_config.h').write_bytes(raw)
    with pytest.raises(ValueError, match='Changed or missing reviewed callback compilation input'):
        stacks.BindingSources_Verify(tmp_path, [SOURCE], build)


def test_f103_inputs_reproduce_from_preserved_project_and_production_generation(tmp_path, recorded_inputs):
    script = ROOT / 'apps/SCG/tools/validation/mpu_epoch_binding_fixture.py'
    spec = importlib.util.spec_from_file_location('epoch_fixture_reproducer', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reproduced = module.Fixture_Reproduce(tmp_path / 'compile', 'arm-none-eabi-gcc', recorded_inputs['target'])
    frozen = recorded_inputs
    assert reproduced['inputs'] == frozen['inputs']
    assert reproduced['dependency'] == frozen['dependency']
    assert reproduced['proof'] == frozen['proof']
    assert reproduced['preprocessed_epoch_tokens_equal']
    assert reproduced['current_generated_header_rejected']
