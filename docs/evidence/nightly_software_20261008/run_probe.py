import ctypes
import faulthandler
import os
import sys
from pathlib import Path

repo = next(p for p in Path(__file__).resolve().parents if (p/'.git').exists())
sys.path.append(str(repo / '.venv/Lib/site-packages'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
faulthandler.enable()
ctypes.windll.kernel32.SetErrorMode(0x8003)

# Capture loaded module + RVA without installing a debugger or changing WER.
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.GetModuleHandleExW.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
kernel.RtlCaptureStackBackTrace.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
dbghelp = ctypes.WinDLL('dbghelp')
class SymbolInfo(ctypes.Structure):
    _fields_ = [('size', ctypes.c_ulong), ('type_index', ctypes.c_ulong),
        ('reserved', ctypes.c_uint64 * 2), ('index', ctypes.c_ulong),
        ('symbol_size', ctypes.c_ulong), ('mod_base', ctypes.c_uint64),
        ('flags', ctypes.c_ulong), ('value', ctypes.c_uint64),
        ('address', ctypes.c_uint64), ('register', ctypes.c_ulong),
        ('scope', ctypes.c_ulong), ('tag', ctypes.c_ulong),
        ('name_len', ctypes.c_ulong), ('max_name_len', ctypes.c_ulong),
        ('name', ctypes.c_char * 1024)]
kernel.GetCurrentProcess.restype = ctypes.c_void_p
process = kernel.GetCurrentProcess()
dbghelp.SymInitializeW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
dbghelp.SymFromAddr.argtypes = [ctypes.c_void_p, ctypes.c_uint64,
    ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(SymbolInfo)]
dbghelp.SymInitializeW(process, None, True)

def native_stack():
    frames = (ctypes.c_void_p * 64)()
    count = kernel.RtlCaptureStackBackTrace(0, 64, frames, None)
    for address in frames[:count]:
        module = ctypes.c_void_p()
        name = ctypes.create_unicode_buffer(2048)
        kernel.GetModuleHandleExW(6, address, ctypes.byref(module))
        kernel.GetModuleFileNameW(module, name, len(name))
        symbol = SymbolInfo(); symbol.size = 88; symbol.max_name_len = 1024
        displacement = ctypes.c_uint64()
        resolved = False  # Resolve RVAs offline; loader locks may be held here.
        print(f'NATIVE {name.value}+0x{address-(module.value or 0):x} '
              + (symbol.name.decode(errors='replace') + f'+0x{displacement.value:x}' if resolved else ''), flush=True)

from PySide6.QtCore import qInstallMessageHandler

def message(kind, context, text):
    print(f'QT {kind.name}: {text}', flush=True)
    if 'thread' in text.lower() or kind.name == 'QtFatalMsg':
        native_stack()
        faulthandler.dump_traceback()

handler = qInstallMessageHandler(message)
# CRT abort callback records the native call chain before the usual fatal exit.
crt = ctypes.CDLL('ucrtbase')
abort_callback_type = ctypes.CFUNCTYPE(None, ctypes.c_int)
@abort_callback_type
def abort_trace(number):
    print('CRT ABORT', number, flush=True)
    native_stack()
    faulthandler.dump_traceback()
crt.signal.argtypes = [ctypes.c_int, abort_callback_type]
# Leave faulthandler's abort handler installed for the target run.
import numpy
import pytest
print('ENV', sys.version, sys.executable, numpy.__version__, flush=True)
raise SystemExit(pytest.main(['-p', 'normal_test_paths', '-p', 'closeout_test_paths', *sys.argv[1:]]))
