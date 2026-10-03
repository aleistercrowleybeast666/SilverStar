"""Test-only binding to the unchanged repository C core, not a shipped DLL."""

import ctypes as ct
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np

Float2, Float3, Float6 = ct.c_float * 2, ct.c_float * 3, ct.c_float * 6


class Sample(ct.Structure):
    _fields_ = [("timestamp", ct.c_uint64), ("state", Float6), ("dv", Float3), ("dt", ct.c_float)]


class Event(ct.Structure):
    _fields_ = [("timestamp", ct.c_uint64), ("observation", Float2), ("group", ct.c_uint8)]


class Context(ct.Structure):
    _fields_ = [
        ("history", Sample * 256),
        ("events", Event * 256),
        ("base", Float6),
        ("gain", Float6),
        ("last_measurement", ct.c_uint64 * 5),
        ("last_receive", ct.c_uint64 * 5),
        ("sequence", ct.c_uint32 * 5),
        ("first", ct.c_uint16),
        ("count", ct.c_uint16),
        ("event_count", ct.c_uint16),
        ("seen", ct.c_uint8 * 5),
        ("initialized", ct.c_uint8),
    ]


class CurrentContext(ct.Structure):
    _fields_ = [
        ("latest", Sample), ("gain", Float6), ("epoch", ct.c_uint64),
        ("last_measurement", ct.c_uint64 * 5), ("last_receive", ct.c_uint64 * 5),
        ("sequence", ct.c_uint32 * 5), ("seen", ct.c_uint8 * 5),
        ("initialized", ct.c_uint8),
    ]


class Measurement(ct.Structure):
    _fields_ = [
        ("measurement", ct.c_uint64),
        ("receive", ct.c_uint64),
        ("sequence", ct.c_uint32),
        ("group", ct.c_uint8),
        ("observation", Float2),
    ]


def Library_Build(directory, *, revision=1):
    compiler = shutil.which("gcc")
    if not compiler:
        raise FileNotFoundError("SF6 oracle requires an actual gcc compiler")
    root = Path(__file__).resolve().parents[2]
    payload = root / "FCCG/plugins/builtin"
    sf6 = Path(__file__).parent / "fixtures/sf6_revision1"
    context_type = Context
    if revision == 2:
        sf6 = payload / "silverstar_algorithm_estimator_sf6/payload/Algorithm/Estimator/SF6"
        context_type = CurrentContext
    elif revision != 1:
        raise ValueError("sf6_oracle_revision_unsupported")
    common = payload / "silverstar_core_0_1_0/payload/Common"
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stub = directory / "assert_host.c"
    stub.write_text(
        """#include "silverstar_assert.h"
#include <stdlib.h>
void SilverStarAssert_Check(uint8_t condition, SilverStarAssertModuleId module,
 const char *file, uint32_t line, SilverStarAssertReasonId reason)
{
 (void)module; (void)file; (void)line; (void)reason;
 if (!condition) { abort(); }
}
""",
        encoding="utf-8",
    )
    library_path = directory / ("sf6_oracle.dll" if os.name == "nt" else "sf6_oracle.so")
    include = sf6 if revision == 1 else sf6 / "Inc"
    source = sf6 / "navigation_sf6.c" if revision == 1 else sf6 / "Src/navigation_sf6.c"
    sources = [source, stub]
    command = [
        compiler,
        "-shared",
        "-std=c11",
        "-O0",
        "-fno-fast-math",
        "-ffp-contract=off",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-I" + str(include),
        "-I" + str(common / "Inc"),
        *map(str, sources),
        "-lm",
        "-o",
        str(library_path),
    ]
    if os.name != "nt":
        command.insert(2, "-fPIC")
    result = subprocess.run(command, capture_output=True, text=True)
    report = {
        "command": command,
        "algorithm_revision": revision,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "compiler_version": subprocess.run(
            [compiler, "--version"], capture_output=True, text=True
        ).stdout,
        "source_hashes": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (*sources, include / "navigation_sf6.h")
        },
    }
    if library_path.exists():
        report["artifact_sha256"] = hashlib.sha256(library_path.read_bytes()).hexdigest()
    (directory / "oracle_build.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if result.returncode:
        raise RuntimeError(result.stderr)
    if os.name == "nt":
        # Keep the DLL search-directory handle alive while the binding is used.
        search_directory = os.add_dll_directory(str(Path(compiler).parent))
    library = ct.CDLL(str(library_path))
    if os.name == "nt":
        library._search_directory = search_directory
    library.NavigationSf6_Initialize.argtypes = [
        ct.POINTER(context_type),
        ct.POINTER(ct.c_float),
        ct.POINTER(ct.c_float),
        ct.c_uint64,
    ]
    library.NavigationSf6_Predict.argtypes = [
        ct.POINTER(context_type),
        ct.c_uint64,
        ct.POINTER(ct.c_float),
        ct.c_float,
    ]
    library.NavigationSf6_Update.argtypes = [
        ct.POINTER(context_type),
        ct.POINTER(Measurement),
        ct.POINTER(ct.c_uint64),
    ]
    library.NavigationSf6_SnapshotGet.argtypes = [ct.POINTER(context_type), ct.POINTER(Sample)]
    library._context_type = context_type
    return library


class CCore:
    def __init__(self, library, gain, velocity=(0, 0, 0), timestamp=0):
        self.library, self.context = library, library._context_type()
        assert (
            library.NavigationSf6_Initialize(
                ct.byref(self.context), Float6(*gain), Float3(*velocity), timestamp
            )
            == 0
        )

    @property
    def state(self):
        sample = Sample()
        assert self.library.NavigationSf6_SnapshotGet(ct.byref(self.context), ct.byref(sample)) == 0
        return np.asarray(sample.state, dtype=np.float32)

    def Predict(self, timestamp, dv, dt):
        return self.library.NavigationSf6_Predict(
            ct.byref(self.context), timestamp, Float3(*dv), dt
        )

    def Update(self, item):
        boundary = ct.c_uint64(2**64 - 1)
        measurement = Measurement(
            item.measurement_us,
            item.receive_us,
            item.sequence,
            item.group,
            Float2(*item.observation),
        )
        result = self.library.NavigationSf6_Update(
            ct.byref(self.context), ct.byref(measurement), ct.byref(boundary)
        )
        return result, boundary.value if result == 0 else None
