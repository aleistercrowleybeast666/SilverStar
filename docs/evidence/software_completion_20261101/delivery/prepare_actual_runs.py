"""Actual CLI producer -> TreeDiagram 10 ms runs -> run-bound tuning bundles."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

ROOT = Path(__file__).resolve().parents[4]
TD = ROOT.parent / "TreeDiagram"
UNDERLINE = ROOT.parent / "Underline_RETLDC"
EVIDENCE = Path(__file__).resolve().parent / "actual-runs-v1"
WORK = TD / ".qa/software-completion-20261101/research-runs-v1"
ENV = os.environ.copy()
ENV.update(PYTHONUTF8="1", TREEDIAGRAM_CACHE=str(
    TD / ".test-tmp/software-completion-20261101/sdk-cache-delivery-v1"))
COMMANDS = []


def Hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def Run(label, command, cwd):
    started = time.monotonic()
    result = subprocess.run(list(map(str, command)), cwd=cwd, env=ENV,
                            capture_output=True, text=True, encoding="utf8", errors="replace")
    (EVIDENCE / (label + ".log")).write_text(result.stdout + result.stderr, encoding="utf8")
    COMMANDS.append({"label": label, "command": list(map(str, command)), "cwd": str(cwd),
                     "exit": result.returncode, "seconds": time.monotonic() - started})
    (EVIDENCE / "commands.json").write_text(json.dumps(COMMANDS, indent=2) + "\n", encoding="utf8")
    print(label, result.returncode, flush=True)
    if result.returncode:
        raise RuntimeError(label + " failed; complete log retained")


def Main():
    EVIDENCE.mkdir(exist_ok=False)
    WORK.mkdir(parents=True, exist_ok=False)
    motor = WORK / "underline.tdmotor.json"
    fixture = UNDERLINE / "tests/fixtures/motor_test_package/v1/synthetic_positive.retldc.json"
    Run("underline-export", [UNDERLINE / ".venv/Scripts/python.exe", "-m", "underline_retldc.cli",
                             "export", fixture, motor], UNDERLINE)
    producer = json.loads(motor.read_text(encoding="utf8"))
    records = []
    for case, kind in (("pid", "pid"), ("lqr", "lqr"), ("underline-pid", "pid")):
        design = WORK / (case + ".json")
        run = WORK / (case + ".tdrun.json")
        bundle = EVIDENCE / (case + ".sstuning.json")
        cli = [TD / ".venv/Scripts/python.exe", "-m", "treediagram"]
        Run(case + "-example", [*cli, "example", design, "--controller", kind,
                                "--control-period-us", "10000"], TD)
        if case == "underline-pid":
            imported = WORK / (case + "-imported.json")
            Run(case + "-import", [*cli, "import-motor", design, motor, imported], TD)
            design = imported
        Run(case + "-check", [*cli, "check", design], TD)
        Run(case + "-run", [*cli, "run", design, run], TD)
        Run(case + "-export", [*cli, "export-parameters", run, bundle], TD)
        actual = json.loads(run.read_text(encoding="utf8"))
        exported = json.loads(bundle.read_text(encoding="utf8"))
        assert actual["status"] == "succeeded"
        assert actual["run_id"] == exported["run_id"]
        assert actual["input_digest"] == exported["model_id"]
        assert actual["design"]["control"]["period_us"] == 10000
        (EVIDENCE / (case + "-design.json")).write_bytes(design.read_bytes())
        records.append({"case": case, "design": str(design), "design_sha256": Hash(design),
                        "run": str(run), "run_sha256": Hash(run), "run_id": actual["run_id"],
                        "input_digest": actual["input_digest"], "summary": actual["summary"],
                        "rows": len(actual["rows"]), "bundle": str(bundle), "bundle_sha256": Hash(bundle),
                        "implementation_identity": exported["implementation_identity"]})
        (EVIDENCE / "results.json").write_text(json.dumps({"runs": records,
            "motor": {"path": str(motor), "sha256": Hash(motor),
                      "content_sha256": producer["content_sha256"], "source": str(fixture),
                      "scope": "synthetic fixture; no measured engine/flight qualification"}}, indent=2) + "\n",
            encoding="utf8")
    print("PASS: actual three-product CLI chain, three 10 ms runs", flush=True)


if __name__ == "__main__":
    Main()
