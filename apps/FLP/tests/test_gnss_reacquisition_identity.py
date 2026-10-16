"""Current disabled identity, corruption rejection, and historical absence."""

import struct
import zlib
from copy import deepcopy

import pytest

from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from silverstar_flp.decoder_profiles.gnss_reacquisition import (
    CONTRACT,
    DEFINITIONS,
    OWNER,
    VERSION,
    WIRE,
    GnssReacquisition_FromSemantics,
    GnssReacquisitionFirmwareParameters_Build,
)


def document():
    wire = bytes(104)
    assert WIRE.size == 104
    return {
        "metadata_declarations": {
            "gnss_reacquisition": {
                "schema_id": CONTRACT["schema_id"],
                "revision": 1,
                "component": OWNER,
                "component_version": VERSION,
                "enabled": False,
                "configuration_id": zlib.crc32(wire),
                "configuration_wire_hex": wire.hex(),
            }
        },
        "firmware_algorithm_parameters": [
            {
                "component": OWNER,
                "parameters": [
                    {
                        "id": row["id"],
                        "value": row["default"],
                        "unit": row["unit"],
                        "representation": row["representation"],
                        "storage_type": "int32" if row["type"] == "integer" else "float32",
                    }
                    for row in DEFINITIONS
                ],
            }
        ],
    }


def test_disabled_actual_policy_and_historical_absence_are_distinct():
    current = document()
    saved = deepcopy(current)
    result = GnssReacquisition_FromSemantics(current, OWNER, VERSION)
    assert result["enabled"] is False and current == saved
    historical = {"metadata_declarations": {}, "firmware_algorithm_parameters": []}
    assert GnssReacquisition_FromSemantics(historical, OWNER, "0.3.0") is None
    assert "gnss_reacquisition" not in historical["metadata_declarations"]
    with pytest.raises(DecoderProfileError, match="declaration_missing"):
        GnssReacquisition_FromSemantics(historical, OWNER, VERSION)
    with pytest.raises(DecoderProfileError, match="component_unsupported"):
        GnssReacquisition_FromSemantics(current, OWNER, "0.3.0")


@pytest.mark.parametrize(
    "case",
    [
        "enabled",
        "parameter_enabled",
        "wire",
        "identity",
        "missing",
        "duplicate",
        "unit",
        "storage",
        "boolean_integer",
        "non_binary32",
        "nan",
    ],
)
def test_active_or_corrupt_actual_identity_is_rejected(case):
    current = document()
    declaration = current["metadata_declarations"]["gnss_reacquisition"]
    rows = current["firmware_algorithm_parameters"][0]["parameters"]
    floating = next(row for row in rows if row["storage_type"] == "float32")
    if case == "enabled":
        declaration["enabled"] = True
    elif case == "parameter_enabled":
        rows[0]["value"] = 1
    elif case == "wire":
        declaration["configuration_wire_hex"] = "01" + "00" * 103
    elif case == "identity":
        declaration["configuration_id"] ^= 1
    elif case == "missing":
        rows.pop()
    elif case == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif case == "unit":
        rows[0]["unit"] = "ms"
    elif case == "storage":
        rows[0]["storage_type"] = "float32"
    elif case == "boolean_integer":
        rows[0]["value"] = False
    elif case == "non_binary32":
        floating["value"] = 1.1
    elif case == "nan":
        floating["value"] = float("nan")
    with pytest.raises(DecoderProfileError):
        GnssReacquisition_FromSemantics(current, OWNER, VERSION)


def test_recovery_fields_are_readonly_firmware_evidence_not_offline_defaults():
    from silverstar_flp.plugins.algorithms.eskf15.plugin import Eskf15AlgorithmPlugin

    plugin = Eskf15AlgorithmPlugin()
    fields = GnssReacquisitionFirmwareParameters_Build()
    assert len(fields) == 29 and all(not row.required for row in fields)
    assert all(
        not row.parameter_id.startswith("gnss_recovery_")
        for row in plugin.metadata.parameter_schema
    )
    assert struct.unpack(
        "<I",
        bytes.fromhex(
            document()["metadata_declarations"]["gnss_reacquisition"]["configuration_wire_hex"]
        )[:4],
    ) == (0,)
