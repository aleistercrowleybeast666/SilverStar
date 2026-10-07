import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2] / '.venv/Lib/site-packages'))
import numpy
import pytest

print('NumPy', numpy.__version__, 'Python', sys.executable, flush=True)
raise SystemExit(pytest.main(sys.argv[1:]))
