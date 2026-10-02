from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
template = (ROOT / '.work/SF6_20261001_v1/backend_probe.py').read_text(encoding='utf-8')
template = template.replace("P=OUT/'SF6_v6/Flight_Controller'", "P=OUT/'SF6_auto_v1/Flight_Controller'")
template = template.replace("OWNER=ROOT/'apps/FCCG/plugins/builtin/silverstar_algorithm_estimator_sf6/payload'", "OWNER=P")
template = template.replace("'backend_export.exe'", "'backend_export_integrated.exe'")
template = template.replace("prefix='backend_export'", "prefix='backend_export_integrated'")
template = template.replace("'SF6_ACTUAL_BACKEND_v1.BIN'", "'SF6_AUTO_ACTUAL_BACKEND_v2.BIN'")
template = template.replace("'-DSYSTEM_BUILD_ESTIMATOR_ENABLED=0U'", "'-DSYSTEM_BUILD_ESTIMATOR_ENABLED=0U','-DSILVERSTAR_MEMORY_LAYOUT_AUTO=1'")
driver = OUT / 'backend_export_integrated_driver.py'
driver.write_text(template, encoding='utf-8')
wrong_fixture = OUT / 'KF6_v6'
wrong_fixture.mkdir(exist_ok=False)
packages = list((OUT / 'KF6_auto_v1').glob('*.ssdecoder'))
assert len(packages) == 1
shutil.copy2(packages[0], wrong_fixture / packages[0].name)
raise SystemExit(subprocess.run([sys.executable, str(driver), '--export']).returncode)
