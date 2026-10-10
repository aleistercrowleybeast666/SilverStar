from pathlib import Path
source=Path('D:/python_software/SilverStar/.work/ccdi_legacy_gates.py').read_text(encoding='utf-8')
source=source.replace('ccdi-evidence10a','ccdi-evidence10b').replace('sscdc-legacy10a','sscdc-legacy10b')
exec(compile(source,'ccdi_legacy_gates10b','exec'))
