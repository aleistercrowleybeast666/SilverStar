"""Isolated SCG checkout, normal path ACL fixture, unchanged pytest modules."""
from pathlib import Path
import sys,importlib.util
root=Path(__file__).parent/'r'
sys.path.insert(0,str(root/'apps/SCG/src'))
import pytest
plugin=Path('D:/python_software/SilverStar/docs/evidence/nightly_software_20261008/normal_test_paths.py')
spec=importlib.util.spec_from_file_location('repair_normal_test_paths',plugin)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
raise SystemExit(pytest.main(sys.argv[1:],plugins=[module]))
