"""Rebuild explicitly synthetic legacy-field fixtures from fixed provenance."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
source = HERE.parent / 'radio_handshake.ssproject'
original = json.loads(source.read_text(encoding='utf-8'))
base = {key: deepcopy(original[key]) for key in (
    'project', 'components', 'modes', 'mode_parameters',
    'hardware', 'resources', 'capability_sources', 'logging', 'build',
    'generated_glue', 'reference_provenance', 'component_provenance', 'log_decoder_profile')}
base['generated_glue'].remove('project_algorithm_parameters')
base['components']['strategies']['alignment'] = 'silverstar.algorithm.alignment.gravity_known_yaw'
base['components']['protocol_bundles'] = ['silverstar.protocol.reference_v0']
base['protocol_profiles'] = {'telemetry': 'air.compact.v0',
    'maintenance': 'maintenance.v0_0', 'logging': 'sslog0'}
for key in ('cubemx_version', 'firmware_package', 'hal_cmsis_source_policy', 'i2c_external_pullup_confirmations'):
    base['hardware'].pop(key, None)
for version in range(2, 8):
    data = deepcopy(base)
    data['format_version'] = version
    data['project']['name'] = 'MigrateV' + str(version)
    if version < 7:
        data.pop('log_decoder_profile')
        data['generated_glue'].remove('project_log_decoder_profile')
    if version < 6:
        data.pop('mode_parameters')
        data.pop('protocol_profiles')
        data['hardware'].pop('assignment_fingerprint')
        data['generated_glue'].remove('project_flight_config')
    if version == 4:
        data['capability_selections'] = {'imu0': ['magnetometer.field']}
        data['build']['configuration'] = 'Release'
    if version == 2:
        devices = data['components']['devices']
        owners = {row['instance_id']: row['plugin'] for row in devices}
        data['components']['devices'] = [row['plugin'] for row in devices]
        data['resources'] = {owners.get(key.partition(':')[0], key.partition(':')[0]) + ':' + key.partition(':')[2]: value
                             for key, value in data['resources'].items()}
        data.pop('capability_sources')
        data['generated_glue'].remove('project_capability_routes')
    (HERE / f'v{version}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
# Format 12 introduced explicit algorithm parameters but predates link/Ground.
v12 = deepcopy(original)
for key in ('alignment', 'air_link', 'ground_target', 'flight_tx_power_dbm'):
    v12.pop(key)
v12['format_version'] = 12
v12['components']['strategies']['alignment'] = 'silverstar.algorithm.alignment.gravity_mag_triad'
(HERE / 'v12.json').write_text(json.dumps(v12, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
commit = subprocess.check_output(['git', 'rev-parse', '2763bb8f'], cwd=REPO, text=True).strip()
model = subprocess.check_output(['git', 'show', commit + ':apps/FCCG/src/silverstar_fccg/project/model.py'], cwd=REPO)
(HERE / 'provenance.json').write_text(json.dumps(dict(
    scope='synthetic legacy field projection; explicit identity boundary retained, not historical hardware data',
    schema_source_commit=commit, model_sha256=hashlib.sha256(model).hexdigest(),
    base_fixture=str(source.relative_to(REPO)), base_fixture_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    fixtures={path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(HERE.glob('v*.json'))}
), indent=2) + '\n', encoding='utf-8')
