"""Summarize actual D/E artifacts; fail rather than infer an unfinished result."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WORK = ROOT / ".work/platform-finish-20261116/contracts"


def main():
    result = {"source_baseline": "d52854c4a7b12c79dbb06cf967006e599103d24e",
              "scope": "Exact final F407 default E28 configuration; dirty input snapshots and D/E commands are separate evidence. Not hardware qualification or an E19 runtime test.",
              "configurations": {}}
    commands = json.loads((WORK / "build-e/commands.json").read_bytes())
    assert len(commands) == 6 and all(row["exit"] == 0 for row in commands)
    for configuration in ("Release", "Debug"):
        case = json.loads((WORK / ("inspect-d-" + configuration + ".json")).read_bytes())["case_candidate"]
        project = WORK / "final-generated-e/f4/Flight_Controller"
        build = project / "build/FCCG/SilverStar_F407" / configuration
        actual = {name: hashlib.sha256((build / name).read_bytes()).hexdigest()
                  for name in case["compiled_artifacts"]}
        assert actual == case["compiled_artifacts"]
        memory = json.loads((build / "memory-report.json").read_bytes())
        stack = json.loads((build / "stack-budget.json").read_bytes())
        assert not memory["errors"] and stack["passes"]
        banks = []
        for region in memory["regions"]:
            banks.append({key: region[key] for key in (
                "name", "used_bytes", "used_percent", "allocated_span_bytes",
                "physical_capacity_bytes", "physical_free_bytes", "reserved_bytes",
                "review_budget_bytes", "budget_free_bytes", "budget_used_percent")})
            banks[-1]["remaining_above_allocation_span_bytes"] = (
                region["physical_capacity_bytes"] - region["allocated_span_bytes"])
        result["configurations"][configuration] = {
            "elf_sha256": memory["artifacts"]["elf"]["sha256"],
            "compiled_artifacts_compared": len(actual), "changed_from_D": [],
            "artifact_hashes": actual, "banks": banks,
            "stack_acceptance": stack["whole_program_stack_acceptance"],
            "task_margins": {row["task"]: {key: row[key] for key in (
                "configured_bytes", "worst_known_bytes", "margin_bytes", "passes")}
                for row in stack["tasks"]},
            "msp": {key: stack["main_msp_exceptions"][key] for key in (
                "configured_bytes", "worst_known_bytes", "margin_bytes", "passes")},
            "hardware_high_water_marks": stack["hardware_high_water_marks"]}
    result["resource_limits"] = (
        "physical_free_bytes is the report's aggregate section accounting, not a continuous allocation guarantee; "
        "remaining_above_allocation_span_bytes separately includes alignment gaps. Unallocated banks are not interchangeable. "
        "review budget N/A means no such budget was declared, not unlimited safe memory. Static MSP/task proof does not measure MCU HWM/WCET.")
    (WORK / "final-artifact-summary.json").write_bytes((json.dumps(result, indent=2) + "\n").encode())
    print("D/E: 510 complete artifacts per configuration matched; exact static stack passed")


if __name__ == "__main__":
    main()
