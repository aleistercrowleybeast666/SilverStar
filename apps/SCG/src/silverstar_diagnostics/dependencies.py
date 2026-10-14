"""Use an existing pyelftools install; never installs or downloads packages."""
import os
from pathlib import Path
import sys
from .contract import DiagnosticError, DiagnosticResult


def ElfTools_Ensure():
    try:
        import elftools
    except ImportError:
        directory = os.environ.get('SILVERSTAR_ELFTOOLS_PATH', os.environ.get('SILVERSTAR_SWD_PYOCD_PATH',''))
        if not directory:
            # Source checkout default reuses the already authorized isolated runtime.
            ancestors = Path(__file__).absolute().parents
            if len(ancestors) > 4:
                directory = str(ancestors[4] / '.work/dev013_swd_pyocd01/deps')
        if not directory or not (Path(directory)/'elftools/__init__.py').is_file():
            raise DiagnosticError(DiagnosticResult.Unsupported,
                'pyelftools 0.33 unavailable; configure SILVERSTAR_ELFTOOLS_PATH (no automatic installation)')
        sys.path.insert(0, str(Path(directory).absolute()))
        import elftools
    if elftools.__version__ != '0.33':
        raise DiagnosticError(DiagnosticResult.Unsupported, 'This reader requires pyelftools 0.33')
