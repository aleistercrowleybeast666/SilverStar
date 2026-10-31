"""Produce compact handoff evidence from completed, version-specific results."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
BASE = EVIDENCE.parent
read = lambda name: json.loads((EVIDENCE / name).read_text(encoding="utf8"))
commands = read("commands.json")
assert len(commands) == 6
coverage = read("coverage-audit.json")
placement = read("linked-placement-and-local-frames.json")
snapshot = read("source-snapshot.json")
metadata = read("coverage-metadata-post.json")
hosts = {}
mode_names = ("normal", "overflow", "startup-overflow", "startup-burst", "startup-burst-overload",
              "preflight-normal-30", "preflight-normal-120", "preflight-diagnostic-30", "preflight-diagnostic-120")
for name in ("h743", "f407"):
    host = read(name+"-storage-host-command.json")
    text = (EVIDENCE / (name+"-storage-host.log")).read_text(encoding="utf8")
    observations = [line for line in text.splitlines() if line.startswith("LOGGER_QUEUE_OBSERVED")]
    assert len(observations) == len(mode_names)
    host.update({"scope":"complete emitted storage_integrity runner, not complete make host-tests; logical sensor records, no physical epoch path",
        "logger_modes":dict(zip(mode_names, observations)),
        "dma_faults":[line for line in text.splitlines() if line.startswith("DISK_FAILURE")],
        "not_applicable":sorted({line for line in text.splitlines() if line.startswith("FCCG_HOST_NOT_APPLICABLE")}),
        "complete_marker":"FCCG_PROGRESS|STORAGE_INTEGRITY|DONE|4|4|logger-integrity" in text,
        "log_sha256":hashlib.sha256((EVIDENCE / (name+"-storage-host.log")).read_bytes()).hexdigest()})
    hosts[name] = host
artifact = (EVIDENCE / "artifact-check.log").read_text(encoding="utf8")
resource_lines = [line.strip() for line in artifact.splitlines() if any(token in line for token in
    ("FLASH     used=", "main SRAM used=", "CCMRAM    used=", "DTCM MSP", "heap      reserved=", "artifact check passed"))]
power = (EVIDENCE / "power10-check.log").read_text(encoding="utf8")
power_summary = [line for line in power.splitlines() if line.startswith("Power of Ten project text checks passed:")]
assert len(power_summary) == 1
stack = (EVIDENCE / "stack-report.log").read_text(encoding="utf8")
assert "Unreviewed H743 build declarations or configuration" in stack
pytest = (EVIDENCE / "pytest-final.log").read_text(encoding="utf8").strip().splitlines()[-1]
summary = {"source_commit":snapshot["git_head_at_generation"],"snapshot_sha256":snapshot["snapshot_sha256"],
    "final_output":".work/0.1.3-treediagram-20261101/h7-storage-v6/final/Flight_Controller",
    "gate_exit_codes":{row["command"][-1]:row["exit_code"] for row in commands},
    "pytest":pytest,"storage_host":hosts,"power10":power_summary[0],
    "h7_first_party_files":coverage["h7_first_party_files"],"f407_first_party_files":coverage["f407_first_party_files"],
    "f407_make_and_coverage_unchanged":coverage["f407_make_unchanged"] and coverage["f407_power10_source_lines_identical"],
    "resources":resource_lines,"artifacts":placement["artifacts"],"scratch_symbol":placement["scratch_symbol"],
    "metadata_faults":metadata,"strict_stack":"FAIL: unreviewed new H743 build declarations; no whitelist changes",
    "critical_contract_review":"NOT PROVEN; tool text checks do not complete manual acceptance",
    "hardware":"NOT TESTED: no MCU, SD-card electrical/timing/cache, power-loss or flight qualification",
    "coverage_history":"v1-v4 P10/strict analyzer omitted canonical owner C; those passes do not qualify the new files. v5 probes exposed and fixed exact coverage, ABI/prototype and missing-metadata gaps; v6 is final.",
    "no_push":"SilverStar source/evidence commits are local; parent owns requested TreeDiagram publication."}
(EVIDENCE / "summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf8")
identity = {"source_commit":snapshot["git_head_at_generation"],"snapshot_sha256":snapshot["snapshot_sha256"],
    "full_snapshot_file_sha256":hashlib.sha256((EVIDENCE/"source-snapshot.json").read_bytes()).hexdigest(),
    "owning_sources_sha256":snapshot["sha256"],"git_status_at_generation":snapshot["git_status_at_generation"],
    "input_identity_audit_sha256":hashlib.sha256((EVIDENCE/"input-owner-audit.json").read_bytes()).hexdigest()}
(EVIDENCE / "compact-source-identity.json").write_text(json.dumps(identity,indent=2)+"\n",encoding="utf8")
index = []
for relative, patterns in (
    ("v1/pre-fix-host.log", ("blocking BSP transfers",)),
    ("v3/storage-host.log", ("drops=287", "FAIL line 545")),
    ("v5/probe-owner-analyzer.log", ("no previous prototype",)),
    ("v5/probe-power10.log", ("conditional compilation violation", "#if _USE_")),
    ("v4/power10-check.log", ("Power of Ten project text checks passed:",)),
    ("v6/power10-check.log", ("POWER10_SOURCE|FATFS", "Power of Ten project text checks passed:")),
    ("v6/stack-report.log", ("Unreviewed H743",)),
):
    path = BASE / relative
    content = path.read_bytes()
    text = content.decode("utf8",errors="replace")
    index.append({"path":relative,"sha256":hashlib.sha256(content).hexdigest(),
                  "lines":[{"line":number,"text":line} for number,line in enumerate(text.splitlines(),1)
                           if any(pattern in line for pattern in patterns)]})
for relative in ("v2/late-boundary-pre.json", "v3/late-boundary-results.json", "v4/coverage-precheck.json",
                 "v5/coverage-metadata-pre.json", "v6/late-boundary-final.json", "v6/coverage-metadata-post.json"):
    path = BASE / relative
    index.append({"path":relative,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                  "record":json.loads(path.read_text(encoding="utf8"))})
(EVIDENCE / "evidence-index.json").write_text(json.dumps(index,indent=2)+"\n",encoding="utf8")
print(json.dumps({"gate_exit_codes":summary["gate_exit_codes"],"pytest":pytest,"resources":resource_lines},indent=2))
