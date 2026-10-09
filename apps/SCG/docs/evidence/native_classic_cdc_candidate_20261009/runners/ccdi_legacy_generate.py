from pathlib import Path
source=Path('D:/python_software/SilverStar/.work/scg_ground_integration_20261009/generate_v2.py').read_text(encoding='utf-8')
source=source.replace("REPO=BASE/'.work/qint'", "REPO=BASE/'.work/ccdi'")
source=source.replace("ssgroundint9e", "sscdc-legacy10a")
source=source.replace("TargetScope.ALL if name=='f103-usb' else TargetScope.GROUND", "TargetScope.GROUND")
exec(compile(source,'ccdi_legacy_generate_expanded','exec'))
