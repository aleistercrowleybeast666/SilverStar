"""Native EIDE commands with synthetic ARM artifacts; no live target."""
import json
import os
from pathlib import Path
import subprocess

import pytest

from test_swd_image_contract import image, TARGET
from silverstar_diagnostics import eide
from silverstar_diagnostics.contract import DiagnosticError
from silverstar_diagnostics.project_descriptor import ProjectDescriptor_Create, ProjectDescriptor_Begin
from services.swd_import import Firmware_ImportAuto
from transport.swd_firmware import DiagnosticResult


def entry(image):
    descriptor = image.parent / "Flight.ssdiag"
    descriptor.write_text(json.dumps(ProjectDescriptor_Create("Synthetic", TARGET)))
    return descriptor


def test_eide_successful_pair_imports_then_next_build_invalidates(image):
    descriptor = entry(image)
    result = eide.EideDiagnostics_Bind(descriptor, image)
    assert result["image_contract_version"] == 2 and not result["hardware_verified"]
    assert Firmware_ImportAuto([descriptor]).result == DiagnosticResult.Ok
    ProjectDescriptor_Begin(descriptor)
    assert Firmware_ImportAuto([descriptor]).firmware is None


def test_corrupt_hex_cannot_publish_a_fresh_ready_entry(image):
    descriptor = entry(image)
    eide.EideDiagnostics_Bind(descriptor, image)
    image.with_suffix(".hex").write_text(":bad")
    with pytest.raises(DiagnosticError):
        eide.EideDiagnostics_Bind(descriptor, image)
    assert json.loads(descriptor.read_text())["state"] == "pending_build"
    assert Firmware_ImportAuto([descriptor]).firmware is None


def test_changed_artifacts_during_binding_are_invalidated(image, monkeypatch):
    descriptor = entry(image)
    resolve = eide.ProjectDescriptor_Resolve
    def changed(*args, **kwargs):
        firmware = resolve(*args, **kwargs)
        image.with_suffix(".hex").write_bytes(image.with_suffix(".hex").read_bytes() + b"\n")
        return firmware
    monkeypatch.setattr(eide, "ProjectDescriptor_Resolve", changed)
    with pytest.raises(DiagnosticError, match="changed during binding"):
        eide.EideDiagnostics_Bind(descriptor, image)
    assert Firmware_ImportAuto([descriptor]).firmware is None


@pytest.mark.skipif(os.name != "nt", reason="Native EIDE Windows command quoting")
def test_expanded_native_commands_accept_paths_with_spaces(image, tmp_path):
    import shutil
    root = tmp_path / "Flight with spaces"
    output = root / "EIDE/Release"
    output.mkdir(parents=True)
    elf = output / "fixture.elf"
    shutil.copyfile(image, elf)
    shutil.copyfile(image.with_suffix(".hex"), elf.with_suffix(".hex"))
    descriptor = root / "Flight.ssdiag"
    descriptor.write_text(json.dumps(ProjectDescriptor_Create("Synthetic", TARGET)))
    hooks = eide.EideHooks_Create()
    for key in ("beforeBuildTasks", "afterBuildTasks"):
        command = hooks[key][0]["command"]
        for name, value in {"ProjectRoot": str(root), "OutDir": str(output),
                            "ProjectName": elf.stem}.items():
            command = command.replace("${" + name + "}", value)
        completed = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        assert completed.returncode == 0, completed.stderr
    assert Firmware_ImportAuto([descriptor]).result == DiagnosticResult.Ok


def test_unsupported_image_basename_stays_rejected(image):
    import shutil
    descriptor = entry(image)
    elf = image.with_name("unsafe image name.elf")
    shutil.copyfile(image, elf)
    shutil.copyfile(image.with_suffix(".hex"), elf.with_suffix(".hex"))
    with pytest.raises(DiagnosticError, match="safe sibling basename"):
        eide.EideDiagnostics_Bind(descriptor, elf)
    assert Firmware_ImportAuto([descriptor]).firmware is None
