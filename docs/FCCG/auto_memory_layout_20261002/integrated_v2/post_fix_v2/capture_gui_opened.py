from pathlib import Path

OUT = Path(__file__).parent
source = (OUT / 'capture_gui.py').read_text(encoding='utf-8')
source = source.replace("dest = OUT / 'GUI'", "dest = OUT / 'GUI_Opened'")
source = source.replace("window._model = service.Project_Open(OUT / (name + '_auto_v1'))\n            window._Project_Refresh()", "window._Project_Open(OUT / (name + '_auto_v1'))\n            assert window._project_root == (OUT / (name + '_auto_v1')).resolve()")
source = source.replace("'image': label + '.png'", "'image': label + '.png', 'project_open_method': 'MainWindow._Project_Open', 'project_root': str(window._project_root), 'flight_status': window.build_page.target_status_labels['flight'].text()")
driver = OUT / 'capture_gui_opened_driver.py'
driver.write_text(source, encoding='utf-8')
import subprocess
import sys
raise SystemExit(subprocess.run([sys.executable, str(driver)]).returncode)
