import ctypes
import re
from pathlib import Path
from PySide6 import QtCore, QtWidgets

kernel = ctypes.WinDLL('kernel32')
kernel.GetCurrentProcess.restype = ctypes.c_void_p
kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
kernel.GetModuleHandleW.restype = ctypes.c_void_p
process = kernel.GetCurrentProcess()
dbg = ctypes.WinDLL('dbghelp')
class Symbol(ctypes.Structure):
    _fields_ = [('size', ctypes.c_ulong), ('type', ctypes.c_ulong), ('reserved', ctypes.c_uint64 * 2),
        ('index', ctypes.c_ulong), ('symbol_size', ctypes.c_ulong), ('module', ctypes.c_uint64),
        ('flags', ctypes.c_ulong), ('value', ctypes.c_uint64), ('address', ctypes.c_uint64),
        ('register', ctypes.c_ulong), ('scope', ctypes.c_ulong), ('tag', ctypes.c_ulong),
        ('length', ctypes.c_ulong), ('max_length', ctypes.c_ulong), ('name', ctypes.c_char * 1024)]
dbg.SymInitializeW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
dbg.SymFromAddr.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(Symbol)]
# Export-table lookup only, no remote symbol path.
dbg.SymInitializeW(process, '', True)
seen = set()
for path, offset in re.findall(r'NATIVE (.+?)\+0x([0-9a-f]+)', (Path(__file__).parent/'pre3.log').read_text(encoding='utf-8')):
    if (path, offset) in seen or 'Qt6' not in path:
        continue
    seen.add((path, offset))
    base = kernel.GetModuleHandleW(path)
    symbol = Symbol(); symbol.size = 88; symbol.max_length = 1024
    displacement = ctypes.c_uint64()
    found = base and dbg.SymFromAddr(process, base+int(offset,16), ctypes.byref(displacement), ctypes.byref(symbol))
    print(Path(path).name, offset, symbol.name.decode(errors='replace') if found else 'UNRESOLVED',
        displacement.value if found else '', flush=True)
