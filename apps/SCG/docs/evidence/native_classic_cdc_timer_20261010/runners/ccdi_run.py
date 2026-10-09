from pathlib import Path
import sys,importlib.util
ROOT=Path('D:/python_software/SilverStar')
sys.path.append(str(ROOT/'.venv/Lib/site-packages'))
sys.path[:0]=[str(ROOT/'.work/ccdi/apps/SCG/src'),str(ROOT/'apps/FLP/src'),str(ROOT/'apps/FLP')]
import pytest
plugins=[]
for name in ('normal_test_paths','closeout_test_paths'):
    spec=importlib.util.spec_from_file_location(name,ROOT/('docs/evidence/nightly_software_20261008/'+name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);plugins.append(module)
raise SystemExit(pytest.main(['-p','no:cacheprovider',*sys.argv[1:]],plugins=plugins))
