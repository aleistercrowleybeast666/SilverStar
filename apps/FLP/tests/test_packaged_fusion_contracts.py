"""Contract validation must also work outside the monorepo source layout."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

import pytest

from silverstar_flp.decoder_profiles.contract_data import Contract_Load

APP = Path(__file__).resolve().parents[1]
PACKAGE = APP / 'src/silverstar_flp'
NAMES = ('navigation_v1.json', 'navigation_fusion_timing_records_v2.json', 'navigation_fusion_horizon_records_v1.json')


@pytest.mark.parametrize('name', NAMES)
def test_packaged_snapshot_is_exact_repository_authority(name):
    authoritative = APP.parents[1] / 'contracts' / name
    packaged = PACKAGE / 'decoder_profiles/contracts' / name
    assert packaged.read_bytes() == authoritative.read_bytes()
    assert Contract_Load(name) == json.loads(authoritative.read_text(encoding='utf-8'))


def test_relocated_minimal_package_imports_both_record_interpreters(tmp_path):
    document = tomllib.loads((APP / 'pyproject.toml').read_text(encoding='utf-8'))
    data_patterns = document['tool']['setuptools']['package-data']['silverstar_flp']
    target = tmp_path / 'isolated/silverstar_flp'
    decoder = target / 'decoder_profiles'
    decoder.mkdir(parents=True)
    for directory in (target, decoder):
        (directory / '__init__.py').write_text('', encoding='utf-8')
    for name in ('contract_data.py', 'errors.py', 'fusion_timing_records.py', 'fusion_horizon_records.py'):
        shutil.copyfile(PACKAGE / 'decoder_profiles' / name, decoder / name)
    for pattern in data_patterns:
        if not pattern.startswith('decoder_profiles/'):
            continue
        for source in PACKAGE.glob(pattern):
            destination = target / source.relative_to(PACKAGE)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    script = '''import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import silverstar_flp.decoder_profiles.fusion_timing_records as timing
import silverstar_flp.decoder_profiles.fusion_horizon_records as horizon
from silverstar_flp.decoder_profiles.contract_data import Contract_Load
assert Path(timing.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve())
assert len(timing.RECORDS) == 3 and len(horizon.RECORDS) == 2
assert horizon.RECORDS['FUSION_HORIZON_MEASUREMENT']['payload_size'] == 148
assert Contract_Load('navigation_v1.json')['eskf15']['component_id'] == 'silverstar.algorithm.estimator.eskf15'
'''
    subprocess.run([sys.executable, '-I', '-X', 'utf8', '-c', script, str(target.parent)],
        cwd=tmp_path, check=True, capture_output=True, text=True)


def test_resource_name_does_not_allow_external_or_decoder_paths():
    with pytest.raises(ValueError, match='unsupported_trusted_contract'):
        Contract_Load('../../contracts/other.json')
