import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'apps/FCCG/src'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication, QScrollArea
from PySide6.QtGui import QFont, QFontDatabase
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.project.artifact_memory import ArtifactMemorySummary_Encode

app = QApplication([])
fonts = {}
for name in ('msyh.ttc', 'msyhbd.ttc', 'segoeui.ttf', 'segoeuib.ttf'):
    path = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / name
    if path.is_file():
        fonts[name] = QFontDatabase.addApplicationFont(str(path))
app.setFont(QFont('Microsoft YaHei', 9))
service = FccgService(ROOT / 'apps/FCCG')
settings_root = Path(tempfile.mkdtemp(prefix='AutoLayoutGUI-', dir=service.workspace_root / '.work'))
dest = OUT / 'GUI'
dest.mkdir(exist_ok=False)
results = []
for name in ['PureINS', 'KF6', 'ESKF15', 'SF6']:
    log = OUT / (name.lower() + '_auto_arm.log')
    summary = ArtifactMemorySummary_Encode(log.read_text(errors='replace'))
    assert summary, name
    for language in ['zh_CN', 'en_US']:
        for theme in ['light', 'dark']:
            label = '_'.join([name, language, theme])
            window = MainWindow(SettingsStore(settings_root / (label + '.ini')), service=service, language=language, theme=theme)
            window._toolchain_checked = True
            window._model = service.Project_Open(OUT / (name + '_auto_v1'))
            window._Project_Refresh()
            window.build_page.QualityResults_Set([SimpleNamespace(task='artifact_check', summary=summary, result='passed', timestamp='integrated source 430956d, real ARM artifact audit')])
            window.navigation_list.setCurrentRow(window.PAGE_CODES.index('page.build'))
            window.resize(1360, 920)
            window.show()
            app.processEvents()
            for scroll in window.build_page.findChildren(QScrollArea):
                scroll.ensureWidgetVisible(window.build_page.memory_layout_combo)
            app.processEvents()
            assert window.build_page.memory_layout_combo.currentData() == 'auto'
            assert window.version_label.text() == 'v0.1.1'
            results.append({'name': name, 'language': language, 'theme': theme, 'selected': window.build_page.memory_layout_combo.currentData(), 'summary': summary, 'visible_text': window.build_page.memory_margin_value.text(), 'status': window.build_page.memory_margin_value.property('statusLevel'), 'fonts': fonts, 'image': label + '.png'})
            assert window.grab().save(str(dest / (label + '.png')))
            window._project_state = type(window._project_state).DRAFT
            window.close()
            window.deleteLater()
            app.processEvents()
(dest / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print('CAPTURED', len(results))
