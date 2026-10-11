"""Launch the unchanged application from its preserved source/resource layout."""
from pathlib import Path
import runpy
import sys

root = Path(sys._MEIPASS)
sys.dont_write_bytecode = True
application = root / "apps" / "SCG"
sys.path.insert(0, str(application))
runpy.run_path(str(application / "main.py"), run_name="__main__")
