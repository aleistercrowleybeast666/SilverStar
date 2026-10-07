import importlib.metadata as metadata
import json
import platform
import sys
packages={}
for name in ('pytest','pytest-qt','PySide6','shiboken6','pyqtgraph','numpy','matplotlib'):
    try: packages[name]=metadata.version(name)
    except metadata.PackageNotFoundError: packages[name]=None
print(json.dumps({'python':sys.version,'executable':sys.executable,
    'platform':platform.platform(),'packages':packages},indent=2))
