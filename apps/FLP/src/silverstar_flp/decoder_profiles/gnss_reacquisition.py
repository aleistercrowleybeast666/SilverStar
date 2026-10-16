"""Closed disabled-only ESKF0.4 identity; never synthesizes Recorded policy."""

import math
import struct
import zlib
from collections.abc import Mapping

from silverstar_flp.decoder_profiles.contract_data import Contract_Load
from silverstar_flp.decoder_profiles.errors import DecoderProfileError

CONTRACT = Contract_Load("navigation_gnss_reacquisition_v1.json")
OWNER = CONTRACT["component"]
VERSION = CONTRACT["component_version"]
DEFINITIONS = tuple(CONTRACT["parameters"])
FIELDS = tuple("gnss_recovery_" + name for name in CONTRACT["configuration_wire"]["order"])
WIRE = struct.Struct(CONTRACT["configuration_wire"]["format"])


def _F32(value):
    try:
        result = struct.unpack("<f", struct.pack("<f", value))[0]
    except (OverflowError, struct.error, TypeError) as error:
        raise DecoderProfileError("gnss_reacquisition_float32_invalid") from error
    if not math.isfinite(result):
        raise DecoderProfileError("gnss_reacquisition_float32_invalid")
    return result


def _Actual_Get(document, component):
    sets = document.get("firmware_algorithm_parameters", ())
    if not isinstance(sets, (list, tuple)) or any(not isinstance(row, Mapping) for row in sets):
        raise DecoderProfileError("gnss_reacquisition_actual_sets_invalid")
    selected = [row for row in sets if row.get("component") == component]
    if len(selected) > 1:
        raise DecoderProfileError("gnss_reacquisition_actual_ambiguous")
    rows = selected[0].get("parameters", ()) if selected else ()
    if not isinstance(rows, (list, tuple)) or any(not isinstance(row, Mapping) for row in rows):
        raise DecoderProfileError("gnss_reacquisition_actual_parameters_invalid")
    actual = {}
    for row in rows:
        name = row.get("id")
        if not isinstance(name, str) or not name.startswith("gnss_recovery_"):
            continue
        if name in actual:
            raise DecoderProfileError("gnss_reacquisition_actual_duplicate")
        actual[name] = row
    return actual


def GnssReacquisition_FromSemantics(document, component, version):
    declaration = document.get("metadata_declarations", {}).get("gnss_reacquisition")
    actual = _Actual_Get(document, component)
    if component != OWNER or version != VERSION:
        if declaration is not None or actual:
            raise DecoderProfileError("gnss_reacquisition_component_unsupported")
        return None  # Historical absence is preserved, not a new default policy.
    expected = {
        "schema_id",
        "revision",
        "component",
        "component_version",
        "enabled",
        "configuration_id",
        "configuration_wire_hex",
    }
    if not isinstance(declaration, Mapping) or set(declaration) != expected:
        raise DecoderProfileError("gnss_reacquisition_declaration_missing_or_invalid")
    if (
        declaration["schema_id"] != CONTRACT["schema_id"]
        or type(declaration["revision"]) is not int
        or declaration["revision"] != 1
        or declaration["component"] != OWNER
        or declaration["component_version"] != VERSION
    ):
        raise DecoderProfileError("gnss_reacquisition_declaration_identity_invalid")
    if type(declaration["enabled"]) is not bool or declaration["enabled"]:
        raise DecoderProfileError("gnss_reacquisition_activation_not_accepted")
    if set(actual) != set(FIELDS):
        raise DecoderProfileError("gnss_reacquisition_actual_incomplete_or_unknown")
    values = {}
    for definition in DEFINITIONS:
        name = definition["id"]
        row = actual[name]
        integer = definition["type"] == "integer"
        value = row.get("value")
        if (
            row.get("storage_type") != ("int32" if integer else "float32")
            or row.get("unit") != definition["unit"]
            or row.get("representation") != definition["representation"]
        ):
            raise DecoderProfileError("gnss_reacquisition_parameter_contract_mismatch:" + name)
        if (integer and type(value) is not int) or (
            not integer and type(value) not in (int, float)
        ):
            raise DecoderProfileError("gnss_reacquisition_parameter_type_invalid:" + name)
        minimum = definition["min"] if integer else _F32(definition["min"])
        maximum = definition["max"] if integer else _F32(definition["max"])
        if not integer and value != _F32(value):
            raise DecoderProfileError("gnss_reacquisition_actual_not_binary32:" + name)
        if not minimum <= value <= maximum:
            raise DecoderProfileError("gnss_reacquisition_parameter_range_invalid:" + name)
        values[name] = value
    if values["gnss_recovery_enabled"] != 0:
        raise DecoderProfileError("gnss_reacquisition_activation_not_accepted")
    wire = WIRE.pack(*(values[name] for name in FIELDS))
    identity = zlib.crc32(wire) or 0xFFFFFFFF
    if (
        type(declaration["configuration_id"]) is not int
        or declaration["configuration_id"] != identity
        or not isinstance(declaration["configuration_wire_hex"], str)
        or declaration["configuration_wire_hex"] != wire.hex()
    ):
        raise DecoderProfileError("gnss_reacquisition_actual_wire_identity_mismatch")
    return declaration


def GnssReacquisitionFirmwareParameters_Build():
    """Read-only firmware fields, absent from offline defaults and What-if knobs."""
    from silverstar_flp.plugins.api.algorithm import ParameterSpec

    return tuple(
        ParameterSpec(
            row["id"],
            "int" if row["type"] == "integer" else "float",
            row["default"],
            row["min"] if row["type"] == "integer" else _F32(row["min"]),
            row["max"] if row["type"] == "integer" else _F32(row["max"]),
            row["unit"],
            representation=row["representation"],
            required=False,
            precision=row["precision"],
        )
        for row in DEFINITIONS
    )
