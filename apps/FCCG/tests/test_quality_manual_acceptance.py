"""Automatic tool success must not erase pending critical-contract review."""
import json

import pytest

from silverstar_fccg.project.quality_results import QualityResult_Save, QualityResults_Load


@pytest.mark.parametrize("succeeded", [True, False])
def test_power10_record_keeps_manual_acceptance_pending(tmp_path, succeeded):
    record = QualityResult_Save(tmp_path, task="power10_check", succeeded=succeeded,
                                duration=1.0, summary="completed")
    assert record.result == ("passed" if succeeded else "failed")
    assert "POWER10_CONTRACT_REVIEW|NOT_PROVEN|manual_acceptance_pending" in record.summary
    assert record.manual_acceptance_pending
    assert QualityResults_Load(tmp_path) == (record,)


def test_legacy_power10_success_does_not_imply_manual_acceptance(tmp_path):
    directory = tmp_path / ".fccg"
    directory.mkdir()
    (directory / "quality-results.json").write_text(json.dumps({"format_version": 1,
        "results": {"power10_check": {"task": "power10_check", "result": "passed",
        "timestamp": "2026-09-27T08:52:18+08:00", "duration": 1.0, "summary": "checks=6459"}}}),
        encoding="utf-8")
    raw_before = (directory / "quality-results.json").read_bytes()
    record, = QualityResults_Load(tmp_path)
    assert "NOT_PROVEN|manual_acceptance_pending" in record.summary
    assert record.result == "passed" and "checks=6459" in record.summary
    assert (directory / "quality-results.json").read_bytes() == raw_before


@pytest.mark.parametrize("succeeded", [True, False])
def test_power10_critical_failure_is_not_replaced_by_pending_review(tmp_path, succeeded):
    summary = "POWER10_CONTRACT_REVIEW|FAIL|unchecked_recovery"
    record = QualityResult_Save(tmp_path, task="power10_check", succeeded=succeeded,
                                duration=1.0, summary=summary)
    assert record.result == "failed" and summary in record.summary
