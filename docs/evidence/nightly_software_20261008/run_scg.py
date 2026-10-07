import sys
from pathlib import Path
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
raise SystemExit(pytest.main(['-p', 'normal_test_paths', '-p', 'no:cacheprovider', *sys.argv[1:]]))
