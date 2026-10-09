from pathlib import Path
import sys
repo = Path(__file__).resolve().parents[2]
# Reuse the installed test plugin; retain this interpreter's NumPy 2.4.1 and Qt.
sys.path.append(str(repo/'.venv/Lib/site-packages'))
sys.path[:0] = [str(repo/'apps/SCG/src'),str(repo/'apps/FLP/src'),str(repo/'apps/FLP')]
import pytest
import importlib.util
spec = importlib.util.spec_from_file_location('normal_test_paths', repo/'docs/evidence/nightly_software_20261008/normal_test_paths.py')
normal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(normal)
spec2 = importlib.util.spec_from_file_location('closeout_test_paths', repo/'docs/evidence/nightly_software_20261008/closeout_test_paths.py')
private = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(private)
raise SystemExit(pytest.main(['-p','no:cacheprovider',*sys.argv[1:]],plugins=[normal, private]))
