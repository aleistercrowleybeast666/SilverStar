"""Generate isolated synthetic radio targets and record real emitted build gates."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "apps/FCCG/src"), str(REPO / "apps/FCCG/tests")]
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.validation import Project_Validate
from silverstar_fccg.project.radio_variants import EBYTE_VARIANTS
from ebyte_variant_fixture import RadioVariantFixture_Create, RadioVariantFixture_Apply


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--modules", nargs="*", default=list(EBYTE_VARIANTS))
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--host", action="store_true")
    args = parser.parse_args()
    output = (REPO / args.output).resolve()
    if not output.is_relative_to(REPO / ".work") or output.exists():
        raise ValueError("Evidence requires a new directory below repository .work")
    output.mkdir(parents=True)
    report = {"started_utc": datetime.now(timezone.utc).isoformat(), "commands": [], "targets": [],
              "qualification": "synthetic software evidence; hardware and flight unverified"}
    def save():
        (output / "evidence.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    def run(command, cwd, log):
        start = datetime.now(timezone.utc)
        with log.open("w", encoding="utf8", errors="replace") as stream:
            result = subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                    env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=900)
        report["commands"].append({"command": command, "cwd": str(cwd), "exit_code": result.returncode,
            "seconds": (datetime.now(timezone.utc) - start).total_seconds(), "log": str(log.relative_to(output)),
            "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()})
        save()
        print(log.name, result.returncode, flush=True)
        return result.returncode
    for tool in ("git", "gcc", "arm-none-eabi-gcc", "mingw32-make", "python"):
        executable = shutil.which(tool)
        if executable is None: raise ValueError("Required tool unavailable: " + tool)
        run([executable, "--version"], REPO, output / (tool + "-version.log"))
    report["source_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    report["dirty_status"] = subprocess.check_output(["git", "status", "--short"], cwd=REPO, text=True)
    paths = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "apps/FCCG", "tools/run_ebyte_radio_evidence.py"], cwd=REPO, text=True).splitlines()
    report["source_hashes"] = {path: hashlib.sha256((REPO / path).read_bytes()).hexdigest()
                                for path in paths if (REPO / path).is_file()}
    catalog = PluginCatalog(REPO / "apps/FCCG/plugins/builtin", REPO / "apps/FCCG/plugins/installed")
    catalog.Scan()
    seed_root = output / "seed"
    seed = RadioVariantFixture_Create(catalog, seed_root)
    make = shutil.which("mingw32-make")
    failures = 0
    for module in args.modules:
        if module not in EBYTE_VARIANTS: raise ValueError("Unknown variant: " + module)
        model = RadioVariantFixture_Apply(deepcopy(seed), module)
        validation = Project_Validate(model, catalog)
        assert validation.valid, validation.issues
        generated = TargetGeneration_Apply(model, catalog, WorkspacePolicy(seed_root),
            output / module, TargetScope.ALL, confirm_dangerous=True)
        for role in generated.targets:
            project = generated.project_root / role
            record = {"module": module, "role": role, "path": str(project),
                "configuration": model.Dictionary_Get(), "validation": [dict(level=item.level, code=item.code, message=item.message) for item in validation.issues]}
            report["targets"].append(record)
            stem = module + "-" + role
            if run([make, "-j4", "SHELL=cmd.exe", "CONFIG=Release", "all"], project, output / (stem + "-build.log")):
                failures += 1; continue
            failures += bool(run([make, "SHELL=cmd.exe", "CONFIG=Release", "architecture-check", "power10-check", "artifact-check"], project, output / (stem + "-gates.log")))
            if args.analyze:
                failures += bool(run([make, "-j4", "SHELL=cmd.exe", "CONFIG=Release", "static-analysis"], project, output / (stem + "-analysis.log")))
            if args.host:
                failures += bool(run([make, "SHELL=cmd.exe", "CONFIG=Release", "host-tests"], project, output / (stem + "-host.log")))
            record["artifact_hashes"] = {str(path.relative_to(project)): hashlib.sha256(path.read_bytes()).hexdigest()
                for suffix in ("*.elf", "*.bin", "*.map", "*.su") for path in (project / "build").rglob(suffix)}
            save()
    report["failures"] = failures
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    save()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
