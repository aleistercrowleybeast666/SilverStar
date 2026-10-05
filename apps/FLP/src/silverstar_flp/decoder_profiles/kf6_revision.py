"""Data-only process-model identity; GNSS quality revision is independent."""
from silverstar_flp.decoder_profiles.errors import DecoderProfileError

COMPONENT = "silverstar.algorithm.estimator.kf6"
MODELS = {1: "legacy_fragment_constant_acceleration",
          2: "original_increment_equivalent_white_acceleration"}


def Kf6Revision_FromSemantics(document):
    if COMPONENT not in document.get("algorithms", ()):
        return None
    declaration = document.get("metadata_declarations", {}).get("kf6", {})
    declared = declaration.get("revision")
    if declared is not None and (type(declared) is not int or declared not in MODELS):
        raise DecoderProfileError("kf6_algorithm_revision_unsupported", str(declared))
    locks = [item for item in document.get("component_locks", ())
             if item.get("component") == COMPONENT]
    if len(locks) != 1:
        raise DecoderProfileError("kf6_component_identity_missing_or_ambiguous")
    version = locks[0].get("version")
    expected = {"0.1.0": 1, "0.2.0": 2}.get(version)
    if expected is None:
        raise DecoderProfileError("kf6_component_version_unsupported", str(version))
    # Audited legacy packages identify their original model by the exact
    # pre-upgrade component version. Never infer revision 2 from membership.
    revision = declared if declared is not None else (1 if expected == 1 else None)
    if revision is None:
        raise DecoderProfileError("kf6_algorithm_revision_missing")
    if revision != expected:
        raise DecoderProfileError("kf6_algorithm_revision_mismatch")
    if declared is not None and declaration.get("process_noise_model") != MODELS[revision]:
        raise DecoderProfileError("kf6_process_noise_model_mismatch")
    return revision


def Kf6Revision_Get(dataset):
    context = dataset.semantic_context
    return Kf6Revision_FromSemantics(context.raw_metadata) if context else None
