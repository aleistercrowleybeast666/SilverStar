"""Legacy path compatibility; the application implementation lives in apps/SCG."""
from pathlib import Path
import runpy
import sys

if __name__ == "__main__":
    application = Path(__file__).resolve().parents[1] / "SCG"
    sys.path.insert(0, str(application))
    runpy.run_path(str(application / "main.py"), run_name="__main__")
