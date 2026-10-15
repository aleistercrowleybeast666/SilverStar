"""A new timing declaration must not bless preserved or edited old payloads."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile


@pytest.mark.parametrize("owner", ("silverstar.algorithm.estimator.kf6", "silverstar.algorithm.estimator.eskf15"))
@pytest.mark.parametrize("relative", (
    "APP/Src/estimator_task.c",
    "System/Inc/system_fusion_timing.h",
    "Protocol/SSLOG/Src/sslog_records.c",
))
def test_new_timing_claim_refuses_user_payload_edit_without_writes(
    tmp_path: Path, workspace_root: Path, owner: str, relative: str,
):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("TimingIdentity")
    model.strategies["estimator"] = owner
    model = ProjectConfiguration_Reconcile(model, service.catalog).model
    model.algorithm_parameters[owner]["fusion_timing_mode"] = 0
    project = tmp_path / "project"
    service.Project_Save(model, project, confirm_dangerous=True)
    target = project / relative
    edited = target.read_bytes() + b"\n/* preserved user edit */\n"
    target.write_bytes(edited)
    managed = {p: sha256(p.read_bytes()).hexdigest() for p in project.rglob("*")
               if p.is_file() and (p.suffix == ".ssdecoder" or "Generated" in p.parts)}
    with pytest.raises((RuntimeError, ValueError), match="(?i)(timing|identity|payload|provenance)"):
        service.Project_Save(model, project, confirm_dangerous=True)
    assert target.read_bytes() == edited
    assert all(sha256(p.read_bytes()).hexdigest() == digest for p, digest in managed.items())


def test_old_undeclared_catalog_is_not_relabelled_or_rejected(tmp_path):
    from silverstar_fccg.generator.fusion_timing import (
        FusionTimingDeclaration_Get, FusionTimingIdentity_Validate,
    )
    owner = "silverstar.algorithm.estimator.kf6"
    manifest = SimpleNamespace(component_id=owner, metadata={})
    catalog = SimpleNamespace(Component_Get=lambda _: manifest)
    model = SimpleNamespace(strategies={"estimator": owner})
    # An old catalog has no timing capability declaration. It stays on its old
    # identity/ownership path; this new guard has nothing to assert about it.
    assert FusionTimingDeclaration_Get(model, catalog) is None
    FusionTimingIdentity_Validate(tmp_path, {}, model, catalog)
    assert not list(tmp_path.iterdir())
