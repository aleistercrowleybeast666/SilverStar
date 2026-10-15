"""Data-only timing identity; never selects or implements a numerical algorithm."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from silverstar_flp.decoder_profiles.errors import DecoderProfileError

SCHEMA_ID = "silverstar.navigation-fusion-timing/1"
PARAMETER_ID = "fusion_timing_mode"
LEGACY_VERSIONS = {
    "silverstar.algorithm.estimator.kf6": frozenset(("0.1.0", "0.2.0", "0.2.1")),
    "silverstar.algorithm.estimator.eskf15": frozenset(("0.1.0", "0.1.1")),
}
_FIELDS = frozenset((
    "schema_id", "revision", "component", "mode", "source_time", "application_time",
    "evaluation_time", "output_state_time", "output_covariance_time", "replays_history",
))


@dataclass(frozen=True)
class FusionTimingIdentity:
    component: str
    version: str | None
    revision: int | None
    mode: int | None
    evidence: str
    unavailable_reason: str = ""


def _Version_Get(document: Mapping, component: str) -> str | None:
    locks = document.get("component_locks", ())
    if not isinstance(locks, (list, tuple)) or any(not isinstance(row, Mapping) for row in locks):
        raise DecoderProfileError("fusion_timing_component_locks_invalid")
    selected = [row for row in locks if row.get("component") == component]
    if len(selected) > 1:
        raise DecoderProfileError("fusion_timing_component_identity_ambiguous")
    if not selected:
        return None
    version = selected[0].get("version")
    if not isinstance(version, str) or not version:
        raise DecoderProfileError("fusion_timing_component_version_invalid")
    return version


def _Declaration_Validate(declaration: object, component: str) -> int:
    if not isinstance(declaration, Mapping) or set(declaration) != _FIELDS:
        raise DecoderProfileError("fusion_timing_declaration_invalid")
    if declaration["schema_id"] != SCHEMA_ID or type(declaration["revision"]) is not int or declaration["revision"] != 1:
        raise DecoderProfileError("fusion_timing_revision_unsupported")
    if declaration["component"] != component:
        raise DecoderProfileError("fusion_timing_component_mismatch")
    mode = declaration["mode"]
    if type(mode) is not int or mode not in (0, 1):
        raise DecoderProfileError("fusion_timing_mode_unsupported")
    expected = {
        "source_time": "resolved_measurement_epoch",
        "application_time": "estimator_present" if mode == 0 else "legacy_algorithm_epoch",
        "evaluation_time": "estimator_present",
        "output_state_time": "estimator_present",
        "output_covariance_time": "estimator_present",
    }
    if any(declaration[key] != value for key, value in expected.items()):
        raise DecoderProfileError("fusion_timing_timestamp_contract_mismatch")
    if type(declaration["replays_history"]) is not bool or declaration["replays_history"] != (mode == 1):
        raise DecoderProfileError("fusion_timing_history_contract_mismatch")
    return mode


def FusionTiming_FromSemantics(document: Mapping) -> FusionTimingIdentity | None:
    """Missing declarations are legacy only for an audited component version.

    An explicit declaration is a package assertion, not proof of implementation
    or runtime record completeness. Current mode is always unavailable here.
    No defaults or parameter values are synthesized into the input document.
    """
    declarations = document.get("metadata_declarations", {})
    if not isinstance(declarations, Mapping):
        raise DecoderProfileError("fusion_timing_metadata_invalid")
    owners = [name for name in document.get("algorithms", ()) if name in LEGACY_VERSIONS]
    declared = "fusion_timing" in declarations
    if len(owners) > 1:
        if declared:
            raise DecoderProfileError("fusion_timing_owner_ambiguous")
        # Historical packages may describe more than one estimator. Their raw
        # records remain readable; do not invent a single timing owner or mode.
        return FusionTimingIdentity("", None, None, None, "unknown",
                                    "fusion_timing_identity_unproven")
    if not owners:
        if declared:
            raise DecoderProfileError("fusion_timing_owner_invalid")
        return None
    component = owners[0]
    version = _Version_Get(document, component)
    legacy = version in LEGACY_VERSIONS[component]
    if not declared:
        return FusionTimingIdentity(component, version, 0 if legacy else None,
                                    1 if legacy else None, "legacy_component_lock" if legacy else "unknown",
                                    "" if legacy else "fusion_timing_identity_unproven")
    mode = _Declaration_Validate(declarations["fusion_timing"], component)
    if legacy and mode != 1:
        raise DecoderProfileError("fusion_timing_legacy_component_mismatch")
    reason = "fusion_timing_current_replay_not_implemented" if mode == 0 else (
        "" if legacy else "fusion_timing_identity_unproven")
    return FusionTimingIdentity(component, version, 1, mode, "explicit_declaration", reason)


def FusionTimingUnavailable_Get(dataset) -> tuple[str, ...]:
    """Return numerical replay blockers without altering raw records or bytes."""
    context = getattr(dataset, "semantic_context", None)
    if context is None:
        return ()  # Existing non-package/What-if admission remains independently checked.
    document = getattr(context, "raw_metadata", {})
    if not isinstance(document, Mapping):
        return ("fusion_timing_metadata_invalid",)
    declarations = document.get("metadata_declarations", {})
    if isinstance(declarations, Mapping) and "fusion_timing" not in declarations:
        # No new declaration means no new admission rule. Existing algorithm
        # revision/recorded-parameter checks retain authority over legacy replay.
        # This does not certify an unknown timing identity as exact replay.
        return ()
    try:
        identity = FusionTiming_FromSemantics(document)
    except DecoderProfileError as error:
        return (str(error),)
    return (identity.unavailable_reason,) if identity and identity.unavailable_reason else ()
