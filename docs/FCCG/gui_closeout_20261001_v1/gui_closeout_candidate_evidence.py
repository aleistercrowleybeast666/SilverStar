import hashlib
import json
import pathlib
import shutil
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parents[1]
evidence = root/'docs/FCCG/gui_closeout_20261001_v1'
sys.path[:0] = [str(root/'apps/FCCG/src'), str(root/'apps/FCCG/tests')]
from silverstar_fccg.project.model import ProjectModel_Parse
from silverstar_fccg.project.power10_report import Power10Report_Create, Power10Report_Current_Is, Power10Report_Csv
from test_power_of_ten_checker_paths import checker_fixture

generated = root/'.work/SCG_Closeout_2175d95_v4'
model = ProjectModel_Parse(json.loads((generated/'SilverStar.ssproject').read_text(encoding='utf-8')))
for target, prefix in (('Flight_Controller', 'kf6'),):
    output = (evidence/(prefix+'_pot_v4.log')).read_text(encoding='utf-8', errors='replace')
    report = Power10Report_Create(generated/target, model, output, 0)
    assert Power10Report_Current_Is(generated/target, model, report)
    (evidence/(prefix+'_report_v4.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (evidence/(prefix+'_report_v4.csv')).write_text(Power10Report_Csv(report), encoding='utf-8-sig')
    print(prefix, len(report['functions']), len(report['findings']), report['critical_contract_review'])

source = 'apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_power_of_ten.ps1'
baseline = subprocess.check_output(['git', 'show', '2175d95:'+source], cwd=root)
probe_results = {}
for variant in ('baseline', 'current'):
    location = root/'apps/FCCG/.work/gui_closeout_v1'/('zero_evidence_'+variant)
    location.mkdir(parents=True, exist_ok=False)
    checker_fixture.__wrapped__(location)
    (location/'APP/fixture.c').write_text('int Fixture(int value)\n{\n    return value;\n}\n', encoding='utf-8')
    if variant == 'baseline':
        (location/'Tools/check_power_of_ten.ps1').write_bytes(baseline)
    command = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(location/'Tools/check_power_of_ten.ps1')]
    result = subprocess.run(command, cwd=location, capture_output=True)
    raw = result.stdout + result.stderr
    (evidence/('zero_'+variant+'_direct.log')).write_bytes(raw)
    probe_results[variant] = dict(command=command, cwd=str(location), exit_code=result.returncode,
        checker_sha256=hashlib.sha256((location/'Tools/check_power_of_ten.ps1').read_bytes()).hexdigest(),
        fixture_sha256=hashlib.sha256((location/'APP/fixture.c').read_bytes()).hexdigest(),
        log_sha256=hashlib.sha256(raw).hexdigest())
assert probe_results['baseline']['exit_code'] == 0
assert probe_results['current']['exit_code'] != 0
(evidence/'zero_before_after.json').write_text(json.dumps(probe_results, indent=2)+'\n', encoding='utf-8')
print('Direct baseline zero accepted; current zero rejected, identical source fixture.')
