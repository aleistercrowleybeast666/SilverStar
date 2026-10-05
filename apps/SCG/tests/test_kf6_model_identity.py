"""Revision metadata must describe the actual preserved KF6 source."""
import hashlib
import json

import pytest
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.assembler import ProjectAssembler
from silverstar_fccg.generator.kf6_identity import (
    COMPONENT,
    KERNEL_PATHS,
    Kf6Identity_Validate,
)
from silverstar_fccg.generator.log_decoder_profile import LogDecoderProfileSource_Render
from silverstar_fccg.generator.render import (
    ComponentProvenance_Get,
    LogDecoderProfile_Render,
)
from silverstar_fccg.project.reference import ReferenceProject_Create


def test_kf6_preserved_kernel_identity(tmp_path):
    files = {}
    for relative in KERNEL_PATHS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode())
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    previous = {"components": {COMPONENT: {"files": files}}}
    Kf6Identity_Validate(tmp_path, previous, {"files": files})
    before = {p: (tmp_path / p).read_bytes() for p in files}
    upstream = dict(files)
    upstream[KERNEL_PATHS[1]] = "0" * 64
    with pytest.raises(ValueError, match="NOT PROVEN"):
        Kf6Identity_Validate(tmp_path, previous, {"files": upstream})
    assert before == {p: (tmp_path / p).read_bytes() for p in files}
    (tmp_path / KERNEL_PATHS[2]).write_bytes(b"user-owned edit")
    with pytest.raises(ValueError, match="NOT PROVEN"):
        Kf6Identity_Validate(tmp_path, previous, {"files": files})
    assert (tmp_path / KERNEL_PATHS[2]).read_bytes() == b"user-owned edit"
    (tmp_path / KERNEL_PATHS[2]).unlink()
    with pytest.raises(ValueError, match="NOT PROVEN"):
        Kf6Identity_Validate(tmp_path, previous, {"files": files})


def test_kf6_fresh_project_identity(tmp_path):
    Kf6Identity_Validate(tmp_path, {}, {"files": {}})


def test_kf6_unowned_existing_kernel_is_not_a_fresh_project(tmp_path):
    target = tmp_path / KERNEL_PATHS[0]
    target.parent.mkdir(parents=True)
    target.write_bytes(b"user-owned")
    with pytest.raises(ValueError, match="NOT PROVEN"):
        Kf6Identity_Validate(tmp_path, {}, {"files": {}})
    assert target.read_bytes() == b"user-owned"


def test_kf6_loaded_old_model_export_has_one_materialized_identity(tmp_path, builtin_catalog):
    model = ReferenceProject_Create("CloneLegacyIntoFresh", catalog=builtin_catalog)
    old = ComponentProvenance_Get(builtin_catalog, COMPONENT)
    old["files"] = dict(old["files"])
    for path in KERNEL_PATHS:
        old["files"][path] = "0" * 64
    model.component_provenance[COMPONENT] = old
    catalog = builtin_catalog.ProjectView_Get(model)
    assembler = ProjectAssembler(WorkspacePolicy(tmp_path), catalog)
    desired, ownership = assembler._DesiredFiles_Get(model, tmp_path / model.identity.name)
    # Compare the generated Descriptor and package directly, not readiness.
    materialized = ReferenceProject_Create("CloneLegacyIntoFresh", catalog=builtin_catalog)
    materialized.component_provenance = {
        component: ownership["components"][component]
        for component in materialized.ComponentIds_Get()
    }
    expected = LogDecoderProfile_Render(materialized, catalog)
    packages = [data for path, data in desired.items() if path.endswith(".ssdecoder")]
    assert packages == [expected.content]
    assert desired["Generated/Src/project_log_decoder_profile.c"] == LogDecoderProfileSource_Render(expected).encode()
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(packages[0])) as archive:
        packaged = json.loads(archive.read("project_semantics.json"))
    assert json.loads(desired["Generated/project_semantics.json"]) == packaged
    actual = ComponentProvenance_Get(catalog, COMPONENT)["files"]
    assert packaged["metadata_declarations"]["kf6"]["kernel_sha256"] == {path: actual[path] for path in KERNEL_PATHS}
    assert model.component_provenance[COMPONENT]["files"][KERNEL_PATHS[0]] == "0" * 64
    with pytest.raises(ValueError, match="NOT PROVEN"):
        LogDecoderProfile_Render(model, catalog)
