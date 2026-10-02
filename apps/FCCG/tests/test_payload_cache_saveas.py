"""Python caches must never become project-owned source or relax source conflicts."""
from copy import copy
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.errors import FccgError
from silverstar_fccg.project.model import ProjectModel_Load


def _PollutedService_Create(workspace_root, root):
    service = FccgService(workspace_root)
    core = service.catalog.Component_Get("silverstar.core.0_1_0")
    package = root / "core"
    shutil.copytree(core.package_root, package)
    tools = package / "payload/Tools"
    cache = root / "import_cache"
    code = ("import sys,importlib.util,shutil; from pathlib import Path; "
            "sys.pycache_prefix="+repr(str(cache))+"; sys.dont_write_bytecode=False; "
            "sys.path.insert(0,"+repr(str(tools))+"); import auto_memory_layout,check_task_stacks; "
            "out=Path("+repr(str(tools/"__pycache__"))+"); out.mkdir(); "
            "[shutil.copyfile(importlib.util.cache_from_source(module.__file__),"
            "out/(module.__name__+'.cpython-test.pyc')) for module in (auto_memory_layout,check_task_stacks)]")
    # Every Python cache, including stdlib imports, is directed into this isolated fixture.
    result = subprocess.run([sys.executable,"-I","-S","-c",code],capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stdout+result.stderr
    (tools/"legacy.pyo").write_bytes(next((tools/"__pycache__").glob("*.pyc")).read_bytes())
    source = tools/"build/keep_source.c"
    source.parent.mkdir();source.write_text("/* real component source in a build-named directory */\n",encoding="utf8")
    service.catalog = copy(service.catalog)
    service.catalog._components = dict(service.catalog._components)
    service.catalog._components[core.component_id] = replace(core,manifest_path=package/"plugin.json")
    return service, service.catalog.Component_Get(core.component_id)


def test_payload_inventory_excludes_only_python_cache(workspace_root,tmp_path):
    service, core = _PollutedService_Create(workspace_root,tmp_path)
    files = {p.relative_to(core.payload_root).as_posix() for p in core.PayloadFiles_Get()}
    assert "Tools/build/keep_source.c" in files
    assert "Tools/auto_memory_layout.py" in files
    assert not any("__pycache__" in Path(p).parts or Path(p).suffix in {".pyc",".pyo"} for p in files)


def test_generation_saveas_ignores_cache_ownership_and_preserves_sources(workspace_root,tmp_path):
    service, core = _PollutedService_Create(workspace_root,tmp_path)
    model = service.ReferenceProject_Create("CacheSafeCopy")
    source=tmp_path/"source";destination=tmp_path/"copy"
    service.GenerationPlan_Apply(model,service.GenerationPlan_Create(model,source))
    edited=source/"Devices/IMU/JY901B/Src/jy901b_device.c"
    marker="\n/* MANUAL SOURCE MUST SURVIVE CACHE MIGRATION */\n"
    edited.write_text(edited.read_text(encoding="utf8")+marker,encoding="utf8")
    ownership_path=source/".fccg/ownership.json"
    ownership=json.loads(ownership_path.read_text(encoding="utf8"))
    old_cache={"Tools/__pycache__/auto_memory_layout.cpython-test.pyc":"a"*64,"Tools/legacy.pyo":"b"*64}
    ownership["components"][core.component_id]["files"].update(old_cache)
    ownership_path.write_text(json.dumps(ownership,indent=2)+"\n",encoding="utf8")
    copied=service.Project_SaveAs(model,source,destination)
    assert (copied/edited.relative_to(source)).read_text(encoding="utf8").endswith(marker)
    assert (copied/"Tools/build/keep_source.c").read_bytes()==(source/"Tools/build/keep_source.c").read_bytes()
    assert not any(p.suffix in {".pyc",".pyo"} or "__pycache__" in p.parts for p in copied.rglob("*"))
    assembler=service._Assembler_Get(copied)
    migrated=assembler._Ownership_Load(copied)
    assert not set(old_cache)&set(migrated["components"][core.component_id]["files"])
    assert assembler.Plan(model,copied).valid
    assert ProjectModel_Load(copied/"SilverStar.ssproject").identity.name=="CacheSafeCopy"


def test_saveas_missing_real_source_still_conflicts_with_path(workspace_root,tmp_path):
    service=FccgService(workspace_root)
    model=service.ReferenceProject_Create("MissingSource")
    source=tmp_path/"source"
    service.GenerationPlan_Apply(model,service.GenerationPlan_Create(model,source))
    relative="Devices/IMU/JY901B/Src/jy901b_device.c"
    (source/relative).unlink()  # Only this isolated generated fixture.
    with pytest.raises(FccgError) as caught:
        service.Project_SaveAs(model,source,tmp_path/"copy")
    assert caught.value.code=="error.project_validation_failed"
    assert caught.value.params["count"]>0
    assert relative in caught.value.technical_detail
    assert "project-owned component file is missing" in caught.value.technical_detail
    assert not (source/relative).exists()


@pytest.mark.parametrize("path, expected", [
    ("Tools/__pycache__/file.pyc", True), ("Tools/cache.PYO", True),
    ("Tools/build/keep_source.c", False), ("Tools/build/source.py", False),
    ("../__pycache__/file.pyc", False), ("/Tools/cache.pyc", False),
    ("C:/Tools/cache.pyc", False), ("Tools/../cache.pyc", False),
])
def test_cache_boundary_does_not_hide_unsafe_ownership_paths(path, expected):
    from silverstar_fccg.plugins.manifest import PayloadCachePath_Is
    assert PayloadCachePath_Is(path) is expected
