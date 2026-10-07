"""Read-only baseline comparison; load five original modules from Git blobs."""
import importlib.abc
import importlib.util
from pathlib import Path
import subprocess
import sys

repo = Path(__file__).resolve().parents[2]
sys.path.append(str(repo / '.venv/Lib/site-packages'))
modules = ['core.artifacts', 'core.project', 'log_open', 'ui.workers', 'ui.main_window']
sources = {f'silverstar_flp.{name}': subprocess.check_output([
    'git', 'show', 'fd1954b:apps/FLP/src/silverstar_flp/' + name.replace('.', '/') + '.py'],
    cwd=repo) for name in modules}


class BaselineLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in sources:
            return importlib.util.spec_from_loader(fullname, self)

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        path = repo / 'apps/FLP/src' / (module.__name__.replace('.', '/') + '.py')
        module.__file__ = str(path)
        exec(compile(sources[module.__name__], str(path), 'exec'), module.__dict__)


sys.meta_path.insert(0, BaselineLoader())
import numpy
import pytest
print('Baseline fd1954b NumPy', numpy.__version__, 'Python', sys.executable, flush=True)
raise SystemExit(pytest.main(sys.argv[1:]))
