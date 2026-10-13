from pathlib import Path
import json
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "apps/SCG/src"))
from silverstar_fccg.app.service import FccgService

service = FccgService(root / "apps/SCG")
variants = {
    "lf13nolog4": ["logging"],
    "lf13nomain4": ["maintenance"],
    "lf13min4": ["telemetry", "logging", "maintenance"],
}
for name, disabled in variants.items():
    destination = root / ".work" / name
    if destination.exists():
        raise RuntimeError("Fresh destination required: " + str(destination))
    model = service.ReferenceProject_Create(name)
    for protocol in disabled:
        model.protocols[protocol] = None
    model = service.ProjectConfiguration_Reconcile(model).model
    service.Project_Save(model, destination, confirm_dangerous=True)
    print(json.dumps({"directory": str(destination), "disabled": disabled}), flush=True)
