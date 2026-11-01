"""Retain exact compiler inputs, accepting reconstructed bytes only by recorded SHA.

The old engine is obtained from the recorded Git baseline, not reimplemented.
Test-harness reconstruction removes only the later window/termination additions;
the pre-fix compiler receipt must match byte-for-byte before retention.
"""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[4]
BASELINE = '8b028f280ba01dce0efc697479ef99ec143f7456'
TEMP = ROOT / '.work/0.1.3-software-completion-20261101/critical'
OUT = Path(__file__).resolve().parent / 'compiler-inputs'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def variants(data):
    normalized = data.replace(b'\r\n', b'\n')
    return [data, normalized, normalized.replace(b'\n', b'\r\n')]

fixture = ROOT / 'apps/SCG/tests/fixtures/mission_critical_contract_host.c'
old_fixture = fixture.read_text(encoding='utf8')
old_fixture = old_fixture.replace('static uint8_t s_function_error;\n', '')
old_fixture = old_fixture.replace('static SystemMissionFunctionConfig s_control = {2U, 1U, 5U, 0U, 8U};\n', '')
old_fixture = old_fixture.replace(
    '    if ((index >= 5U) || (config == NULL) || (s_function_error != 0U))\n'
    '    { return SystemMissionProcessResult_Invalid; }',
    '    if ((index >= 5U) || (config == NULL)) { return SystemMissionProcessResult_Invalid; }')
old_fixture = old_fixture.replace('    if (index == 4U) { *config = s_control; }\n', '')
old_fixture = old_fixture.replace(
    '        assert(SystemMissionProcess_ControlWindowGet() == SystemMissionControlWindowResult_Disabled);\n', '')
start = old_fixture.index('static int MissionReview_ControlWindow(void)')
end = old_fixture.index('int main(int argc, char **argv)', start)
old_fixture = old_fixture[:start] + old_fixture[end:]
old_fixture = old_fixture.replace('    if (strcmp(mode, "window") == 0) { return MissionReview_ControlWindow(); }\n', '')
old_fixture = old_fixture.replace('    if (strcmp(mode, "termination-config-error") == 0) { return MissionReview_TerminateConfigError(); }\n', '')
old_fixture = old_fixture.replace('    else if (strcmp(mode, "window-count") == 0) { s_process.entered = 255U; }\n', '')
old_fixture = old_fixture.replace('        else if (strcmp(mode, "window-count") == 0)\n'
                                  '        { (void)SystemMissionProcess_ControlWindowGet(); }\n', '')

core = ROOT / 'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload'
engine = core / 'System/Src/system_mission_process.c'
before_termination = engine.read_text(encoding='utf8').replace(
    '    if (s_process.entered < PROJECT_MISSION_STAGE_COUNT)\n'
    '    {\n'
    '        if (ProjectMissionStage_ConfigGet(s_process.entered, &stage) != SystemMissionProcessResult_Entered)\n'
    '        { result = SystemMissionProcessResult_Invalid; }\n'
    '        else if ((stage.signal == 0U) && ((input->events & stage.event_mask) != 0U))\n'
    '        { result = SystemMissionProcess_Transition(input, &stage); }\n'
    '    }',
    '    if ((s_process.entered < PROJECT_MISSION_STAGE_COUNT) &&\n'
    '        (ProjectMissionStage_ConfigGet(s_process.entered, &stage) == SystemMissionProcessResult_Entered) &&\n'
    '        (stage.signal == 0U) && ((input->events & stage.event_mask) != 0U))\n'
    '    { result = SystemMissionProcess_Transition(input, &stage); }')

extra = variants(old_fixture.encode()) + variants(before_termination.encode())
records = []
for run in ('pre-mission-v3', 'pre-runtime-v2', 'pre-termination', 'post-mission-v3',
            'post-combined-v2'):
    for receipt in sorted((TEMP / run).glob('*/compiler-receipt.json')):
        value = json.loads(receipt.read_text(encoding='utf8'))
        name = run + '-' + receipt.parent.name
        retained = {}
        for source, expected in value['sources'].items():
            path = Path(source)
            candidates = list(extra)
            if path.exists():
                candidates.extend(variants(path.read_bytes()))
            relative = path.relative_to(ROOT).as_posix()
            git = subprocess.run(['git', 'show', BASELINE + ':' + relative],
                                 cwd=ROOT, capture_output=True, check=False)
            if git.returncode == 0:
                candidates.extend(variants(git.stdout))
            matching = next((data for data in candidates if digest(data) == expected), None)
            if matching is None:
                raise RuntimeError(f'Exact input not recovered: {name}: {relative}: {expected}')
            target = OUT / 'objects' / (expected + path.suffix)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != matching:
                raise RuntimeError('Refuse to replace retained evidence')
            target.write_bytes(matching)
            retained[relative] = target.relative_to(OUT).as_posix()
        destination = OUT / (name + '.json')
        destination.write_bytes(receipt.read_bytes())
        binary = next(receipt.parent.glob('*.exe'))
        records.append({'run': run, 'receipt': destination.name, 'input_objects': retained,
                        'executable_sha256': digest(binary.read_bytes()),
                        'executable_bytes': binary.stat().st_size})
(OUT / 'index.json').write_text(json.dumps(records, indent=2), encoding='utf8')
print(json.dumps({'retained_compilations': len(records), 'baseline': BASELINE}))
