from __future__ import annotations

import pytest

from silverstar_flp.decoder_profiles.algorithm_parameters import FirmwareParameters_CheckPlugins
from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from silverstar_flp.plugins.registry import builtin_registry


def _IntegrityParameterGroup_Build():
    plugin = builtin_registry().Algorithm_Get("silverstar.algorithm.kf6")
    specs = tuple(
        spec for spec in plugin.metadata.parameter_schema
        if spec.parameter_id.startswith("gnss_integrity_")
    )
    assert len(specs) == 10
    return {
        "component": "silverstar.algorithm.estimator.kf6",
        "parameters": [{
            "id": spec.parameter_id,
            "value": spec.default,
            "unit": spec.unit,
            "representation": spec.representation,
            "storage_type": "float32" if spec.kind == "float" else "int32",
        } for spec in specs],
    }


def test_integrity_parameter_revision_requires_complete_matching_group() -> None:
    group = _IntegrityParameterGroup_Build()
    FirmwareParameters_CheckPlugins([group], integrity_revision=2)
    partial = {
        **group,
        "parameters": group["parameters"][:-1],
    }
    with pytest.raises(DecoderProfileError, match="gnss_integrity_parameters_incomplete"):
        FirmwareParameters_CheckPlugins([partial], integrity_revision=2)
    FirmwareParameters_CheckPlugins([partial], integrity_revision=0)
    legacy = {**group, "parameters": []}
    FirmwareParameters_CheckPlugins([legacy], integrity_revision=0)
    with pytest.raises(DecoderProfileError, match="gnss_integrity_parameters_incomplete"):
        FirmwareParameters_CheckPlugins([legacy], integrity_revision=2)


def test_legacy_candidate_revision_is_explicitly_unsupported() -> None:
    with pytest.raises(DecoderProfileError, match="legacy_candidate_unsupported"):
        FirmwareParameters_CheckPlugins([_IntegrityParameterGroup_Build()],
                                        integrity_revision=1)
