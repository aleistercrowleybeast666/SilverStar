from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from tools.sslog_audit import (
    Audit_Bytes,
    Audit_CandidatesScan,
    Audit_FieldsRead,
    Audit_ProfileLoad,
)


@pytest.fixture(scope="module")
def storage_project(tmp_path_factory):
    root = Path(__file__).resolve().parents[1]
    compiler = shutil.which("gcc")
    if compiler is None:
        pytest.skip("Host GCC unavailable")
    project = tmp_path_factory.mktemp("storage-integrity")
    service = FccgService(root)
    service.Project_Save(service.ReferenceProject_Create("StorageRegression"), project,
                         confirm_dangerous=True)
    runner = project / "Tests/Host/storage_integrity/run_storage_integrity.py"
    output = project / "build/FCCG/Host/Tests/StorageIntegrity"
    result = subprocess.run([sys.executable, str(runner), "--project", str(project),
                             "--compiler", compiler], cwd=project,
                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                            capture_output=True, text=True, timeout=300,
                            check=False)
    WorkspacePolicy(project).Text_AtomicWrite(
        output / "integrity.log", result.stdout + result.stderr
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return project, output


def test_real_fatfs_delayed_dma_logger_and_queue(storage_project):
    project, output = storage_project
    catalog, hashes = Audit_ProfileLoad(project / "StorageRegression.ssdecoder")
    mixed = Audit_Bytes((output / "mixed.sslog").read_bytes(), catalog)
    assert mixed["passed"] and mixed["records"] == 40000
    assert mixed["record_counts"]["ALIGNMENT_EVIDENCE"] > 0
    assert mixed["record_counts"]["MISSION_SNAPSHOT_IDENTITY"] > 0
    assert mixed["record_counts"]["MAG_CALIBRATION_IDENTITY"] > 0
    normal = Audit_Bytes((output / "logger-normal.sslog").read_bytes(), catalog, decoder_hashes=hashes)
    # Startup suppresses a bounded number of native records until the logger
    # and mission snapshot are ready; the remaining sustained stream must be
    # intact and free of queue drops.
    assert normal["passed"] and normal["records"] >= 39900
    assert normal["queue_overflow_max"] == 0 and normal["sequence_gap_records"] == 0
    dropped = Audit_Bytes((output / "logger-overflow.sslog").read_bytes(), catalog,
                          decoder_hashes=hashes, allow_queue_drops=True)
    assert dropped["passed"] and dropped["sequence_gap_records"] > 0
    assert dropped["sequence_gap_records"] == dropped["queue_overflow_max"]
    assert dropped["sequence_reorders"] == 0
    startup = Audit_Bytes((output / "logger-startup-overflow.sslog").read_bytes(), catalog,
                          decoder_hashes=hashes, allow_queue_drops=True)
    assert startup["passed"] and startup["queue_overflow_max"] > dropped["queue_overflow_max"]
    assert startup["record_counts"]["DECODER_PROFILE_DESCRIPTOR"] == 1
    for report in (normal, dropped):
        assert report["unvalidated_tail_bytes"] == 0
        assert {"IMU_CORRECTED", "GNSS_NATIVE", "BARO_NATIVE",
                "ALIGNMENT_RESULT", "CALIBRATION_RESULT", "MISSION_CONFIG", "INITIAL_STATE",
                "EVENT", "STATS", "ESTIMATOR"} <= set(report["record_counts"])
    wrong_hashes = dict(hashes, record_catalog_hash_128="00" * 16)
    assert not Audit_Bytes((output / "logger-normal.sslog").read_bytes(), catalog,
                           decoder_hashes=wrong_hashes)["passed"]


def test_default_200hz_startup_and_overload_recovery(storage_project):
    project, output = storage_project
    catalog, hashes = Audit_ProfileLoad(project / "StorageRegression.ssdecoder")
    for mode in ("startup-burst", "startup-burst-overload"):
        report = Audit_Bytes((output / f"logger-{mode}.sslog").read_bytes(), catalog,
                             decoder_hashes=hashes, allow_queue_drops=mode.endswith("overload"))
        assert report["passed"] and report["integrity_ok"]
        assert report["unvalidated_tail_bytes"] == 0
        assert report["sequence_reorders"] == 0
        assert report["sequence_gap_records"] == report["queue_overflow_max"]
        assert (report["queue_overflow_max"] > 0) == mode.endswith("overload")
        counts = report["record_counts"]
        assert "KF6_DIAGNOSTIC" not in counts and "KF6_FULL_P" not in counts
        assert counts["CALIBRATION_RESULT"] == counts["ALIGNMENT_RESULT"] == 1
        assert counts["INITIAL_STATE"] == counts["MISSION_CONFIG"] == 1
        assert counts["SYSTEM_CONFIG"] == 2  # Bootstrap and actual START configuration.
        assert counts["DECODER_PROFILE_DESCRIPTOR"] == 1
        assert {"BARO_NATIVE", "GNSS_NATIVE", "POWER",
                "IMU_CORRECTED", "INERTIAL_INCREMENT", "ESTIMATOR_STEP", "GNSS_RECOVERY",
                "ESTIMATOR", "GNSS_MEASUREMENT",
                "BARO_MEASUREMENT", "STATS", "TELEMETRY_DIAG", "HEALTH"} <= set(counts)
        assert not {"SAMPLE", "RAW_SENSOR", "IMU_NATIVE", "HW_QUAT_NATIVE", "PURE_INS"}.intersection(counts)
        if not mode.endswith("overload"):
            # Exactly 194 seconds after START: 200 Hz corrected input, 100 Hz
            # generated/consumed increments, 25 Hz GNSS epochs, 25/5 Hz snapshots.
            assert counts["IMU_CORRECTED"] == 38800
            assert counts["INERTIAL_INCREMENT"] == counts["ESTIMATOR_STEP"] == 19400
            assert counts["BARO_NATIVE"] == 38800
            assert counts["BARO_MEASUREMENT"] == 19400
            assert counts["GNSS_NATIVE"] == counts["GNSS_MEASUREMENT"] == 4850
            assert counts["GNSS_RECOVERY"] == 4850
            assert counts["ESTIMATOR"] == 4850


CASES = json.loads((Path(__file__).parent / "fixtures/sslog_corruption_cases.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_strict_audit_synthetic_corruption(storage_project, case):
    project, output = storage_project
    catalog, _ = Audit_ProfileLoad(project / "StorageRegression.ssdecoder")
    complete = (output / "mixed.sslog").read_bytes()
    end = 64
    while end < 4096:
        end += 28 + struct.unpack_from("<H", complete, end + 6)[0]
    data = bytearray(complete[:end])  # Small fixture from the real C writer.
    operation = case["operation"]
    position = case.get("offset", 0)
    if operation == "duplicate_previous_byte":
        data[position:position] = data[position - 1:position]
    elif operation == "remove_byte":
        del data[position]
    elif operation == "flip_byte":
        data[position] ^= 0x80
    elif operation == "oversize_first_record":
        struct.pack_into("<H", data, 70, 0xFFFF)
    elif operation == "append_byte":
        data += b"\xFF"
    elif operation == "skip_sequence":
        position = 64
        while position < len(data):
            length = 28 + struct.unpack_from("<H", data, position + 6)[0]
            sequence = struct.unpack_from("<I", data, position + 8)[0]
            if sequence >= 2:
                struct.pack_into("<I", data, position + 8, sequence + case["missing_records"])
                struct.pack_into("<I", data, position + length - 4,
                                 zlib.crc32(data[position:position + length - 4]))
            position += length
    else:
        raise AssertionError(operation)
    report = Audit_Bytes(bytes(data), catalog, allow_queue_drops=True)
    assert not report["passed"]
    if "expected_error" in case:
        assert report["errors"][0]["kind"] == case["expected_error"]
        assert report["unvalidated_tail_bytes"] > 0
    else:
        assert report["integrity_ok"]
        assert report["sequence_gap_records"] == case["missing_records"]
        assert not report["queue_drop_accounted"]
    if "signature" in case:
        assert case["signature"] in {signature["kind"] for signature in report["boundary_signatures"]}
        forensic = Audit_CandidatesScan(bytes(data), catalog)
        assert forensic["valid_crc_candidates"] > report["records"]
        assert forensic["errors"]["bad_crc"] > 0


def test_storage_sources_survive_reference_reimport(monkeypatch, workspace_root):
    import tools.import_reference_components as importer

    monkeypatch.setattr(importer, "_ManifestValues_Get", lambda *_: [])
    components = {item["manifest"]["id"]: item for item in importer._Components_Get(
        Path("unused"), {"commit": "fixture", "snapshot_digest": "fixture"})}
    core = components["silverstar.core.0_1_0"]
    for relative in ("APP/Src/logger_bus.c", "APP/Src/logger_task.c", "APP/Inc/logger_bus.h",
                     "APP/Inc/logger_task.h", "Interfaces/Inc/system_storage_if.h",
                     "Tests/Host/storage_integrity/test_storage_integrity.c",
                     "Tests/Host/storage_integrity/test_logger_storage.c",
                     "Tests/Host/storage_integrity/run_storage_integrity.py",
                     "Tests/Host/test_logger.c", "Tests/Host/test_lifecycle_logging.c",
                     "Tests/Target/storage_integrity.c", "Tools/sslog_audit.py"):
        source = workspace_root / core["fccg_owned_files"][relative]
        assert source.is_file()
        assert source.read_bytes() == (workspace_root / "plugins/builtin/silverstar_core_0_1_0/payload" / relative).read_bytes()
    board = components["silverstar.board.silverstar_0_5"]
    ffconf = "FATFS/Target/ffconf.h"
    assert board["fccg_owned_files"][ffconf].endswith("payload/FATFS/Target/ffconf.h")
    assert (workspace_root / board["fccg_owned_files"][ffconf]).is_file()
    for component in components.values():
        if component["manifest"]["id"].startswith("silverstar.board."):
            for relative in ("sd_diskio.c", "bsp_driver_sd.c"):
                overlay = component["overlay_files"]["FATFS/Target/" + relative]
                assert (workspace_root / "tools/reference_overlays" / overlay).read_bytes() == (
                    workspace_root / "plugins/builtin/silverstar_board_silverstar_0_5/payload/FATFS/Target" / relative).read_bytes()
        if component["manifest"]["id"].startswith("silverstar.device.storage."):
            owned = component["fccg_owned_files"]
            assert set(owned) == {
                "Devices/Storage/SdSdioFatFs/Src/storage_service.c",
                "Devices/Storage/SdSdioFatFs/Src/log_sink_service.c",
                "Devices/Storage/SdSdioFatFs/Src/persistent_storage.c",
                "Devices/Storage/SdSdioFatFs/Src/fatfs_lfn_ascii.c",
                "Devices/Storage/SdSdioFatFs/Inc/persistent_storage.h",
            }
            assert all((workspace_root / path).is_file() for path in owned.values())


def test_protocol_layout_is_unchanged(workspace_root):
    path = workspace_root / "plugins/builtin/silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG/schema/sslog_schema.json"
    catalog, _ = Audit_ProfileLoad(path)
    mission = next(record for record in catalog["records"] if record["name"] == "MISSION_CONFIG")
    assert mission["payload_size"] == 91 and mission["version"] == 0
    assert 24 + mission["payload_size"] + 4 == 119


def test_sparse_preflight_producers_start_boundary_and_diagnostic_override(storage_project):
    project, output = storage_project
    header = (project / "System/User/system_user_config.h").read_text()
    import re
    for macro in ("SYSTEM_LOG_PREFLIGHT_NATIVE_ENABLE", "SYSTEM_LOG_PREFLIGHT_CORRECTED_IMU_ENABLE"):
        assert re.search(r"#define\s+" + macro + r"\s+0U", header)
        assert "#ifndef " + macro in header
    catalog, hashes = Audit_ProfileLoad(project / "StorageRegression.ssdecoder")
    metadata = {(int(r["id"], 16), r["version"]): r for r in catalog["records"]}
    summaries = {}
    required = {"EVENT", "DECODER_PROFILE_DESCRIPTOR", "SYSTEM_CONFIG", "DEVICE_DESCRIPTOR",
                "ALGORITHM_DESCRIPTOR", "LOG_STREAM_DESCRIPTOR", "CALIBRATION_RESULT",
                "ALIGNMENT_RESULT", "MISSION_CONFIG", "INITIAL_STATE"}
    high_rate = {"IMU_CORRECTED", "BARO_NATIVE", "GNSS_NATIVE"}
    for mode in ("normal", "diagnostic"):
        for seconds in (30, 120):
            data = (output / f"preflight-{mode}-{seconds}.sslog").read_bytes()
            report = Audit_Bytes(data, catalog, decoder_hashes=hashes)
            assert report["passed"] and report["sequence_gap_records"] == 0
            assert report["queue_overflow_max"] == 0 and report["unvalidated_tail_bytes"] == 0
            assert required <= set(report["record_counts"])
            records = []
            offset = 64
            while offset < len(data):
                length = 28 + struct.unpack_from("<H", data, offset + 6)[0]
                info = metadata[(data[offset + 5], data[offset + 4])]
                timestamp = struct.unpack_from("<Q", data, offset + 12)[0]
                fields = Audit_FieldsRead(data[offset + 24:offset + length - 4], info)
                records.append((info["name"], timestamp, fields, length))
                offset += length
            start = next(t for name, t, fields, _ in records
                         if name == "EVENT" and int.from_bytes(fields["event_id"], "little") == 3)
            landing = next(t for name, t, fields, _ in records
                           if name == "EVENT" and int.from_bytes(fields["event_id"], "little") == 0x2A)
            assert landing - start == 20_000_000
            assert any(name == "INITIAL_STATE" and t == start for name, t, _, _ in records)
            for name in high_rate:
                times = [t for n, t, _, _ in records if n == name]
                assert start in times  # Producer dedup has not consumed the first START sample.
                assert (min(times) < start) == (mode == "diagnostic")
            for name in ("IMU_CORRECTED",):
                times = [t for n, t, _, _ in records if n == name and start <= t < landing]
                assert times == list(range(start, landing, 10000))
            for name in ("ESTIMATOR", "KF6_DIAGNOSTIC", "KF6_FULL_P", "INERTIAL_INCREMENT",
                         "BARO_MEASUREMENT", "GNSS_MEASUREMENT", "PURE_INS"):
                assert any(n == name and t == start for n, t, _, _ in records)
            preflight = [r for r in records if r[1] < start]
            summaries[f"{mode}-{seconds}"] = {
                "file_bytes": len(data), "records": report["records"],
                "preflight_bytes": 64 + sum(r[3] for r in preflight),
                "preflight_records": len(preflight), "counts": report["record_counts"],
            }
    for name in high_rate:
        assert summaries["normal-30"]["counts"][name] == summaries["normal-120"]["counts"][name]
        assert summaries["diagnostic-120"]["counts"][name] > summaries["diagnostic-30"]["counts"][name]
    assert summaries["normal-120"]["preflight_bytes"] < summaries["diagnostic-120"]["preflight_bytes"] / 10
    (output / "preflight-comparison.json").write_text(json.dumps(summaries, indent=2))
