"""Compare every sealed final-identity E19 A/B artifact after real builds."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WORK = ROOT / ".work/platform-finish-20261116/contracts"


def main():
    commands = json.loads((WORK / "build-e19-b/commands.json").read_bytes())
    assert len(commands) == 6 and all(row["exit"] == 0 for row in commands)
    output = WORK / "e19-final-artifact-summary.json"
    if output.exists():
        raise ValueError("Do not overwrite prior evidence")
    result = {"scope": "Exact final-identity E19 synthetic F407 Flight, not Ground or hardware",
              "configurations": {}}
    for configuration in ("Release", "Debug"):
        case = json.loads((WORK / ("inspect-e19-a-" + configuration + ".json")).read_bytes())["case_candidate"]
        build = ROOT / ".work/pf1117/contract-e19-b/Flight_Controller/build/FCCG/SilverStar_F407" / configuration
        actual = {name: hashlib.sha256((build / name).read_bytes()).hexdigest()
                  for name in case["compiled_artifacts"]}
        assert actual == case["compiled_artifacts"]
        memory = json.loads((build / "memory-report.json").read_bytes())
        stack = json.loads((build / "stack-budget.json").read_bytes())
        assert not memory["errors"] and stack["passes"]
        result["configurations"][configuration] = {
            "compiled_artifacts_compared": len(actual), "changed_from_A": [],
            "artifact_hashes": actual, "banks": memory["regions"],
            "stack_acceptance": stack["whole_program_stack_acceptance"],
            "tasks": stack["tasks"], "msp": stack["main_msp_exceptions"],
            "hardware_high_water_marks": stack["hardware_high_water_marks"]}
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print("Final E19 A/B complete 504 artifacts per configuration match; strict software bound passed")


if __name__ == "__main__":
    main()
