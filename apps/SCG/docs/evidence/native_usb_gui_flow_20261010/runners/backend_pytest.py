"""Use inherited Windows test directory ACLs; no permission changes."""
from pathlib import Path
import importlib.util
import sys

root = Path('D:/python_software/SilverStar/.work/ccdi')
sys.path.insert(0, str(root / 'apps/SCG/src'))
import pytest
plugin = Path('D:/python_software/SilverStar/docs/evidence/nightly_software_20261008/normal_test_paths.py')
spec = importlib.util.spec_from_file_location('native_backend_test_paths', plugin)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
raise SystemExit(pytest.main(sys.argv[1:], plugins=[module]))
