import sys
from pathlib import Path
repo=next(p for p in Path(__file__).resolve().parents if (p/'.git').exists())
sys.path[:0]=[str(repo/'apps/GSHC'),str(repo/'apps/GSHC/tests')]
import pytest
raise SystemExit(pytest.main(['-p','normal_test_paths','-p','no:cacheprovider',*sys.argv[1:]]))
