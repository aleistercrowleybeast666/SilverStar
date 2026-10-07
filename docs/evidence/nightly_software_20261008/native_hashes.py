import hashlib
import json
from pathlib import Path
import sys
from PySide6 import QtCore, QtWidgets
import shiboken6

base=Path(QtCore.__file__).parent
files=[Path(QtCore.__file__),Path(QtWidgets.__file__),base/'Qt6Core.dll',base/'Qt6Widgets.dll',
       Path(shiboken6.__file__).parent/'shiboken6.abi3.dll',Path(sys.base_prefix)/'python314.dll']
print(json.dumps({str(p):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                  for p in files},indent=2))
