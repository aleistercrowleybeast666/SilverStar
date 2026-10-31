"""Generate a new versioned H743 SDMMC candidate from retained CubeMX input."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
SCG = ROOT / "apps/SCG"
sys.path.insert(0, str(SCG / "src"))
spec = importlib.util.spec_from_file_location("h7_fixture", SCG / "tools/validation/h743_static_validate.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
service = fixture.FccgService(SCG)
model, validation = fixture.Scenario_Create(service,
    ROOT / ".work/h7_20261025/verified_release/CubeMX_StaticInput", "eskf20", 1, {})
if not validation.valid:
    raise RuntimeError(str(validation))
output = ROOT / ".work/0.1.3-treediagram-20261101/h7-storage-v5/probe2"
if output.exists():
    raise RuntimeError("A new generated output is required")
result = fixture.TargetGeneration_Apply(model, service.catalog,
    fixture.WorkspacePolicy(SCG), output, fixture.TargetScope.FLIGHT)
(Path(__file__).with_name("project-model.json")).write_text(
    json.dumps(model.Dictionary_Get(), indent=2)+"\n", encoding="utf8")
print(validation)
print(result)
