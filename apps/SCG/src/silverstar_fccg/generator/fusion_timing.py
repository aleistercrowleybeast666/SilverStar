"""Timing declarations require the actual selected mode and its owning payload."""
from __future__ import annotations

import hashlib
from pathlib import Path

from silverstar_fccg.project.algorithm_parameters import AlgorithmParameters_Resolve


_OWNERS = ("silverstar.algorithm.estimator.kf6", "silverstar.algorithm.estimator.eskf15")
_CAPABILITY = {"schema_id": "silverstar.navigation-fusion-timing/1",
               "revision": 1, "parameter": "fusion_timing_mode"}


def _Owner_Get(model, catalog):
    owner = model.strategies.get("estimator")
    if owner not in _OWNERS:
        return None
    capability = catalog.Component_Get(owner).metadata.get("fusion_timing_contract")
    if capability is None:
        return None
    if capability != _CAPABILITY:
        raise ValueError("Unsupported fusion timing capability declaration")
    return owner


def _Components_Get(model, catalog):
    # The owning core and optional logging component are selected by identity,
    # not inferred from file names. Validate every copied payload in these owners.
    owner = _Owner_Get(model, catalog)
    if owner is None:
        return ()
    return tuple(component for component in model.ComponentIds_Get()
                 if component == owner or catalog.Component_Get(component).component_type == "core"
                 or component == getattr(model.protocols.get("logging"), "component", None))


def FusionTimingDeclaration_Get(model, catalog):
    owner = _Owner_Get(model, catalog)
    if owner is None:
        return None
    actual = next(row for row in AlgorithmParameters_Resolve(model, catalog)
                  if row["component"] == owner)
    mode = next(row["value"] for row in actual["parameters"]
                if row["id"] == "fusion_timing_mode")
    if type(mode) is not int or mode not in (0, 1):
        raise ValueError("Fusion timing actual must be integer 0 or 1")
    from silverstar_fccg.generator.render import ComponentProvenance_Get
    for component in _Components_Get(model, catalog):
        upstream = ComponentProvenance_Get(catalog, component)["files"]
        declared = model.component_provenance.get(component)
        if declared is not None and declared.get("files") != upstream:
            raise ValueError("Fusion timing payload identity NOT PROVEN: preserved provenance")
    return {"schema_id": _CAPABILITY["schema_id"], "revision": 1,
            "component": owner, "mode": mode,
            "source_time": "resolved_measurement_epoch",
            "application_time": "estimator_present" if mode == 0 else "legacy_algorithm_epoch",
            "evaluation_time": "estimator_present", "output_state_time": "estimator_present",
            "output_covariance_time": "estimator_present", "replays_history": mode == 1}


def FusionTimingIdentity_Validate(project_root: Path, previous: dict, model, catalog) -> None:
    if _Owner_Get(model, catalog) is None:
        return
    from silverstar_fccg.generator.render import ComponentProvenance_Get
    root = project_root.resolve()
    for component in _Components_Get(model, catalog):
        upstream = ComponentProvenance_Get(catalog, component)["files"]
        prior = previous.get("components", {}).get(component, {}).get("files", {})
        for relative, digest in upstream.items():
            target = project_root.joinpath(*relative.split("/"))
            unsafe = target.is_symlink() or not target.resolve().is_relative_to(root)
            if not prior and not target.exists() and not unsafe:
                continue
            if (unsafe or prior.get(relative) != digest or not target.is_file()
                    or hashlib.sha256(target.read_bytes()).hexdigest() != digest):
                raise ValueError("Fusion timing payload identity NOT PROVEN: "
                    f"{relative}; use a fresh separately named project. "
                    "Preserved user sources and decoder are not replaced.")
