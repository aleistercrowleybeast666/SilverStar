"""Freeze new normal-generated H743 and F407 outputs after whole-file review."""
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
SCG = ROOT / "apps/SCG"
EVIDENCE = Path(__file__).resolve().parent
WORK = ROOT / ".work/0.1.3-treediagram-20261101/h7-storage-v4"
sys.path.insert(0, str(SCG / "src"))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.project.reference import ReferenceProject_Create

spec = importlib.util.spec_from_file_location("h7_fixture", SCG / "tools/validation/h743_static_validate.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
service = FccgService(SCG)
model, validation = fixture.Scenario_Create(service,
    ROOT / ".work/h7_20261025/verified_release/CubeMX_StaticInput", "eskf20", 1, {})
if not validation.valid:
    raise RuntimeError(str(validation))
f407 = ReferenceProject_Create("H7StorageFinalF407", catalog=service.catalog)
current_graph = json.loads(json.dumps(asdict(SourceGraph_Resolve(f407, service.catalog))))
baseline = json.loads((EVIDENCE.parent / "v1/f407-sourcegraph-unchanged.json").read_text())
assert current_graph == baseline["source_graph"]
(EVIDENCE / "f407-sourcegraph-unchanged.json").write_text(json.dumps({
    "baseline": baseline["baseline"], "identical": True, "source_graph": current_graph}, indent=2)+"\n")
for name, selected in (("final", model), ("f407-final", f407)):
    output = WORK / name
    if output.exists():
        raise RuntimeError("A new generated output is required: " + str(output))
    print(TargetGeneration_Apply(selected, service.catalog, WorkspacePolicy(SCG),
                                 output, TargetScope.FLIGHT), flush=True)
    (EVIDENCE / (name+"-model.json")).write_text(json.dumps(selected.Dictionary_Get(), indent=2)+"\n")
owned = ["apps/SCG/src/silverstar_fccg/generator/assembler.py",
         "apps/SCG/src/silverstar_fccg/generator/source_graph.py",
         "apps/SCG/src/silverstar_fccg/generator/h7_storage.py",
         "apps/SCG/tests/test_h7_storage_replacement.py"]
owned += [str(path.relative_to(ROOT)).replace("\\", "/") for directory in (
    SCG / "plugins/builtin/silverstar_device_storage_sdmmc_fatfs_h7",
    SCG / "tests/fixtures/h7_diskio", SCG / "tests/fixtures/h7_storage")
    for path in directory.rglob("*") if path.is_file()]
owned += ["apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/storage_integrity/"+name
          for name in ("run_storage_integrity.py", "test_storage_integrity.c", "test_logger_storage.c")]
snapshot = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sorted(owned)}
record = {"git_head_at_generation": subprocess.check_output(["git", "rev-parse", "HEAD"],cwd=ROOT,text=True).strip(),
          "sha256": snapshot, "snapshot_sha256": hashlib.sha256(json.dumps(snapshot,sort_keys=True).encode()).hexdigest(),
          "validation": repr(validation)}
record["generator_python_sha256"] = {str(path.relative_to(ROOT)).replace("\\", "/"):
    hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((SCG / "src").rglob("*.py"))}
record["git_status_at_generation"] = subprocess.check_output(["git", "status", "--short"],cwd=ROOT,text=True)
(EVIDENCE / "source-snapshot.json").write_text(json.dumps(record,indent=2)+"\n")
