from __future__ import annotations
import hashlib,json,os,shutil,subprocess
from pathlib import Path
import pytest
@pytest.fixture(scope="module")
def runtime_owner_executable(tmp_path_factory):
    gcc=shutil.which("gcc")
    if gcc is None:pytest.skip("Host GCC unavailable")
    root=Path(__file__).resolve().parents[1]
    project=Path(os.environ["SILVERSTAR_RADIO_GENERATED_PROJECT"]).resolve()
    build=tmp_path_factory.mktemp("runtime-owner-build")
    includes=[p for p in project.rglob("Inc") if "build" not in p.parts]
    includes += [project/"Common/Src",project/"System/User",project/"Tests/Host",project/"Devices/Telemetry/SX1281/Src",project/"System/Src",project/"Middlewares/Third_Party/SX1280lib"]
    cmd=[gcc,"-std=c11","-O2","-Wall","-Wextra","-Werror","-pedantic","-ffunction-sections","-fdata-sections","-Wl,--gc-sections","-DSILVERSTAR_AIR_LINK_ENABLED=1","-include",str(project/"Generated/Inc/project_flight_config.h")]
    for p in includes:cmd.extend(["-I",str(p)])
    fixture=root/"tests/fixtures/radio_runtime_owner_host.c"
    files=[fixture]+[project/p for p in ["Devices/Telemetry/SX1281/Adapter/Src/sx1281_telemetry_adapter.c","Generated/Src/project_resources.c"]]
    exe=build/"runtime.exe";cmd += [str(p) for p in files]+["-lm","-o",str(exe)]
    result=subprocess.run(cmd,cwd=build,capture_output=True,text=True,encoding="utf8",errors="replace",timeout=90)
    (build/"compile-record.json").write_text(json.dumps({"command":cmd,"cwd":str(build),"exit":result.returncode,"stdout":result.stdout,"stderr":result.stderr},indent=2),encoding="utf8")
    files += [project/"Common/Src/silverstar_assert.c",project/"System/Src/system_startup.c",project/"Devices/Telemetry/SX1281/Src/sx1281_device.c"]
    (build/"source-hashes.json").write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2),encoding="utf8")
    assert result.returncode==0,result.stdout+result.stderr
    return exe,build
@pytest.mark.parametrize("fault",["busy","spi","timeout"])
def test_runtime_owner_generated(runtime_owner_executable,fault):
    exe,build=runtime_owner_executable
    result=subprocess.run([str(exe),fault],cwd=build,capture_output=True,text=True,encoding="utf8",errors="replace",timeout=30)
    (build/(fault+".log")).write_text(result.stdout+result.stderr,encoding="utf8")
    (build/(fault+".exit")).write_text(str(result.returncode),encoding="utf8")
    assert result.returncode==0,result.stdout+result.stderr
    assert "0 failures" in result.stdout

def test_generated_telemetry_runtime_callers():
    import re
    project=Path(os.environ["SILVERSTAR_RADIO_GENERATED_PROJECT"]).resolve()
    callers=[]
    for source in project.rglob("*.c"):
        if "Tests" in source.parts or "build" in source.parts:continue
        if re.search(r"\bSystemTelemetry_Process\s*\(\s*\)",source.read_text(encoding="utf8")):
            callers.append(str(source.relative_to(project)).replace("\\","/"))
    assert callers==["Modules/Src/telemetry_service.c"],callers
    task=(project/"APP/Src/telemetry_task.c").read_text(encoding="utf8")
    service=(project/"Modules/Src/telemetry_service.c").read_text(encoding="utf8")
    assert "TelemetryService_Process();" in task
    assert "SystemTelemetry_Process();" in service
    startup=(project/"System/Src/system_startup.c").read_text(encoding="utf8")
    assert "device->init_result = SystemTelemetry_Init();" in startup
    assert "device->start_result = SystemTelemetry_Start();" in startup
    # Bootstrap publishes started only after HAL initialization/start completes.
    adapter=(project/"Devices/Telemetry/SX1281/Adapter/Src/sx1281_telemetry_adapter.c").read_text(encoding="utf8")
    start=adapter[adapter.index("static SystemDeviceResult Sx1281Transport_Start("):adapter.index("static SystemDeviceResult Sx1281Transport_Stop(")]
    assert start.index("Lora_StartRx(instance);") < start.index("s_started = 1U;")
