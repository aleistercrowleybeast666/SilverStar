"""Small reproducible software validation; no serial opens or firmware builds."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy
import scipy
import pytest
import PySide6


ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
TASK=REPO/".work/dev013_installation_calibration_20261018"
EXP=REPO/"apps/SCG/experiments/installation_calibration_0_1_3"
STREAM_EXP=REPO/"apps/SCG/experiments/installation_capture_stream_0_1_3"


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--run",required=True)
    parser.add_argument("--backend-only",action="store_true"); args=parser.parse_args()
    if not args.run.isascii() or not args.run.isalnum() or len(args.run)>24: parser.error("bounded run prefix")
    prefix=args.run+"_20261019_"; files=lambda suffix:TASK/(prefix+suffix)
    # Keep legacy Windows download-fixture paths below MAX_PATH. This is a new
    # owned directory, never an existing basetemp (pytest would remove one).
    temp=REPO/".work"/("ic013_"+args.run)
    if any(TASK.glob(prefix+"*")) or temp.exists(): parser.error("existing evidence preserved; choose new prefix")
    assert temp.resolve().is_relative_to((REPO/".work").resolve())
    targets=[ROOT/"tests/test_installation_calibration_backend.py",ROOT/"tests/test_installation_capture_contract.py"]
    if not args.backend_only:
        targets += [ROOT/"tests/test_magnetometer_workflow.py", ROOT/"tests/test_magnetometer_transport.py",
                    ROOT/"tests/test_maintenance_api.py",ROOT/"tests/test_file_service_owner_classification.py",
                    ROOT/"tests/test_release_layout.py", EXP,STREAM_EXP/"test_offline_proof.py"]
    owned=[REPO/"contracts/installation_calibration_v1.json",Path(__file__).resolve(),
           *list((ROOT/"services").glob("installation_calibration_*.py")),
           ROOT/"tests/test_installation_calibration_backend.py",ROOT/"tests/installation_calibration.ini",
           ROOT/"tests/test_installation_capture_contract.py",
           *[p for p in EXP.iterdir() if p.is_file() and p.suffix in (".py",".ini",".md")]]
    owned += [p for p in STREAM_EXP.iterdir() if p.is_file() and p.suffix in (".py",".c",".ld",".md")]
    snapshot={str(p.relative_to(REPO)):{"bytes_hex":p.read_bytes().hex(),"sha256":digest(p)} for p in owned}
    files("source.json").write_text(json.dumps(snapshot,indent=2)+"\n",encoding="utf-8")
    command=[sys.executable,"-B","-m","pytest","-c",str(ROOT/"tests/installation_calibration.ini"),
             *[str(p) for p in targets],"--basetemp",str(temp),"-q","-W","error"]
    env=dict(os.environ,PYTHONPATH=str(ROOT),PYTHONDONTWRITEBYTECODE="1",PYTHONIOENCODING="utf-8",QT_QPA_PLATFORM="offscreen",
             INSTALL_CAL_EVIDENCE=str(TASK),INSTALL_CAL_PREFIX=prefix)
    begin=time.monotonic()
    with files("pytest.log").open("w",encoding="utf-8") as stream:
        try: code=subprocess.run(command,cwd=REPO,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=180).returncode
        except subprocess.TimeoutExpired: code=124; stream.write("\nTEST_TIMEOUT_180_SECONDS\n")
    changed=[str(p.relative_to(REPO)) for p in owned if digest(p)!=snapshot[str(p.relative_to(REPO))]["sha256"]]
    if changed: code=125
    ui_before=json.loads((TASK/"software_baseline_20261019.json").read_text())["files"]
    ui_changed=[path for path,sha in ui_before.items() if digest(REPO/path)!=sha]
    if ui_changed: code=126
    metadata={"owner":"installation_calibration_software_20261019","purpose":"software/mock/replay only; no hardware",
              "command":command,"cwd":str(REPO),"exit_code":code,"seconds":time.monotonic()-begin,
              "python":sys.version,"numpy":numpy.__version__,"scipy":scipy.__version__,"pytest":pytest.__version__,
              "pyside6":PySide6.__version__,"platform":platform.platform(),
              "head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip(),
              "targets":[str(p.relative_to(REPO)) for p in targets],"changed_during_run":changed,
              "gui_changed":ui_changed,"temp_directory":str(temp.relative_to(REPO)),"cleanup_authorized":False}
    files("results.json").write_text(json.dumps(metadata,indent=2)+"\n",encoding="utf-8")
    generated=[p for p in TASK.glob(prefix+"*") if p.is_file()]+[p for p in temp.rglob("*") if p.is_file()]
    inventory=[{"path":str(p.relative_to(REPO)),"bytes":p.stat().st_size,"sha256":digest(p),
                "owner":metadata["owner"],"purpose":"retained synthetic software evidence","cleanup_authorized":False} for p in generated]
    files("inventory.json").write_text(json.dumps(inventory,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"exit_code":code,"seconds":metadata["seconds"],"gui_changed":ui_changed,
                      "evidence_bytes":sum(p["bytes"] for p in inventory),"log":str(files("pytest.log"))},indent=2))
    print("\n".join(files("pytest.log").read_text(encoding="utf-8").splitlines()[-80:]))
    return code


if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
