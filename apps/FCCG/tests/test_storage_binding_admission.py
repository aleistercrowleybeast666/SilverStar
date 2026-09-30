import copy
from dataclasses import replace

import pytest

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.generator.render import _StorageBindingHeader_Render
from silverstar_fccg.project import storage_binding
from silverstar_fccg.project.resources import ResourceAssignmentResult, ResourceAssignments_Resolve
from silverstar_fccg.project.validation import Project_Validate


@pytest.mark.parametrize("logging", (True, False))
def test_missing_storage_has_same_actionable_validation_and_render_reason(workspace_root, tmp_path, logging):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("StorageAdmission")
    if not logging:
        model.protocols["logging"] = None
    model.device_instances = [d for d in model.device_instances if d.instance_id != "storage0"]
    model.resource_assignments = {k:v for k,v in model.resource_assignments.items() if not k.startswith("storage0:")}
    before = copy.deepcopy(model.Dictionary_Get())
    issues = [i for i in Project_Validate(model, service.catalog).issues if i.code == "STORAGE_DEVICE_REQUIRED"]
    assert len(issues) == 1 and "SDIO" in issues[0].message
    with pytest.raises(ValueError) as rejected:
        _StorageBindingHeader_Render(model, service.catalog)
    assert str(rejected.value) == "STORAGE_DEVICE_REQUIRED: " + issues[0].message
    plan = service.GenerationPlan_Create(model, tmp_path / "not_created")
    assert not plan.validation.valid and not plan.operations
    assert not (tmp_path / "not_created").exists()
    assert model.Dictionary_Get() == before


def test_duplicate_storage_rejected_without_changing_instances(workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("StorageDuplicate")
    original = next(d for d in model.device_instances if d.instance_id == "storage0")
    model.device_instances.append(replace(original, instance_id="storage1"))
    result = storage_binding.StorageBinding_Resolve(model, service.catalog)
    assert not result.valid and result.issues[0].code == "STORAGE_DEVICE_AMBIGUOUS"


@pytest.mark.parametrize("fault", ("unbound", "disabled", "errors", "identifier"))
def test_fatfs_binding_failures_share_authoritative_reason(workspace_root, monkeypatch, fault):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("StorageFatFs")
    result = ResourceAssignments_Resolve(model, service.catalog)
    assignments = []
    for item in result.assignments:
        if item.component_id == "storage0" and item.requirement.kind == "sdio":
            if fault == "unbound":
                continue
            metadata = copy.deepcopy(item.provision.metadata)
            metadata["fatfs"][{"disabled":"enabled", "errors":"errors", "identifier":"object_symbol"}[fault]] = {
                "disabled":False, "errors":["ambiguous symbols"], "identifier":"invalid;symbol"}[fault]
            item = replace(item, provision=replace(item.provision, metadata=metadata))
        assignments.append(item)
    monkeypatch.setattr(storage_binding, "ResourceAssignments_Resolve", lambda *_: ResourceAssignmentResult(tuple(assignments), ()))
    expected = "STORAGE_SDIO_UNBOUND" if fault == "unbound" else "STORAGE_FATFS_INVALID"
    issues = [i for i in Project_Validate(model, service.catalog).issues if i.code == expected]
    assert len(issues) == 1
    with pytest.raises(ValueError, match=expected):
        _StorageBindingHeader_Render(model, service.catalog)


def test_valid_binding_remains_identical_with_logging_disabled(workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("StorageValid")
    header = _StorageBindingHeader_Render(model, service.catalog)
    model.protocols["logging"] = None
    assert storage_binding.StorageBinding_Resolve(model, service.catalog).valid
    assert _StorageBindingHeader_Render(model, service.catalog) == header
