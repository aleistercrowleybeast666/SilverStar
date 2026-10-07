"""Read back named RF56 probe evidence; a known loss remains a strict failure.

This check proves only record/rate/snapshot/accounting observations. It never
turns an expected failing queue-loss case into zero-loss qualification.
"""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import struct


def RfActualRates_RecordsCheck(project: Path, attempt: Path) -> dict:
    spec = importlib.util.spec_from_file_location("rf_exact_audit", project / "Tools/sslog_audit.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    decoders = list(project.glob("*.ssdecoder"))
    assert len(decoders) == 1, "exact single generated decoder required"
    catalog, hashes = audit.Audit_ProfileLoad(decoders[0])
    definitions = {(int(row["id"], 16), row["version"]): row for row in catalog["records"]}
    formats = {"u8": "B", "i8": "b", "u16": "H", "i16": "h", "u32": "I", "i32": "i",
               "u64": "Q", "i64": "q", "f32": "f"}

    def decode(data):
        rows = []
        position = 64
        while position < len(data):
            size = struct.unpack_from("<H", data, position + 6)[0]
            meta = definitions[data[position + 5], data[position + 4]]
            raw = audit.Audit_FieldsRead(data[position + 24:position + 24 + size], meta)
            fields = {}
            for field in meta["fields"]:
                if field["type"] == "pad":
                    continue
                values = struct.unpack("<" + formats[field["type"]] * field.get("count", 1), raw[field["name"]])
                fields[field["name"]] = values[0] if len(values) == 1 else list(values)
            rows.append({"name": meta["name"], "timestamp_us": struct.unpack_from("<Q", data, position + 12)[0],
                         "sequence": struct.unpack_from("<I", data, position + 8)[0], "fields": fields})
            position += 28 + size
        assert position == len(data)
        return rows

    expected_counts = {"IMU_CORRECTED": 4800, "INERTIAL_INCREMENT": 2400, "BARO_NATIVE": 480,
                       "GNSS_NATIVE": 600, "SF6_MEASUREMENT": 2880, "SF6_STATE": 240}
    evidence = {}
    for name, expected_loss in (("baseline", 0), ("delay80", 1)):
        path = attempt / ("rf-actual-rates-" + name + ".sslog")
        data = path.read_bytes()
        strict = audit.Audit_Bytes(data, catalog, decoder_hashes=hashes)
        assert strict["integrity_ok"] and strict["decoder_match"] and not strict["errors"]
        assert strict["unvalidated_tail_bytes"] == 0 and strict["sequence_reorders"] == 0
        assert strict["passed"] == (expected_loss == 0)
        assert strict["sequence_gap_count"] == expected_loss == strict["queue_overflow_max"]
        rows = decode(data)
        counts = Counter(row["name"] for row in rows)
        for kind, count in expected_counts.items():
            assert counts[kind] == count, (kind, counts[kind], count)
        config_indices = [index for index, row in enumerate(rows) if row["name"] == "SYSTEM_CONFIG"]
        assert len(config_indices) == 2
        snapshot = rows[config_indices[1]:config_indices[1] + 58]
        assert [row["name"] for row in snapshot] == (["SYSTEM_CONFIG"] + ["DEVICE_DESCRIPTOR"] * 9 +
            ["ALGORITHM_DESCRIPTOR"] * 4 + ["LOG_STREAM_DESCRIPTOR"] * 40 +
            ["MISSION_CONFIG", "MISSION_SNAPSHOT_IDENTITY", "INITIAL_STATE", "EVENT"])
        # SSLOG event enum: BOOT=1, ALIGNMENT_COMPLETE=2, MISSION_START=3.
        assert snapshot[-1]["fields"]["event_id"] == 3
        config = snapshot[0]["fields"]
        assert [config[key] for key in ("configured_imu_rate_hz", "configured_gnss_rate_hz",
            "configured_barometer_rate_hz", "expected_ins_rate_hz", "normal_queue_depth",
            "estimator_queue_depth")] == [200, 25, 20, 100, 56, 16]
        streams = [row["fields"] for row in snapshot if row["name"] == "LOG_STREAM_DESCRIPTOR"]
        assert len({(stream["record_type"], stream["record_version"]) for stream in streams}) == 40
        assert sum(stream["enabled"] for stream in streams) == 21
        identity = snapshot[-3]["fields"]
        assert identity["ready"] == 1 and identity["mission_id"] == 1 and identity["commit_generation"] == 1
        assert snapshot[-2]["fields"]["p0_diagonal"] == config["p0_diagonal"]
        measurements = [row["fields"] for row in rows if row["name"] == "SF6_MEASUREMENT"]
        groups = Counter(row["group"] for row in measurements)
        assert sorted(groups.values()) == [480, 600, 600, 600, 600]
        assert all(row["physically_valid"] == 1 for row in measurements)
        stats = [row["fields"] for row in rows if row["name"] == "STATS"]
        assert max(row["logger_queue_overflow_count"] for row in stats) == expected_loss
        assert max(row["health_flags"] for row in stats) == 256 * expected_loss
        times = [row["timestamp_us"] for row in rows if row["name"] == "SF6_STATE"]
        intervals = Counter(after - before for before, after in zip(times, times[1:]))
        evidence[name] = {"strict_zero_loss_passed": strict["passed"], "counts": dict(counts),
            "critical_start_records": len(snapshot), "unique_stream_descriptors": 40, "enabled_streams": 21,
            "sf6_measurement_groups": dict(groups), "sf6_state_interval_us": dict(intervals),
            "sequence_gap_count": strict["sequence_gap_count"], "queue_overflow_max": expected_loss,
            "health_flags_max": max(row["health_flags"] for row in stats),
            "sf6_state_times_near_failed_attempt": [stamp for stamp in times if 6380000 <= stamp <= 6510000]}
    return {"scope": "Exact-decoder readback; rates/critical snapshot/drop accounting only",
            "rf56_default_zero_loss_qualification": "FAIL: delay80 strict queue-loss failure is retained",
            "cases": evidence}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--attempt", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(RfActualRates_RecordsCheck(args.project.resolve(), args.attempt.resolve()), indent=2))
