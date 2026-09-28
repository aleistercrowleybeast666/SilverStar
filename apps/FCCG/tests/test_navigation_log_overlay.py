from __future__ import annotations

import json

import pytest

from silverstar_fccg.core.workspace import WorkspacePolicy
from tools.import_reference_components import _ProtocolMetadata_Adapt


def test_all_35_log_policies_survive_reference_overlay(workspace_root, tmp_path):
    source = workspace_root / (
        "plugins/builtin/silverstar_protocol_logging_sslog_0_0/"
        "payload/Protocol/SSLOG/schema/sslog_parser_metadata.json"
    )
    overlay_path = workspace_root / "tools/reference_overlays/sslog_fccg_metadata.json"
    metadata = json.loads(source.read_text(encoding="utf8"))
    overlay = json.loads(overlay_path.read_text(encoding="utf8"))
    assert len(metadata["fccg"]["records"]) == len(overlay["fccg"]["records"]) == 35
    assert metadata["fccg"] == overlay["fccg"]
    assert (
        metadata["project_semantics"]["navigation_replay"]["gnss_integrity_revision"]
        == 3
    )
    copied = tmp_path / "metadata.json"
    copied.write_text(json.dumps(metadata), encoding="utf8")
    _ProtocolMetadata_Adapt(copied, overlay_path, WorkspacePolicy(tmp_path))
    adapted = json.loads(copied.read_text(encoding="utf8"))
    for name in ("ESKF15_BODY_INPUT", "ESKF15_MEASUREMENT", "ESKF15_INITIAL_P_PART"):
        assert (
            adapted["fccg"]["records"]["FLIGHT_LOG_RECORD_" + name]["level"]
            == "required"
        )
    del overlay["fccg"]["records"]["FLIGHT_LOG_RECORD_ESKF15_BODY_INPUT"]
    invalid = tmp_path / "incomplete_overlay.json"
    invalid.write_text(json.dumps(overlay), encoding="utf8")
    with pytest.raises(RuntimeError, match="cover every record"):
        _ProtocolMetadata_Adapt(copied, invalid, WorkspacePolicy(tmp_path))
