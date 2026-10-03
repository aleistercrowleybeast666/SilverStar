"""Data-only SF6 revision identity; never infer a new algorithm from old logs."""

from silverstar_flp.decoder_profiles.errors import DecoderProfileError

COMPONENT = "silverstar.algorithm.estimator.sf6"
GAIN_IDS = {"gain_" + axis for axis in ("ve", "vn", "vu", "pe", "pn", "pu")}
DELAY_IDS = {"gnss_position_measurement_delay_ms", "gnss_velocity_measurement_delay_ms",
             "baro_measurement_delay_ms"}


def Sf6Revision_FromSemantics(document):
    if COMPONENT not in document.get("algorithms", ()):
        return None
    declaration = document.get("metadata_declarations", {}).get("sf6", {})
    declared = declaration.get("revision")
    if declared is not None and (type(declared) is not int or declared not in (1, 2)):
        raise DecoderProfileError("sf6_algorithm_revision_unsupported", str(declared))
    locks = [item for item in document.get("component_locks", ())
             if item.get("component") == COMPONENT]
    if len(locks) > 1:
        raise DecoderProfileError("sf6_component_identity_ambiguous")
    version = locks[0].get("version") if locks else None
    if version is not None and version not in ("0.1.0", "0.2.0"):
        raise DecoderProfileError("sf6_component_version_unsupported", str(version))
    version_revision = {"0.1.0": 1, "0.2.0": 2}.get(version)
    groups = [item for item in document.get("firmware_algorithm_parameters", ())
              if item["component"] == COMPONENT]
    identifiers = {item["id"] for group in groups for item in group["parameters"]}
    # Frozen early package1.2 profiles lacked an explicit declaration. Their
    # complete legacy gain/delay schema is an audited revision1 identity only.
    legacy_identity = 1 if identifiers == GAIN_IDS | DELAY_IDS else None
    revision = declared or version_revision or legacy_identity
    if revision is None:
        raise DecoderProfileError("sf6_algorithm_revision_missing")
    if version_revision is not None and version_revision != revision:
        raise DecoderProfileError("sf6_algorithm_revision_mismatch")
    if revision == 2 and identifiers & DELAY_IDS:
        raise DecoderProfileError("sf6_revision2_delay_parameters_forbidden")
    return revision


def Sf6Revision_Get(dataset):
    context = dataset.semantic_context
    revision = Sf6Revision_FromSemantics(context.raw_metadata) if context else None
    states = dataset.Records_Get("SF6_STATE")
    for record in states:
        actual = record.payload.get("algorithm_revision")
        if type(actual) is not int or actual not in (1, 2):
            raise DecoderProfileError("sf6_recorded_algorithm_revision_unsupported", str(actual))
        if revision is None:
            raise DecoderProfileError("sf6_recorded_algorithm_identity_missing")
        if actual != revision:
            raise DecoderProfileError("sf6_recorded_algorithm_revision_mismatch")
    if revision is None and dataset.Records_Get("SF6_MEASUREMENT"):
        raise DecoderProfileError("sf6_recorded_algorithm_identity_missing")
    return revision
