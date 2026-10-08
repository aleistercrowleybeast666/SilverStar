from pathlib import Path
import os, sys, json, platform, datetime
os.environ['QT_QPA_PLATFORM'] = 'windows'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
root = Path(__file__).resolve().parent
repo = root.parents[1]
sys.path[:0] = [str(repo/'apps/FLP/src'), str(repo/'apps/FLP')]
import pytest
import numpy as np
import PySide6
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from silverstar_flp.core.path_preferences import PathPreferences
from silverstar_flp.plugins.container_packages import TrustedContainerPluginManager
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.log_open import LogOpenCoordinator
import silverstar_flp.ui.main_window as module

class IsolatedPreferences:
    @pytest.fixture(autouse=True)
    def private_ui(self, monkeypatch, tmp_path):
        monkeypatch.setattr(module, 'QSettings', lambda *a, **k:
            QSettings(str(tmp_path/'isolated.ini'), QSettings.Format.IniFormat))
        monkeypatch.setattr(module, 'PathPreferences', lambda *a, **k:
            PathPreferences(tmp_path/'paths.json'))
        monkeypatch.setattr(module, 'TrustedContainerPluginManager', lambda *a, **k:
            TrustedContainerPluginManager(tmp_path/'plugins'))
        monkeypatch.setattr(module, 'LogOpenCoordinator', lambda registry, *a, **k:
            LogOpenCoordinator(registry, cache=DecoderProfileCache(tmp_path/'cache')))

app = QApplication([])
assert app.platformName() == 'windows'
sys.path.insert(0,str(repo/'.work/nightly_closeout_20261008'))
sys.path.append(str(repo/'.venv/Lib/site-packages'))
args = ['-p', 'pytestqt.plugin', '-p', 'normal_test_paths', '-p', 'no:cacheprovider', '-v', '-ra', '--basetemp='+str(root/'pytest_v3'),
        '--junitxml='+str(root/'pytest_v3.xml'),
        str(repo/'apps/FLP/tests/test_project_stage_progress.py'),
        str(repo/'apps/FLP/tests/test_project_stage_progress_gui.py'),
        str(repo/'apps/FLP/tests/test_optional_secondary_source.py')+'::test_secondary_default_none_and_full_run_identity',
        str(repo/'apps/FLP/tests/test_optional_secondary_source.py')+'::test_compatibility_never_fills_or_relabels_primary',
        str(repo/'apps/FLP/tests/test_optional_secondary_source.py')+'::test_state_group_selections_survive_display_refresh']
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
code = pytest.main(args, plugins=[IsolatedPreferences()])
(root/'focused_test_result_v3.json').write_text(json.dumps({
    'started_utc': started, 'finished_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'exit': int(code), 'args': args, 'python': sys.version, 'numpy': np.__version__,
    'pyside': PySide6.__version__, 'platform': app.platformName(),
    'settings_isolated': True, 'scope': 'Tiny deterministic fixtures; not actual TF fault injection'
}, indent=2), encoding='utf-8')
sys.exit(code)
