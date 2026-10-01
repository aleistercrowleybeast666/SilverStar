"""Generate fresh independent KF6/Ground and ESKF15 candidates; no hardware I/O."""
import json
from pathlib import Path
import sys
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "apps/FCCG/src"), str(ROOT / "apps/FCCG/tests")]
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.folder_contract import ProjectRoot_Save
from silverstar_fccg.project.logging import LoggingProfile_AvailabilityTransitionApply
from test_gui_qa_repair import _GroundF103Model_Get

directory = ROOT / ".work/PostFieldMemory_d410f4a_20261001_v3"
if directory.exists():
    raise SystemExit("Validation directory already exists; choose a fresh version")
service = FccgService(ROOT / "apps/FCCG")
for name in ("kf6", "eskf"):
    model = _GroundF103Model_Get(service.catalog)
    model.identity = type(model.identity)("PostFieldMemory_" + name)
    previous = deepcopy(model)
    # Preserve today's 200 Hz configuration. This is synthetic validation.
    model.algorithm_parameters["silverstar.algorithm.ins.coning2_sculling2"]["mechanization_aggregation"] = 1
    if name == "eskf":
        model.strategies["estimator"] = "silverstar.algorithm.estimator.eskf15"
        LoggingProfile_AvailabilityTransitionApply(previous, model, service.catalog)
        model = service.ProjectConfiguration_Reconcile(model).model
    project = directory / name
    ProjectRoot_Save(model, project, create_new=True)
    result = TargetGeneration_Apply(model, service.catalog, service.policy, project,
                                   TargetScope.ALL if name == "kf6" else TargetScope.FLIGHT,
                                   confirm_dangerous=True)
    (Path(__file__).parent / (name + "_configuration.ssproject")).write_text(
        json.dumps(model.Dictionary_Get(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"project": str(project), "targets": result.targets,
                      "files": len(result.file_hashes)}), flush=True)
