"""Reproduce final TreeDiagram run -> SCG -> actual generated C/decoder checks."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[4]
TD = ROOT.parent / "TreeDiagram"
SCG = ROOT / "apps/SCG"
EVIDENCE = Path(__file__).resolve().parent
WORK = ROOT / ".work/0.1.3-treediagram-20261101/control-core-v2"
SOURCE = TD / "docs/evidence/20261101/final-examples"
sys.path[:0] = [str(SCG / "src"), str(TD / "src")]

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.log_decoder_profile import LogDecoderPackage_Verify
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.model import ProjectModel_Load, ProjectModel_Save
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.tuning_bundle import (
    TuningBundle_Read, TuningBundle_Preview, TuningBundle_Apply, TuningBundle_ControlCoreAttach,
)
from treediagram.algorithms.control import PidController, LqrController, Lqr_Solve
from treediagram.algorithms.native import Sdk_Identity


def Float32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def Write(name, value):
    (EVIDENCE / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


commands = []


def Run(name, command):
    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    (EVIDENCE / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
    commands.append({"name": name, "command": command, "cwd": str(ROOT),
                     "exit_code": result.returncode, "seconds": time.monotonic()-started})
    Write("commands.json", commands)
    if result.returncode:
        raise RuntimeError(name + " failed; see complete log")
    return result.stdout


def Main():
    WORK.mkdir(parents=True, exist_ok=False)
    (EVIDENCE / "inputs").mkdir(exist_ok=False)
    host = shutil.which("gcc")
    if not host:
        raise RuntimeError("Host GCC required")
    os.environ.setdefault("TREEDIAGRAM_CACHE", str(TD / ".test-tmp/sdk-cache"))
    Run("host-compiler-version", [host, "--version"])
    manifest = Sdk_Identity()
    if manifest["source_commit"] != "4f701b4a7822302dc0f4ac858549f7cc7fa4ba0e":
        raise RuntimeError("Final SDK source commit changed")
    Write("final-sdk-manifest.json", manifest)
    matrix = json.loads((SOURCE / "matrix.json").read_text(encoding="utf-8"))
    cases = {row["case"]: row for row in matrix["cases"]}
    shutil.copyfile(SOURCE / "matrix.json", EVIDENCE / "inputs/matrix.json")
    source_records = []
    for path in (TD / "examples/underline-pid.json", TD / "tools/verify_examples.py"):
        source_records.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    Write("provenance.json", {"silverstar_code_commit": manifest["source_commit"],
        "silverstar_evidence_head_before_run": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "tree_diagram_head_before_run": subprocess.check_output(["git", "-C", str(TD), "rev-parse", "HEAD"], text=True).strip(),
        "tree_diagram_state": "final content-addressed working tree; final commit pending",
        "python": sys.version, "source_records": source_records,
        "scope": "actual final run parameter adoption and generated Host consumer; no new ARM or hardware validation"})
    service = FccgService(SCG)
    outcomes = []
    for case in ("underline-pid", "pid", "lqr"):
        path = SOURCE / (case + ".sstuning.json")
        frozen = EVIDENCE / "inputs" / path.name
        shutil.copyfile(path, frozen)
        bundle = TuningBundle_Read(frozen)
        assert bundle["model_id"] == cases[case]["input_digest"]
        control = bundle["control_research"]
        kind = control["kind"]
        parameters = control["parameters"]
        original = ReferenceProject_Create("Actual_" + case.replace("-", "_"), catalog=service.catalog)
        original_value = original.Dictionary_Get()
        preview = TuningBundle_Preview(original, service.catalog, bundle)
        applied = TuningBundle_Apply(original, service.catalog, bundle)
        candidate = TuningBundle_ControlCoreAttach(applied, service.catalog, bundle)
        assert original.Dictionary_Get() == original_value
        preview["control_core_preview"] = {
            "before": original.algorithm_parameters.get("silverstar.algorithm.control." + kind),
            "after": candidate.algorithm_parameters["silverstar.algorithm.control." + kind],
            "runtime_dispatch": False,
        }
        Write(case + "-preview.json", preview)
        saved = WORK / (case + ".ssproject")
        ProjectModel_Save(candidate, saved, WorkspacePolicy(WORK))
        candidate = ProjectModel_Load(saved)
        Write(case + "-project.json", candidate.Dictionary_Get())
        destination = WORK / case
        generation = TargetGeneration_Apply(candidate, service.catalog, WorkspacePolicy(SCG), destination, TargetScope.FLIGHT)
        project = destination / "Flight_Controller"
        # Target naming is deliberately read from actual generated output.
        decoders = list(destination.glob("*.ssdecoder"))
        assert len(decoders) == 1
        decoder = decoders[0]
        decoder_manifest = LogDecoderPackage_Verify(decoder.read_bytes())
        with zipfile.ZipFile(decoder) as archive:
            semantics = json.loads(archive.read("project_semantics.json"))
        owners = {row["component"]: row for row in semantics["firmware_algorithm_parameters"]}
        expected_owners = {row["plugin_id"]: row["parameters"] for row in bundle["profiles"]}
        expected_owners["silverstar.algorithm.control." + kind] = [
            {"id": key, "value": value} for key, value in parameters.items()]
        comparisons = []
        print_lines = []
        for owner_id, requested in expected_owners.items():
            owner = service.catalog.Component_Get(owner_id)
            definitions = {row.parameter_id: row for row in owner.algorithm_parameters}
            decoded = {row["id"]: row for row in owners[owner_id]["parameters"]}
            assert owners[owner_id]["manifest_sha256"] == owner.ManifestSha256_Get()
            assert set(decoded) == {row["id"] for row in requested}
            for row in requested:
                definition = definitions[row["id"]]
                actual = definition.Value_Resolve(row["value"])
                found = decoded[row["id"]]
                assert found["value"] == actual
                assert found["unit"] == definition.unit and found["representation"] == definition.representation
                comparisons.append({"owner": owner_id, "id": row["id"], "input": row["value"],
                    "target": actual, "decoder": found["value"], "symbol": definition.generated_symbol,
                    "storage_type": found["storage_type"], "lifecycle": definition.lifecycle})
                print_lines.append(f'printf("{definition.generated_symbol}=%.9g\\n",(double){definition.generated_symbol});')
        if kind == "pid":
            controller = PidController(**parameters)
            expected_output = controller.Step(.01, 0., parameters["sample_period_s"])
            body = "ControlPidConfig c; ControlPidContext s; float y; if(ControlPid_ProjectConfigGet(&c)!=CONTROL_PID_OK || ControlPid_Start(&s,&c)!=CONTROL_PID_OK || ControlPid_Step(&s,&c,0.01f,0.0f,c.sample_period_s,&y)!=CONTROL_PID_OK) return 1;"
            for key in parameters:
                body += f'printf("CONFIG_{key}=%.9g\\n",(double)c.{key});'
        else:
            design = control["design"]
            solved = Lqr_Solve(design["a"], design["b"], design["q"], design["r"],
                dt_s=design["dt_s"], model_source=design["model_source"])
            assert solved.target_k.tolist() == design["k"]
            controller = LqrController(solved, output_limit=parameters["output_limit"])
            expected_output = controller.Step([.01, .02])
            body = "ControlLqrConfig c; float x[2]={0.01f,0.02f},y; if(ControlLqr_ProjectConfigGet(&c)!=CONTROL_LQR_OK || ControlLqr_Step(&c,x,&y)!=CONTROL_LQR_OK) return 1;"
            for key, field in (("k_angle", "gain[0]"), ("k_rate", "gain[1]"), ("output_limit", "output_limit")):
                body += f'printf("CONFIG_{key}=%.9g\\n",(double)c.{field});'
        assert controller.implementation_identity == bundle["implementation_identity"]
        body += 'printf("OUTPUT=%.9g\\n",(double)y);' + "".join(print_lines) + "return 0;"
        consumer = WORK / (case + "-consumer.c")
        consumer.write_text(f'#include <stdio.h>\n#include "project_algorithm_parameters.h"\n#include "control_{kind}_project.h"\nint main(void){{{body}}}\n', encoding="utf-8")
        core = project / f"Algorithm/Control/{kind.upper()}"
        binary = WORK / (case + "-consumer.exe")
        Run(case + "-consumer-compile", [host, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-fanalyzer",
            "-I"+str(core/"Inc"), "-I"+str(project/"Generated/Inc"),
            str(core/f"Src/control_{kind}.c"), str(core/f"Src/control_{kind}_project.c"), str(consumer), "-lm", "-o", str(binary)])
        output = Run(case + "-consumer-execute", [str(binary)])
        actual_output = dict(line.split("=", 1) for line in output.splitlines())
        for row in comparisons:
            number = float(actual_output[row["symbol"]])
            value = Float32(number) if row["storage_type"] == "float32" else int(number)
            assert value == row["target"]
            row["compiled_c_value"] = value
        for key, value in parameters.items():
            assert Float32(float(actual_output["CONFIG_" + key])) == Float32(value)
        assert Float32(float(actual_output["OUTPUT"])) == expected_output
        Write(case + "-values.json", comparisons)
        outcomes.append({"case": case, "bundle_sha256": hashlib.sha256(frozen.read_bytes()).hexdigest(),
            "model_id": bundle["model_id"], "run_id": bundle["run_id"],
            "implementation_identity": bundle["implementation_identity"], "generation_result": str(generation),
            "parameter_comparisons": len(comparisons), "decoder_sha256": hashlib.sha256(decoder.read_bytes()).hexdigest(),
            "generation_profile_sha256": decoder_manifest["generation_profile_sha256"],
            "host_sdk_control_output": expected_output, "generated_consumer_control_output": Float32(float(actual_output["OUTPUT"])),
            "original_project_unchanged": True, "deployment_ready": False, "result": "PASS"})
        Write("outcomes.json", outcomes)
        print(case, "PASS", len(comparisons), expected_output, flush=True)
    inventory = [{"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size,
                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "owner": "algorithm_sdk",
                  "purpose": "final actual-run parameter adoption validation; not a hardware candidate"}
                 for path in sorted(WORK.rglob("*")) if path.is_file()]
    Write("inventory.json", inventory)


if __name__ == "__main__":
    Main()
