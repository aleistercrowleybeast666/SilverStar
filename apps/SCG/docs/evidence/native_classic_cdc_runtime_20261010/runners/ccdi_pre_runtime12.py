from pathlib import Path
import sys, runpy
root = Path('D:/python_software/SilverStar')
sys.path.insert(0, str(root/'.work/ccdi/apps/SCG/src'))
from silverstar_fccg.generator import native_runtime
old = Path('C:/Users/chdxm/AppData/Local/Temp/sscdc-ground-f103-11b')
native_runtime.NativeRuntime_FilesRender = lambda: {
    p: (old/p).read_bytes() for p in ['Generated/Inc/native_runtime.h','Generated/Src/native_runtime.c']}
runpy.run_path(str(root/'.work/ccdi_run.py'),run_name='__main__')
