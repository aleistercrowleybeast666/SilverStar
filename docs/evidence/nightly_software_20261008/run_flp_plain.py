import ctypes
import faulthandler
import sys
from pathlib import Path
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ctypes.windll.kernel32.SetErrorMode(0x8003)
faulthandler.enable()
repo = next(p for p in Path(__file__).resolve().parents if (p/'.git').exists())
sys.path.append(str(repo / '.venv/Lib/site-packages'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pytest
raise SystemExit(pytest.main(['-p', 'normal_test_paths', '-p', 'closeout_test_paths',
    '-p', 'no:cacheprovider', *sys.argv[1:]]))
