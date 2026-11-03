"""Recompile only a Host harness around the unchanged generated logger translation units."""

from pathlib import Path
import argparse, hashlib, json, os, subprocess
import shutil


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("host_log", type=Path)
    parser.add_argument("project", type=Path)
    parser.add_argument("new_output", type=Path)
    args = parser.parse_args()
    work = args.new_output.resolve()
    work.mkdir(parents=True, exist_ok=False)
    project = args.project.resolve()
    prefix = "FCCG_HOST_COMMAND|"
    rows = [
        json.loads(line[line.index(prefix) + len(prefix) :])
        for line in args.host_log.read_text(encoding="utf-8-sig").splitlines()
        if prefix in line
    ]
    command = next(
        row
        for row in reversed(rows)
        if any(s.endswith("test_logger_storage.c") for s in row)
    )
    wrapper = Path(__file__).with_name("export_test_volume.c").resolve()
    executable = work / "capture.exe"
    source = (project / "APP/Src/flight_task.c").read_bytes()
    begin = source.index(b"static LoggerBusResult FlightTask_MissionSnapshotIdentityBuild(")
    end = source.index(b"static LoggerBusResult FlightTask_MagCalibrationIdentityBuild(", begin)
    identity = source[begin:end].strip()
    if not identity.endswith(b"}") or identity.count(b"FlightTask_MissionSnapshotIdentityBuild(") != 1:
        raise ValueError("Unexpected generated identity builder")
    (work / "generated_identity_builder.inc").write_bytes(identity)
    print("flight_task_source_sha256", hashlib.sha256(source).hexdigest(),
          "identity_builder_sha256", hashlib.sha256(identity).hexdigest())
    fixture = next(Path(s) for s in command if s.endswith("test_logger_storage.c"))
    body = fixture.read_bytes()
    entry = b"int main(int argc, char **argv)"
    if body.count(entry) != 1:
        raise ValueError("Unexpected Host fixture entry point")
    (work / "test_logger_storage_capture.inc").write_bytes(
        body.replace(entry, b"static int StorageFixture_Main(int argc, char **argv)")
    )
    command = [
        str(wrapper) if s.endswith("test_logger_storage.c") else s for s in command
    ]
    command[1:1] = ["-I" + str(work), "-I" + str(fixture.parent)]
    command[command.index("-o") + 1] = str(executable)
    env = {**os.environ, "TEMP": str(work), "TMP": str(work)}
    (work / "compile-command.json").write_text(
        json.dumps(command, indent=2), encoding="utf8"
    )
    subprocess.run(command, cwd=project, env=env, check=True)
    package = next(project.glob("*.ssdecoder"))
    for scenario in ("writer", "objects", "valid-input"):
        directory = work / scenario
        directory.mkdir()
        cmd = [str(executable), "HOST_GENERATED.sslog"]
        if scenario == "objects":
            cmd.append("persistent-objects")
        with (directory / "run.log").open("w", encoding="utf8") as stream:
            subprocess.run(
                cmd,
                cwd=directory,
                env=env | ({"RC_HOST_VALID_INPUT": "1"} if scenario == "valid-input" else {}),
                stdout=stream,
                stderr=subprocess.STDOUT,
                check=True,
            )
        shutil.copyfile(package, directory / package.name)
        (directory / "input-hashes.json").write_text(json.dumps({
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()
            if p.name.startswith("snap") or p.suffix in (".ssdecoder", ".sslog")
        }, indent=2), encoding="utf8")
        print(scenario, {p.name: p.stat().st_size for p in directory.iterdir()})
    print("host_executable", hashlib.sha256(executable.read_bytes()).hexdigest())


if __name__ == "__main__":
    run()
