from pathlib import Path
source=Path('D:/python_software/SilverStar/.work/scg_ground_integration_20261009/run_gates.py').read_text(encoding='utf-8')
source=source.replace("OUT=ROOT/'.work/scg_ground_integration_20261009'", "OUT=ROOT/'.work/ccdi-evidence10a'")
source=source.replace("ssgroundint9e", "sscdc-legacy10a")
source=source.replace("cases += [('c071-usb',TARGETS/'c071-usb'),('c071-uart',TARGETS/'c071-uart')]", "")
source=source.replace("ROOT/'.work/qint'", "ROOT/'.work/ccdi'")
exec(compile(source,'ccdi_legacy_gates_expanded','exec'))
