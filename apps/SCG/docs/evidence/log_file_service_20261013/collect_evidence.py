"""Collect scoped development evidence; never substitutes historical artifacts."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
evidence = root / "apps/SCG/docs/evidence/log_file_service_20261013"
evidence.mkdir(parents=True, exist_ok=True)
core = "apps/SCG/plugins/builtin/silverstar_core_0_1_0/"
adapter = "payload/Devices/Storage/SdSdioFatFs/Adapter/Src/log_file_storage.c"
owned = [core + item for item in [
    "plugin.json", "payload/APP/Src/logger_task.c", "payload/BuildSystem/first_party.mk",
    "payload/System/Inc/system_log_file.h", "payload/System/Src/system_log_file.c",
    "payload/System/Src/system_console.c", "payload/Tests/Host/run_tests.ps1",
    "payload/Tests/Host/Fixtures/log_file_storage_stub.c",
    "payload/Tests/Host/storage_integrity/run_storage_integrity.py",
    "payload/Tests/Host/storage_integrity/test_logger_storage.c",
]]
for plugin in ["silverstar_device_storage_sd_sdio_fatfs", "silverstar_device_storage_sd_sdio_fatfs_f1"]:
    owned += ["apps/SCG/plugins/builtin/" + plugin + "/" + name for name in ["plugin.json", adapter]]
owned += [str(path.relative_to(root)).replace("\\", "/") for path in
          (root / "apps/SCG/tests/log_file_service").glob("*") if path.is_file()]
owned += ["apps/SCG/tests/test_log_file_service.py", "docs/public/SCG/LOG_FILE_SERVICE_V1.md",
          "contracts/log_file_service_v1.json", "contracts/session_export_v1.schema.json",
          "contracts/session_export_v1.golden.json"]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(name, value):
    path = evidence / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)

commands = {}
for name, command in {
    "git_head": ["git", "rev-parse", "HEAD"],
    "git_status": ["git", "status", "--short"],
    "gcc": ["gcc", "--version"],
    "arm_gcc": ["arm-none-eabi-gcc", "--version"],
    "make": ["mingw32-make", "--version"],
    "python": [str(root / ".venv/Scripts/python.exe"), "--version"],
}.items():
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    commands[name] = {"command": command, "exit_code": result.returncode,
                      "stdout": result.stdout, "stderr": result.stderr}
write("environment.json", {"captured_at_utc": datetime.now(timezone.utc).isoformat(),
                            "commands": commands, "scope": "dirty working snapshot; no hardware actions"})
write("owned_files.json", owned)
write("source_snapshot.sha256.json", {name: digest(root / name) for name in owned})
for name in owned:
    copy(root / name, evidence / "source_snapshot" / name)
patch = subprocess.run(["git", "diff", "--no-ext-diff", "--", *owned], cwd=root, capture_output=True).stdout
(evidence / "tracked_source.patch").write_bytes(patch)

generated_changed = ["System/Inc/system_log_file.h", "System/Src/system_log_file.c",
                     "System/Src/system_console.c", "APP/Src/logger_task.c",
                     "Devices/Storage/SdSdioFatFs/Adapter/Src/log_file_storage.c",
                     "BuildSystem/first_party.mk", "Tests/Host/run_tests.ps1",
                     "Tests/Host/Fixtures/log_file_storage_stub.c",
                     "Tests/Host/storage_integrity/run_storage_integrity.py",
                     "Tests/Host/storage_integrity/test_logger_storage.c",
                     "SilverStar.ssproject", "Makefile", "Generated/project_sources.mk",
                     "Generated/project_semantics.json", "Generated/Inc/project_flight_config.h",
                     ".fccg/ownership.json", ".fccg/hardware-preparation.json"]
for name in ["lf13f4", "lf13b4", "lf13final4", "lf13final5", "lf13nolog4", "lf13nomain4", "lf13min4", "lf13min4b"]:
    project = root / ".work" / name
    if not project.is_dir():
        continue
    target = evidence / "runs" / name
    for path in project.glob("*.log"):
        copy(path, target / path.name)
    for relative in generated_changed:
        source = project / relative
        if source.is_file():
            copy(source, target / "inputs" / relative)
    inputs = {}
    artifacts = {}
    for path in project.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(project)
        if relative.parts[0] in {"build", "Logs"}:
            if relative.parts[0] == "build" and path.suffix.lower() in {".elf", ".map", ".bin", ".hex", ".su", ".d"}:
                artifacts[relative.as_posix()] = {"sha256": digest(path), "size": path.stat().st_size}
                if path.suffix == ".su" and path.stem in {"system_log_file", "log_file_storage", "logger_task", "system_console"}:
                    copy(path, target / "stack_frames" / relative)
            continue
        if path.suffix != ".log":
            inputs[relative.as_posix()] = digest(path)
    write("runs/" + name + "/generated_inputs.sha256.json", inputs)
    write("runs/" + name + "/artifacts.sha256.json", artifacts)

for name in ["lfs13-finaltest3.log", "lfs13-selection.log", "lfs13-selection2.log", "lfs13-gen-variants.log", "lfs13-final5-generation.log", "lfs13-min4b-generation.log"]:
    path = root / ".work" / name
    if path.is_file():
        copy(path, evidence / name)
for path in (root / ".work/lfs13-finaltest3").rglob("run.json"):
    copy(path, evidence / "dedicated_host" / path.relative_to(root / ".work/lfs13-finaltest3"))
copy(Path(__file__), evidence / "collect_evidence.py")
copy(root / ".work/lfs13_gen_variants.py", evidence / "generate_variants.py")
copy(root / ".work/lfs13_contract.py", evidence / "validate_contract_vectors.py")
print(evidence)
