from pathlib import Path
import importlib.util
import sys
ROOT=Path('D:/python_software/SilverStar')
sys.path.append(str(ROOT/'.venv/Lib/site-packages'))
sys.path[:0]=[str(ROOT/'apps/SCG/src'),str(ROOT/'apps/FLP/src'),str(ROOT/'apps/FLP')]
import silverstar_fccg
print('BASELINE_PACKAGE', silverstar_fccg.__file__, flush=True)
import pytest
plugins=[]
for name in ('normal_test_paths','closeout_test_paths'):
    spec=importlib.util.spec_from_file_location(name,ROOT/('docs/evidence/nightly_software_20261008/'+name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);plugins.append(module)
raise SystemExit(pytest.main(['-p','no:cacheprovider',*sys.argv[1:]],plugins=plugins))
