from pathlib import Path
root=Path(__file__).parent
source=(root/'backend_probe.py').read_text(encoding='utf-8')
source=source.replace("'SF6_v6/Flight_Controller'", "'SF6_v7/Flight_Controller'")
source=source.replace("'backend_export.exe'", "'backend_export_v5.exe'")
source=source.replace("prefix='backend_export'", "prefix='backend_export_v5'")
source=source.replace("'SF6_ACTUAL_BACKEND_v1.BIN'", "'SF6_ACTUAL_BACKEND_v5.BIN'")
path=root/'backend_export_v5_driver.py';path.write_text(source,encoding='utf-8')
import subprocess,sys
raise SystemExit(subprocess.run([sys.executable,str(path),'--export']).returncode)
