"""Configuration snapshot of existing flight rules; no new runtime state machine."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import runpy
import sys

from silverstar_fccg.app.version import __version__

_ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[5]
_API = runpy.run_path(str(_ROOT / "tools/silverstar_mission_profile.py"))
MissionProfile_Read = _API["MissionProfile_Read"]
MissionProfile_Write = _API["MissionProfile_Write"]
MissionProfile_Require = _API["MissionProfile_Require"]


class MissionProfileUnsupportedError(ValueError):
    """An optional snapshot format cannot describe this otherwise valid recipe."""


def MissionProfile_Build(model, catalog):
    contract = _API["CONTRACT"]
    catalog = catalog.ProjectView_Get(model)
    if "silverstar.flight_logic.cycle.reference" not in model.ComponentIds_Get():
        raise MissionProfileUnsupportedError("mission_profile_template_unsupported")
    def component(component_id):
        if component_id is None:
            return None
        manifest = catalog.Component_Get(component_id)
        return {"plugin_id": component_id, "version": manifest.version}

    rules = []
    for component_id in model.base_components:
        manifest = catalog.Component_Get(component_id)
        selection = manifest.selection
        if selection is None or selection.slot == "calibration" or selection.kind.value != "mode":
            continue
        if component(component_id) != contract['rule_owner']:
            raise MissionProfileUnsupportedError('mission_profile_rule_unsupported:' + component_id + '@' + manifest.version)
        for option in selection.options:
            values = model.mode_parameters.get(selection.slot, {}).get(option, {})
            rules.append({"owner": component(component_id), "slot": selection.slot, "option": option,
                "enabled": option in model.modes.get(selection.slot, []),
                "parameters": [{"id": p.parameter_id, "type": p.value_type,
                    "value": values.get(p.parameter_id, p.default), "unit": p.unit,
                    "minimum": p.minimum, "maximum": p.maximum,
                    "generated_symbol": p.generated_symbol, "generated_scale": p.generated_scale}
                    for p in selection.parameters.get(option, ())]})
    profile = {"schema_id": contract["schema_id"], "schema_version": 1, "source": "scg_project",
        "project": {"name": model.identity.name, "firmware_version": model.identity.firmware_version,
                    "generator_version": __version__, "mcu": model.mcu, "board": model.board},
        "frame": deepcopy(contract["frame"]),
        "lifecycle": {"template_id": contract["lifecycle_template"], "states": deepcopy(contract["states"])},
        "rules": rules,
        "continuous": {**{key: component(model.strategies.get(key)) for key in ("ins", "estimator", "landing")},
                       "logging": [asdict(row) for row in model.logging_streams]},
        "qualification": deepcopy(contract["qualification"])}
    profile["sha256"] = _API["MissionProfile_Digest"](profile)
    return MissionProfile_Require(profile)
