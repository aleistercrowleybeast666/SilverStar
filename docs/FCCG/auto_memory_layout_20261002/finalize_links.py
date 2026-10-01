"""Fresh current-adapter links from recorded ARM objects in separate v2 clones.

Runtime sources are byte-checked against their owning payloads. v1's full
compilation logs remain separate; this is explicitly a relink, not a new full
compile. No binary is copied into the v2 output directory.
"""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/FCCG/src"))
from silverstar_fccg.generator.render import _Makefile_Render
from silverstar_fccg.project.model import ProjectModel_Load
from silverstar_fccg.project.build_audit import BuildAudit_Run

DOC = Path(__file__).parent
VERSION = os.environ.get("SILVERSTAR_LINK_VERSION", "v2")
EVIDENCE = DOC / ("evidence_" + VERSION)
EVIDENCE.mkdir(exist_ok=True)
os.environ["PATH"] = "D:/Arm GNU Toolchain/14.3 rel1/bin;D:/msys64/ucrt64/bin;" + str(Path(sys.executable).parent) + ";" + os.environ["PATH"]
PLUGINS = ROOT / "apps/FCCG/plugins/builtin"
TOOL_ROOT = PLUGINS / "silverstar_core_0_1_0/payload/Tools"
current_tool = TOOL_ROOT / "auto_memory_layout.py"
manifest = {"utc": datetime.now(timezone.utc).isoformat(), "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "scope": "fresh current-adapter relink of exact v1 objects; full compilation evidence is v1", "results": []}
if (EVIDENCE / "results.json").exists():
    manifest = json.loads((EVIDENCE / "results.json").read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save():
    (EVIDENCE / "results.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def run(name, directory, command):
    log = EVIDENCE / (name + ".log")
    with log.open("wb") as stream:
        result = subprocess.run(command, cwd=directory, stdout=stream, stderr=subprocess.STDOUT, timeout=600)
    record = {"name": name, "cwd": str(directory), "command": command, "exit_code": result.returncode, "log_sha256": digest(log)}
    manifest["results"].append(record)
    save()
    print(name, result.returncode, flush=True)
    return result.returncode


for name in sys.argv[1:] or ("ESKF15", "KF6", "SF6", "PureINS"):
    if name in manifest:
        continue
    original = ROOT / ".work/AutoMemoryCandidates_v1" / name / "Flight_Controller"
    if not tuple((original / "build/FCCG/SilverStar_F407/Release/auto").glob("*.elf")):
        print("SKIP incomplete v1 auto link: " + name, flush=True)
        continue
    target = ROOT / (".work/AutoMemoryCandidates_" + VERSION) / name / "Flight_Controller"
    if target.exists():
        raise RuntimeError("Use a new final-link version; preserve prior evidence")
    shutil.copytree(original, target, ignore=shutil.ignore_patterns("build", "__pycache__"))
    # Verify each changed first-party runtime payload exactly matches v1 source.
    runtime = {}
    for plugin_name, relative in (
        ("silverstar_algorithm_estimator_eskf15", "Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.c"),
        ("silverstar_core_0_1_0", "APP/Src/estimator_task.c"),
        ("silverstar_core_0_1_0", "System/Src/system_navigation_health.c"),
        ("silverstar_platform_api", "Platform/Inc/platform_memory.h"),
        ("silverstar_mcu_stm32f407vet6", "Targets/SilverStar_F407/Inc/platform_memory_target.h"),
        ("silverstar_mcu_stm32f407vet6", "STM32F407XX_FLASH.ld"),
        ("silverstar_mcu_stm32f407vet6", "startup_stm32f407xx.s"),
    ):
        payload = PLUGINS / plugin_name / "payload" / relative
        if (target / relative).exists():
            assert digest(payload) == digest(target / relative), relative
            runtime[relative] = digest(payload)
    model = ProjectModel_Load(original / "SilverStar.ssproject")
    (target / "Makefile").write_text(_Makefile_Render(model), encoding="utf-8")
    shutil.copy2(ROOT / "apps/FCCG/src/silverstar_fccg/project/build_audit.py", target / "Generated/memory_audit.py")
    for relative in ("auto_memory_layout.py", "check_firmware_artifact.ps1", "check_architecture.ps1"):
        shutil.copy2(TOOL_ROOT / relative, target / "Tools" / relative)
    source_manifest = {str(path.relative_to(target)): digest(path) for path in target.rglob("*") if path.is_file()}
    (EVIDENCE / (name + "_source_sha256.json")).write_text(json.dumps(source_manifest, indent=2) + "\n", encoding="utf-8")
    old_decision = next((original / "build").rglob("decision.json"))
    decision = json.loads(old_decision.read_text())
    command = decision["attempts"][decision["selected"]]["command"]
    objects = [value for value in command if value.endswith(".o")]
    copied_objects = []
    for value in objects:
        relative = Path(value)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original / relative, destination)
        assert digest(destination) == decision["object_sha256"][value]
        copied_objects.append(value)
        stack = (original / relative).with_suffix(".su")
        if stack.exists():
            shutil.copy2(stack, destination.with_suffix(".su"))
    flags = [value for value in command[1:] if value not in objects and not value.startswith("-T") and value != "-o" and not value.endswith(".elf")]
    elf = Path("build/FCCG/SilverStar_F407/Release/auto") / (model.identity.build_target + ".elf")
    code = run(name + "_current_auto_link", target, [sys.executable, "Tools/auto_memory_layout.py", "--linker", "STM32F407XX_FLASH.ld",
        "--output", elf.as_posix(), "--compiler", "arm-none-eabi-gcc", "--objdump", "arm-none-eabi-objdump", "--", *copied_objects, *flags])
    if code:
        continue
    for suffix, format_name in (("hex", "ihex"), ("bin", "binary")):
        run(name + "_" + suffix, target, ["arm-none-eabi-objcopy", "-O", format_name, str(elf), str(elf.with_suffix("." + suffix))])
    run(name + "_current_artifact", target, ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "Tools/check_firmware_artifact.ps1",
        "-Config", "Release", "-MemoryLayout", "auto"])
    run(name + "_current_architecture", target, ["D:/msys64/ucrt64/bin/mingw32-make.exe", "architecture-check"])
    run(name + "_current_power10", target, ["D:/msys64/ucrt64/bin/mingw32-make.exe", "power10-check"])
    audit = BuildAudit_Run(target / elf, (target / elf).with_suffix(".map"), target / "STM32F407XX_FLASH.ld",
        (target / elf).parent, json.loads((PLUGINS / "silverstar_mcu_stm32f407vet6/plugin.json").read_text())["metadata"])
    manifest[name] = {"runtime_owner_sha256": runtime, "existing_resource_audit": audit.__dict__ if hasattr(audit, "__dict__") else str(audit),
                      "audit_errors": audit.errors, "decision": json.loads((target / elf).parent.joinpath("memory_layout/decision.json").read_text()),
                      "artifact_sha256": {suffix: digest((target / elf).with_suffix("." + suffix)) for suffix in ("elf", "map", "bin", "hex")}}
    save()
save()
