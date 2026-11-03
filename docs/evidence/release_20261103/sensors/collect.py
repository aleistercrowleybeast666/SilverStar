"""Freeze actual commands/results, generated identities, linked memory and residuals."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / ".work/release-20261103/sensors"
OUT = HERE / "final-v2"
CODE = "724030c4744886b148a55954bfe0580c575c9bff"


def hash_(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    result = dict(production_commit=CODE, cases={})
    for short, ver, gate_dir in (("f407","v5","frozen-v1"),("installation","v7","final-v2"),("h743","v7","final-v2")):
        dest=WORK/ver/short
        project=dest/"Flight_Controller"
        package=next(dest.glob("*.ssdecoder"))
        generated=(project/"Generated/project_sources.mk").read_bytes()
        rows=json.loads((HERE/gate_dir/(short+"-commands.json")).read_bytes())
        assert len(rows)==9 and all(r["exit_code"]==(2 if r["command"][-1]=="stack-report" else 0) for r in rows)
        active=json.loads((project/".fccg/ownership.json").read_bytes())["active_components"]
        identity={p.relative_to(dest).as_posix():hash_(p) for p in
            [dest/"SilverStar.ssproject",package,project/"Generated/project_sources.mk", project/"Makefile", project/".fccg/ownership.json"]}
        sizes={}
        for configuration in ("Release","Debug"):
            memory=next((project/"build/FCCG").glob(f"SilverStar_*/{configuration}/memory-report.json"))
            target=OUT/(short+"-"+configuration+"-memory.json")
            shutil.copyfile(memory,target)
            obj=json.loads(memory.read_bytes())
            sizes[configuration]=[dict(name=r["name"],used=r["used_bytes"],phys_free=r["physical_free_bytes"],
                budget_free=r["budget_free_bytes"]) for r in obj["regions"]]
        result["cases"][short]=dict(version=ver, active_components=active,identity=identity,
            gates=[dict(config=r["command"][-2],target=r["command"][-1],exit_code=r["exit_code"]) for r in rows],
            memory=sizes, logs=gate_dir, strict_complete=False)
    storage=ROOT/".work/dev013_mag_tf_20261103/v5/results.json"
    shutil.copyfile(storage,OUT/"calibration-storage.json")
    result["storage_status"]=json.loads(storage.read_bytes())["exit_code"]
    result["h743_runtime_host_exit"]=int((HERE/"h743-runtime-host-v7.exit").read_text())
    result["installation_fixed_host_exit"]=int((HERE/"installation-fixed-host-v7.exit").read_text())
    result["h743_runtime_claim"]="Selected runtime plus automatically invoked logger/storage integrity. Full emitted Host suite was not run."
    result["row_counts"]={"online_and_saved_profiles":8,"combined_sensor_native_and_generation":52,"calibration_gui_workflow":20,"storage_with_serial":49}
    result["limitations"]=["Strict whole-program stack refused on each build. No reviewed seal added.",
        "Critical contracts not proven globally. No MCU, physical GNSS, IMU, magnetometer, card, flight, time bound or electrical verification.",
        "Complete offline installation capture uses separate session/native boot and measurement-time proof. Online uses serviced IRQ/conversion brackets.",
        "Mixed configurable GNSS boot dynamics rejected with the actual instance ids and requested modes."]
    (OUT/"summary.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
    (HERE/"work-inventory.json").write_text(json.dumps(dict(purpose="Generated sensor test projects, synthetic I/O, compiler checks and model comparisons",
        owner="release-20261103/sensors",retained=str(HERE),cleanup="none performed",
        disposable_children=sorted(p.name for p in WORK.iterdir()),persistence=str(storage.parent.parent),
        preserved="Input H7 validated release project and installed board payloads are read-only; synthetic PE2/3 wiring has a separate fixture diff."),indent=2)+"\n",encoding="utf8")


if __name__=="__main__":
    main()
