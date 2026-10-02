"""Keep the published project schema aligned with the current serializer."""

from __future__ import annotations

import json
from pathlib import Path

from silverstar_fccg.project.model import PROJECT_FORMAT_VERSION, PROJECT_GROUND_RADIOS_FORMAT_VERSION


def test_format_14_schema_tracks_current_model_fields() -> None:
    schema = json.loads(
        (Path(__file__).resolve().parents[1] / "schemas/project.schema.json")
        .read_text(encoding="utf-8")
    )
    assert schema["properties"]["format_version"]["enum"] == [PROJECT_FORMAT_VERSION, PROJECT_GROUND_RADIOS_FORMAT_VERSION] == [14, 15]
    assert {"alignment", "flight_tx_power_dbm", "ground_target"} <= set(schema["required"])
    assert {"alignment", "flight_tx_power_dbm"} <= set(schema["properties"])
    assert "mcu_family" in schema["properties"]["components"]["properties"]
    assert "tx_power_dbm" in schema["properties"]["ground_target"]["properties"]
    hardware = schema["properties"]["hardware"]
    assert set(hardware["required"]) <= set(hardware["properties"])
    assert "cubemx_version" not in schema["properties"]["log_decoder_profile"]["properties"]
