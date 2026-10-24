"""Reproduce small, already-reviewed F103RE/RF epoch binding regression inputs.

Replays a published or pinned-baseline normal-generation Flight header, renders the other inputs
from its saved project with the production generator, and actually compiles the
owning C unit. No checker registration is added. The current Flight header is
also compiled, compared and required to remain rejected until separately reviewed.
No target/hardware access, SDK copy or complete project materialization occurs.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import types
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCG = ROOT / "apps/SCG"
sys.path.insert(0, str(SCG / "src"))

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.generator.render import GeneratedFiles_Render
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.project.algorithm_parameters import AlgorithmParameters_Reconcile
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.model import ProjectModel_Parse

SOURCE = "System/Src/system_imu_epoch.c"
FLIGHT = "Generated/Inc/project_flight_config.h"
ARCHIVE = "docs/FCCG/platform/evidence/SF6_feature_tiers_compile/feature_tiers_compile_checkpoint.zip"
ARCHIVE_SHA = "b192afd4c6f30c20cb9216f289f91008b45c1e78cf40d1b69e22901fdb2977c8"
RENDER_COMMIT = "7896c1d09a7f9138c41cdac35beef38347d94b78"
RENDER_SHA = "91d2ac503cd0563315e50306555193aa8911dc2902895e5c4865fef0cf60066f"


def Digest_Get(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def Fixture_Reproduce(output: Path, compiler: str, target: str = "SilverStar_F103RE") -> dict:
    output = output.resolve()
    if output.exists():
        raise ValueError("Use a new task-owned output directory")
    archive = ROOT / ARCHIVE
    if Digest_Get(archive.read_bytes()) != ARCHIVE_SHA:
        raise ValueError("Published generation archive changed")
    variant = {"SilverStar_F103RE": "ret6", "SilverStar_F103RF": "rft6"}[target]
    prefix = "generated/" + variant + "/"
    with zipfile.ZipFile(archive) as bundle:
        saved = bundle.read(prefix + "SilverStar.ssproject")
        historical = bundle.read(prefix + FLIGHT)
    service = FccgService(SCG)
    model = ProjectModel_Parse(json.loads(saved))
    if variant == "rft6":
        model = ProjectConfiguration_Reconcile(model, service.catalog).model
    catalog = service.catalog.ProjectView_Get(model)
    AlgorithmParameters_Reconcile(model, catalog)
    graph = SourceGraph_Resolve(model, catalog)
    generated = GeneratedFiles_Render(model, catalog, graph)
    assert model.mcu == "silverstar.mcu.stm32f103" + variant
    assert model.build.target_profile == target
    assert SOURCE in graph.sources and "-mcpu=cortex-m3" in graph.mcu_flags
    assert b"#define SYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED 1U" in generated[
        "Generated/Inc/project_device_build_capabilities.h"]
    tool = SCG / "plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_task_stacks.py"
    spec = importlib.util.spec_from_file_location("epoch_fixture_checker", tool)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    renderer_evidence = None
    if variant == "ret6":
        # Recover the original target using the exact repository baseline's
        # normal renderer. Never edit generated text to hunt an accepted hash.
        # Only verified first-party source from this pinned commit is executed.
        command = ["git", "show", RENDER_COMMIT + ":apps/SCG/src/silverstar_fccg/generator/render.py"]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=30)
        if result.returncode or Digest_Get(result.stdout) != RENDER_SHA:
            raise ValueError("Pinned historical normal renderer unavailable or changed")
        baseline = types.ModuleType("silverstar_fccg.generator.epoch_baseline_render")
        baseline.__package__ = "silverstar_fccg.generator"
        baseline.__file__ = str(SCG / "src/silverstar_fccg/generator/render.py")
        exec(compile(result.stdout, baseline.__file__, "exec"), baseline.__dict__)
        historical = baseline._FlightConfigHeader_Render(model, catalog).encode("utf8")
        renderer_evidence = dict(commit=RENDER_COMMIT, sha256=RENDER_SHA, command=command)
    normalized = historical.decode("utf8").replace("\r\n", "\n")
    assert checker.BindingSourceHash_Get(normalized) in checker.BindingSourceVersions_Get(FLIGHT)

    payload, origins = {}, {}
    for component in model.ComponentIds_Get():
        manifest = catalog.Component_Get(component)
        for source in manifest.PayloadFiles_Get():
            relative = source.relative_to(manifest.payload_root).as_posix()
            if relative in payload and payload[relative] != source.read_bytes():
                raise ValueError("Ambiguous source owner: " + relative)
            payload[relative] = source.read_bytes()
            origins[relative] = source.relative_to(ROOT).as_posix()
    payload.update(generated)
    current_flight = payload[FLIGHT]
    payload[FLIGHT] = historical
    selected = {}
    pending = [SOURCE, *graph.forced_includes]
    while pending:
        relative = pending.pop(0)
        if relative in selected:
            continue
        raw = payload[relative]
        selected[relative] = raw
        for include in re.findall(r'^\s*#\s*include\s*"([^"\n]+)"', raw.decode("utf8"), re.M):
            candidates = [(Path(relative).parent / include).as_posix()]
            candidates += [(Path(directory) / include).as_posix() for directory in graph.include_dirs]
            resolved = next((name for name in candidates if name in payload), None)
            if resolved is None:
                raise ValueError("Missing normal source-graph input: " + include)
            pending.append(resolved)
    for relative, raw in selected.items():
        destination = output / relative
        destination.resolve().relative_to(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    build = output / "build/FCCG" / target / "Release"
    obj = build / Path(SOURCE).with_suffix(".o")
    obj.parent.mkdir(parents=True)
    common = [compiler, *graph.mcu_flags, *("-D" + value for value in graph.defines),
              *("-I" + value for value in graph.include_dirs)]
    for include in graph.forced_includes:
        common += ["-include", include]
    common += ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-fstack-usage",
               "-ffunction-sections", "-fdata-sections"]
    records = []

    def run(arguments: list[str]) -> str:
        result = subprocess.run(arguments, cwd=output, capture_output=True, text=True, timeout=60)
        records.append(dict(command=arguments, exit_code=result.returncode,
                            stdout=result.stdout, stderr=result.stderr))
        (output / "commands.json").write_text(json.dumps(records, indent=2), encoding="utf8")
        if result.returncode:
            raise ValueError(result.stderr or result.stdout)
        return result.stdout

    version = run([compiler, "--version"]).splitlines()[0]
    run([*common, "-g3", "-gdwarf-4", "-MMD", "-MP", "-MF", obj.with_suffix(".d").relative_to(output).as_posix(),
         "-c", SOURCE, "-o", obj.relative_to(output).as_posix()])
    proof = checker.BindingSources_Verify(output, [SOURCE], build)
    old_preprocessed = run([*common, "-E", "-P", SOURCE])
    # Only this test-owned header changes. Restore it in finally even on error.
    try:
        (output / FLIGHT).write_bytes(current_flight)
        new_preprocessed = run([*common, "-E", "-P", SOURCE])
        run([*common, "-c", SOURCE, "-o", "current_epoch.o"])
        try:
            checker.BindingSources_Verify(output, [SOURCE], build)
        except ValueError as exc:
            current_rejection = str(exc)
        else:
            raise ValueError("Unreviewed generated configuration unexpectedly accepted")
    finally:
        (output / FLIGHT).write_bytes(historical)
    if old_preprocessed != new_preprocessed:
        raise ValueError("New configuration changes epoch translation-unit tokens; review required")
    dependency = obj.with_suffix(".d").read_text(encoding="utf8")
    names = dependency.split(":", 1)[1].replace("\\\n", " ").split("\n", 1)[0].split()
    assert set(names) == set(selected)
    fixture = dict(format="silverstar.compiler-input-fixture/1", target=target,
        source=SOURCE, compiler=version, archive=ARCHIVE, archive_sha256=ARCHIVE_SHA,
        saved_project_entry=prefix + "SilverStar.ssproject",
        flight_header_entry=prefix + FLIGHT if variant == "rft6" else None,
        historical_renderer=renderer_evidence,
        purpose="Historical " + target + " provider-input integrity regression, not a complete firmware stack proof",
        dependency=dependency, proof=proof, checker_sha256=Digest_Get(tool.read_bytes()),
        current_generated_header_rejected=current_rejection, preprocessed_epoch_tokens_equal=True,
        current_generated_flight_header=dict(text=current_flight.decode("utf8"),
                                            sha256=Digest_Get(current_flight)),
        inputs={name: dict(text=raw.decode("utf8"), sha256=Digest_Get(raw),
                          origin=(ARCHIVE + "!" + prefix + FLIGHT if variant == "rft6" else
                                  "pinned normal renderer " + RENDER_COMMIT) if name == FLIGHT else
                          origins.get(name, "production GeneratedFiles_Render"))
                for name, raw in sorted(selected.items())})
    (output / "fixture.json").write_text(json.dumps(fixture, indent=2), encoding="utf8")
    (output / "saved_project.json").write_bytes(saved)
    (output / "current_flight_config.h").write_bytes(current_flight)
    return fixture


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compiler", default="arm-none-eabi-gcc")
    parser.add_argument("--target", choices=("SilverStar_F103RE", "SilverStar_F103RF"), default="SilverStar_F103RE")
    args = parser.parse_args()
    fixture = Fixture_Reproduce(args.output, args.compiler, args.target)
    print(json.dumps(dict(target=fixture["target"], files=len(fixture["inputs"]),
                          input_bytes=sum(len(item["text"].encode()) for item in fixture["inputs"].values()),
                          accepted=True, current_generated_header_rejected=True,
                          preprocessed_epoch_tokens_equal=True)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
