"""Data-only process-model identity; GNSS quality revision is independent."""
import re
from collections.abc import Mapping

from silverstar_flp.decoder_profiles.errors import DecoderProfileError

COMPONENT = "silverstar.algorithm.estimator.kf6"
MODELS = {1: "legacy_fragment_constant_acceleration",
          2: "original_increment_equivalent_white_acceleration"}
KERNEL_PATHS = (
    "Algorithm/Estimator/KF6/Inc/navigation_kf.h",
    "Algorithm/Estimator/KF6/Src/navigation_kf.c",
    "Algorithm/Estimator/KF6/Src/navigation_kf_replay.c",
)


def Kf6Revision_FromSemantics(document):
    if COMPONENT not in document.get("algorithms", ()):
        return None
    declarations = document.get("metadata_declarations", {})
    if not isinstance(declarations, Mapping):
        raise DecoderProfileError("kf6_metadata_declarations_invalid")
    declaration = declarations.get("kf6", {})
    if not isinstance(declaration, Mapping):
        raise DecoderProfileError("kf6_algorithm_declaration_invalid")
    declared = declaration.get("revision")
    if "revision" in declaration and (type(declared) is not int or declared not in MODELS):
        raise DecoderProfileError("kf6_algorithm_revision_unsupported", str(declared))
    raw_locks = document.get("component_locks", [])
    # JSON lists are frozen to tuples in the read-only dataset context.
    if not isinstance(raw_locks, (list, tuple)) or any(not isinstance(item, Mapping) for item in raw_locks):
        raise DecoderProfileError("kf6_component_locks_invalid")
    locks = [item for item in raw_locks if item.get("component") == COMPONENT]
    if len(locks) > 1:
        raise DecoderProfileError("kf6_component_identity_ambiguous")
    if any(not isinstance(item.get("version"), str) for item in locks):
        raise DecoderProfileError("kf6_component_version_invalid")
    expected = {"0.1.0": 1, "0.2.0": 2, "0.2.1": 2}.get(locks[0]["version"]) if len(locks) == 1 else None
    # Audited legacy packages identify their original model by the exact
    # pre-upgrade component version. Never infer revision 2 from membership.
    revision = declared if declared is not None else (1 if expected == 1 else None)
    if declared is not None and expected is not None and declared != expected:
        raise DecoderProfileError("kf6_algorithm_revision_mismatch")
    if ("process_noise_model" in declaration or declared is not None) and (
        revision is None or declaration.get("process_noise_model") != MODELS[revision]
    ):
        raise DecoderProfileError("kf6_process_noise_model_mismatch")
    hashes = declaration.get("kernel_sha256")
    if declared == 2 or "kernel_sha256" in declaration:
        if not isinstance(hashes, Mapping) or set(hashes) != set(KERNEL_PATHS) or any(
            not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{64}", value) is None
            for value in hashes.values()
        ):
            raise DecoderProfileError("kf6_kernel_identity_invalid")
    # Missing or unknown optional locks do not prevent data-only raw decoding.
    # Mathematical replay must resolve a known identity separately, fail closed.
    return revision if expected is not None else None


def Kf6Revision_Get(dataset):
    context = dataset.semantic_context
    return Kf6Revision_FromSemantics(context.raw_metadata) if context else None
