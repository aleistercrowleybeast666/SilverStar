"""Exact reviewed provider/header inputs; no ELF/hardware acceptance claim."""
import json
from pathlib import Path
import pytest
from test_stack_budget import stacks

ROOT = Path(__file__).resolve().parents[3]
SOURCE = 'System/Src/system_imu_epoch.c'


def _Fixture(tmp_path):
    recorded = ROOT / '.work/sf6_epoch_v3/ret6'
    dependency = recorded / 'build/FCCG/SilverStar_F103RE/Release/System/Src/system_imu_epoch.d'
    text = dependency.read_text()
    names = text.split(':', 1)[1].replace('\\\n', ' ').split('\n', 1)[0].split()
    for name in set(names + [SOURCE]):
        target = tmp_path / name
        target.resolve().relative_to(tmp_path.resolve())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((recorded / name).read_bytes())
    build = tmp_path / 'build'
    target = build / Path(SOURCE).with_suffix('.d')
    target.parent.mkdir(parents=True)
    target.write_text(text)
    assert stacks.BindingSources_Verify(tmp_path, [SOURCE], build)
    return build


@pytest.mark.parametrize('path', [SOURCE, 'Interfaces/Inc/system_imu_epoch_if.h'])
def test_epoch_reviewed_input_mutation_rejected(tmp_path, path):
    build = _Fixture(tmp_path)
    target = tmp_path / path
    target.write_text(target.read_text() + '\n/* unreviewed complete-input mutation */\n')
    with pytest.raises(ValueError, match='Changed'):
        stacks.BindingSources_Verify(tmp_path, [SOURCE], build)


def test_epoch_unknown_dependency_rejected(tmp_path):
    build = _Fixture(tmp_path)
    target = build / Path(SOURCE).with_suffix('.d')
    text = target.read_text()
    colon = text.index(':')
    target.write_text(text[:colon + 1] + ' unknown.inc ' + text[colon + 1:])
    (tmp_path / 'unknown.inc').write_text('void Unreviewed_Input(void) {}\n')
    with pytest.raises(ValueError, match='Changed compiled callback dependency graph'):
        stacks.BindingSources_Verify(tmp_path, [SOURCE], build)
