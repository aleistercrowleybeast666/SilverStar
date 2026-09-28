import json
from dataclasses import replace

from joint_navigation_support import NavigationGolden_Generate

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.project.logging import LoggingProfile_Reconcile
from tools.sslog_audit import Audit_Bytes, Audit_ProfileLoad


def test_joint_navigation_contract_and_c_golden(tmp_path, workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("JointNumerical")
    model.algorithm_parameters["silverstar.algorithm.estimator.kf6"]["baro_measurement_delay_ms"] = 100
    # Full-rate protocol contracts cannot be weakened by an old saved choice.
    model.logging_streams = [replace(s, decimation=7) if s.record == "FLIGHT_LOG_RECORD_IMU_CORRECTED" else s
                             for s in model.logging_streams]
    LoggingProfile_Reconcile(model, service.catalog)
    full_rate = next(s for s in model.logging_streams if s.record == "FLIGHT_LOG_RECORD_IMU_CORRECTED")
    assert (full_rate.policy, full_rate.decimation, full_rate.period_us) == ("EVERY", 1, 0)
    project = tmp_path / "generated"
    service.Project_Save(model, project, confirm_dangerous=True)
    log = NavigationGolden_Generate(project, tmp_path / "numerical")
    assert log.stat().st_size > 100_000
    audit_catalog, hashes = Audit_ProfileLoad(project / "JointNumerical.ssdecoder")
    audited = Audit_Bytes(log.read_bytes(), audit_catalog, decoder_hashes=hashes)
    assert audited["passed"]
    assert "ESTIMATOR" in audited["record_counts"]
    assert "KF6_FULL_P" not in audited["record_counts"]
    catalog = json.loads((project / "Protocol/SSLOG/schema/sslog_schema.json").read_text())
    records = {r["name"]: r for r in catalog["records"]}
    assert not {"SAMPLE", "RAW_SENSOR", "IMU_NATIVE", "HW_QUAT_NATIVE"} & records.keys()
    assert records["ESTIMATOR"]["version"] == 1
    assert {"q_nb", "operation_sequence", "replay_epoch"} <= {f["name"] for f in records["ESTIMATOR"]["fields"]}
