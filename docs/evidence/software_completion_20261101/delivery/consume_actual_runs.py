"""Actual SCG CLI Preview/Apply, fresh generation, decoder and C torque consumer."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[4]
TD = ROOT.parent / "TreeDiagram"
SCG = ROOT / "apps/SCG"
INPUT = Path(__file__).resolve().parent / "actual-runs-v1"
EVIDENCE = Path(__file__).resolve().parent / "consumer-v1"
WORK = ROOT / ".work/0.1.3-software-completion-20261101/delivery/consumer-v1"
sys.path[:0] = [str(SCG / "src"), str(TD / "src")]
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.log_decoder_profile import LogDecoderPackage_Verify
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.model import ProjectModel_Load, ProjectModel_Save
from silverstar_fccg.project.reference import ReferenceProject_Create
from treediagram.algorithms.control import PidController, LqrController, Lqr_Solve

ENV = os.environ.copy()
ENV.update(PYTHONUTF8="1", PYTHONPATH=str(SCG / "src"))
os.environ["TREEDIAGRAM_CACHE"] = str(TD / ".test-tmp/software-completion-20261101/sdk-cache-delivery-v1")
COMMANDS = []


def Hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def Write(name, value):
    (EVIDENCE / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf8")


def Run(label, command, cwd=ROOT):
    started = time.monotonic()
    result = subprocess.run(list(map(str, command)), cwd=cwd, env=ENV,
                            capture_output=True, text=True, encoding="utf8", errors="replace")
    (EVIDENCE / (label + ".log")).write_text(result.stdout + result.stderr, encoding="utf8")
    COMMANDS.append({"label": label, "command": list(map(str, command)), "cwd": str(cwd),
                     "exit": result.returncode, "seconds": time.monotonic() - started})
    Write("commands.json", COMMANDS)
    print(label, result.returncode, flush=True)
    if result.returncode:
        raise RuntimeError(label + " failed; complete log retained")
    return result.stdout


def Main():
    EVIDENCE.mkdir(exist_ok=False)
    WORK.mkdir(parents=True, exist_ok=False)
    service = FccgService(SCG)
    results = []
    candidates = {}
    for case in ("pid", "lqr", "underline-pid"):
        bundle_path = INPUT / (case + ".sstuning.json")
        bundle = json.loads(bundle_path.read_text(encoding="utf8"))
        kind = bundle["control_research"]["kind"]
        base = ReferenceProject_Create("SoftwareCompletion_" + kind.upper(), catalog=service.catalog)
        base_path = WORK / (case + "-base.ssproject")
        candidate_path = WORK / (case + ".ssproject")
        ProjectModel_Save(base, base_path, WorkspacePolicy(WORK))
        before = Hash(base_path)
        cli = [ROOT / ".venv/Scripts/python.exe", "-m", "silverstar_fccg.project.tuning_bundle"]
        preview = json.loads(Run(case + "-preview", [*cli, "preview", base_path, bundle_path,
                                                     "--include-control-task"]))
        assert preview["control_task_preview"]["runtime_dispatch"] is True
        assert preview["control_task_preview"]["electrical_output"] is False
        assert Hash(base_path) == before and not candidate_path.exists()
        Run(case + "-apply", [*cli, "apply", base_path, bundle_path, "--include-control-task",
                              "--output", candidate_path])
        assert Hash(base_path) == before
        candidate = ProjectModel_Load(candidate_path)
        if case == "underline-pid":
            assert candidate.Dictionary_Get() == candidates["pid"]
        else:
            candidates[case] = candidate.Dictionary_Get()
        Write(case + "-model.json", candidate.Dictionary_Get())
        destination = WORK / case
        generation = TargetGeneration_Apply(candidate, service.catalog, WorkspacePolicy(SCG),
                                            destination, TargetScope.FLIGHT)
        project = destination / "Flight_Controller"
        contract = json.loads((project / "Generated/control_research.json").read_text(encoding="utf8"))
        assert contract["enabled"] and contract["period_us"] == 10000
        assert contract["output"] == {"quantity": "requested_body_y_torque", "axis": "body-Y",
                                      "unit": "N*m", "nm_per_core_output_unit": 1.0,
                                      "maximum_absolute_torque_nm": 1.0}
        assert contract["electrical_output"] is False and contract["deployable"] is False
        decoders = list(destination.glob("*.ssdecoder"))
        assert len(decoders) == 1
        decoder = decoders[0]
        LogDecoderPackage_Verify(decoder.read_bytes())
        with zipfile.ZipFile(decoder) as archive:
            semantics = json.loads(archive.read("project_semantics.json"))
        owners = {row["component"]: row for row in semantics["firmware_algorithm_parameters"]}
        requested = {row["plugin_id"]: {p["id"]: p["value"] for p in row["parameters"]}
                     for row in bundle["profiles"]}
        parameters = bundle["control_research"]["parameters"]
        requested["silverstar.algorithm.control." + kind] = parameters
        comparisons = []
        prints = []
        for owner_id, values in requested.items():
            owner = service.catalog.Component_Get(owner_id)
            assert owners[owner_id]["manifest_sha256"] == owner.ManifestSha256_Get()
            decoded = {row["id"]: row for row in owners[owner_id]["parameters"]}
            assert set(decoded) == set(values)
            for definition in owner.algorithm_parameters:
                key = definition.parameter_id
                actual = definition.Value_Resolve(values[key])
                assert decoded[key]["value"] == actual
                assert decoded[key]["unit"] == definition.unit
                assert decoded[key]["representation"] == definition.representation
                comparisons.append({"owner": owner_id, "id": key, "input": values[key],
                                    "target": actual, "decoder": decoded[key],
                                    "symbol": definition.generated_symbol, "lifecycle": definition.lifecycle})
                prints.append(f'printf("{definition.generated_symbol}=%.9g\\n",(double){definition.generated_symbol});')
        if kind == "pid":
            controller = PidController(**parameters)
            expected = controller.Step(0., .01, .01)
        else:
            design = bundle["control_research"]["design"]
            solved = Lqr_Solve(design["a"], design["b"], design["q"], design["r"],
                               dt_s=design["dt_s"], model_source=design["model_source"])
            assert solved.target_k.tolist() == design["k"]
            controller = LqrController(solved, output_limit=parameters["output_limit"])
            expected = controller.Step([.01, .002])
        assert controller.implementation_identity == bundle["implementation_identity"]
        source = WORK / (case + "-consumer.c")
        source.write_text('#include <stdio.h>\n#include "control_research.h"\n'
            '#include "project_algorithm_parameters.h"\nint main(void) { float limit, value; '
            'if(ControlResearchBackend_Start(&limit)!=ControlResearchResult_Ok || '
            'ControlResearchBackend_Step(0.01f,0.002f,&value)!=ControlResearchResult_Ok) return 1; '
            'printf("OUTPUT_NM=%.9g\\n",(double)value); printf("LIMIT_NM=%.9g\\n",(double)limit); '
            + "".join(prints) + 'return ControlResearchBackend_Stop()!=ControlResearchResult_Ok; }\n', encoding="utf8")
        core = project / f"Algorithm/Control/{kind.upper()}"
        binary = WORK / (case + "-consumer.exe")
        includes = [core / "Inc", *(project / name for name in (
            "Generated/Inc", "APP/Inc", "Interfaces/Inc", "System/Inc", "Platform/Inc"))]
        command = [shutil.which("gcc"), "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic", "-O2", "-fanalyzer",
                   *("-I" + str(p) for p in includes), core / f"Src/control_{kind}.c",
                   core / f"Src/control_{kind}_project.c", project / "Generated/Src/project_control_research.c",
                   source, "-lm", "-o", binary]
        Run(case + "-consumer-compile", command)
        output = dict(line.split("=", 1) for line in Run(case + "-consumer-run", [binary]).splitlines())
        assert abs(float(output["OUTPUT_NM"]) - expected) < 2e-7
        assert abs(float(output["LIMIT_NM"]) - parameters["output_limit"]) < 2e-7
        for row in comparisons:
            target = float(row["target"])
            if row["decoder"]["storage_type"] == "float32":
                target = struct.unpack("<f", struct.pack("<f", target))[0]
            assert abs(float(output[row["symbol"]]) - target) <= max(1e-8, abs(target) * 2e-8)
        results.append({"case": case, "bundle": str(bundle_path), "bundle_sha256": Hash(bundle_path),
                        "project": str(project), "model": str(candidate_path), "generation": str(generation),
                        "decoder": str(decoder), "decoder_sha256": Hash(decoder), "contract": contract,
                        "consumer_sha256": Hash(binary), "expected_nm": expected,
                        "actual_nm": float(output["OUTPUT_NM"]), "parameters": comparisons})
        Write("results.json", results)
    Write("scope.json", {"scope": "actual CLI transaction, decoder and generated C backend; full task/ARM/stack separate",
                         "underline_pid_model_equals_pid": True,
                         "rebuild": "Fresh ReferenceProject_Create with project name SoftwareCompletion_PID/LQR; actual bundle through TuningBundle_ControlTaskAttach. Never reuse stale component provenance."})
    print("PASS: three actual bundles, generated consumers and decoders", flush=True)


if __name__ == "__main__":
    Main()
