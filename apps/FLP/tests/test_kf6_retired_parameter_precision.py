"""Synthetic regressions for declared binary32 retired-parameter equality.

The first test expresses the intended corrected behavior and fails on 34bbd38.
No implementation is patched or replaced by this private reproduction suite.
"""

import numpy as np
import pytest
from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    from dataclasses import replace

    from tests.synthetic_parameter_navigation import NavigationPair_Open

    data = NavigationPair_Open(tmp_path_factory.mktemp("synthetic"), flight_samples=3).dataset
    metadata = dict(data.semantic_context.raw_metadata)
    metadata["metadata_declarations"] = {"navigation_replay": {"gnss_integrity_revision": 3}}
    metadata["firmware_algorithm_parameters"] = [
        {
            **group,
            "parameters": [
                {**item, "value": float(np.float32(item["value"]))}
                if item["storage_type"] == "float32"
                else dict(item)
                for item in group["parameters"]
            ],
        }
        for group in metadata["firmware_algorithm_parameters"]
    ]
    return replace(data, semantic_context=replace(data.semantic_context, raw_metadata=metadata))


def test_offline_gui_full_defaults_equal_implicit_offline_defaults(dataset):
    plugin = Kf6AlgorithmPlugin()
    implicit = plugin._Parameters_Resolve(dataset, ReplayRequest(mode=ReplayMode.OFFLINE))
    # ReplayPage._Request_Get sends this complete map in OFFLINE mode.
    explicit = plugin._Parameters_Resolve(
        dataset,
        ReplayRequest(mode=ReplayMode.OFFLINE, parameters=dict(plugin.OfflineParameters_Get())),
    )
    assert explicit == implicit


def test_recorded_and_unchanged_what_if_use_firmware_baseline(dataset):
    plugin = Kf6AlgorithmPlugin()
    recorded = plugin._Parameters_Resolve(dataset, ReplayRequest())
    unchanged = plugin._Parameters_Resolve(
        dataset,
        ReplayRequest(
            mode=ReplayMode.WHAT_IF, parameters=dict(plugin.recorded_parameters(dataset))
        ),
    )
    assert unchanged == recorded


@pytest.mark.parametrize("mode", [ReplayMode.OFFLINE, ReplayMode.WHAT_IF])
def test_actual_retired_parameter_override_is_still_rejected(dataset, mode):
    plugin = Kf6AlgorithmPlugin()
    values = dict(
        plugin.OfflineParameters_Get()
        if mode == ReplayMode.OFFLINE
        else plugin.recorded_parameters(dataset)
    )
    values["gnss_integrity_sacc_max_mps"] = 1.1
    with pytest.raises(ValueError, match="parameter_retired_revision3:gnss_integrity_sacc_max_mps"):
        plugin._Parameters_Resolve(dataset, ReplayRequest(mode=mode, parameters=values))


RETIRED_FLOAT32 = (
    "gnss_integrity_recovery_threshold_m",
    "gnss_integrity_hacc_max_m",
    "gnss_integrity_sacc_max_mps",
)


@pytest.mark.parametrize("name", RETIRED_FLOAT32)
def test_same_declared_binary32_value_is_accepted(dataset, name):
    plugin = Kf6AlgorithmPlugin()
    records = dataset.semantic_context.FirmwareParameters_Get("silverstar.algorithm.estimator.kf6")
    assert records[name]["storage_type"] == "float32"
    values = dict(plugin.recorded_parameters(dataset))
    original = values[name]
    values[name] = float(np.nextafter(np.float64(original), np.float64(np.inf)))
    assert values[name] != original
    assert np.float32(values[name]) == np.float32(original)
    plugin._Parameters_Resolve(dataset, ReplayRequest(mode=ReplayMode.WHAT_IF, parameters=values))


@pytest.mark.parametrize("storage", [None, "float64", "int32"])
def test_missing_or_unknown_float32_declaration_remains_conservative(dataset, storage):
    from dataclasses import replace

    name = "gnss_integrity_sacc_max_mps"
    metadata = dict(dataset.semantic_context.raw_metadata)
    groups = []
    for group in metadata["firmware_algorithm_parameters"]:
        parameters = []
        for item in group["parameters"]:
            item = dict(item)
            if item["id"] == name:
                if storage is None:
                    item.pop("storage_type")
                else:
                    item["storage_type"] = storage
            parameters.append(item)
        groups.append({**group, "parameters": parameters})
    metadata["firmware_algorithm_parameters"] = groups
    data = replace(
        dataset, semantic_context=replace(dataset.semantic_context, raw_metadata=metadata)
    )
    plugin = Kf6AlgorithmPlugin()
    values = dict(plugin.recorded_parameters(data))
    plugin._Parameters_Resolve(data, ReplayRequest(mode=ReplayMode.WHAT_IF, parameters=values))
    values[name] = float(np.nextafter(np.float64(values[name]), np.float64(np.inf)))
    with pytest.raises(ValueError, match=f"parameter_retired_revision3:{name}"):
        plugin._Parameters_Resolve(data, ReplayRequest(mode=ReplayMode.WHAT_IF, parameters=values))


@pytest.mark.parametrize("name", RETIRED_FLOAT32)
def test_next_float32_value_remains_a_rejected_substantive_override(dataset, name):
    plugin = Kf6AlgorithmPlugin()
    values = dict(plugin.recorded_parameters(dataset))
    original = values[name]
    values[name] = float(np.nextafter(np.float32(original), np.float32(np.inf)))
    assert np.float32(values[name]) != np.float32(original)
    with pytest.raises(ValueError, match=f"parameter_retired_revision3:{name}"):
        plugin._Parameters_Resolve(
            dataset, ReplayRequest(mode=ReplayMode.WHAT_IF, parameters=values)
        )


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_retired_float32_remains_invalid(dataset, invalid):
    plugin = Kf6AlgorithmPlugin()
    with pytest.raises(ValueError, match="parameter_not_finite:gnss_integrity_sacc_max_mps"):
        plugin._Parameters_Resolve(
            dataset,
            ReplayRequest(
                mode=ReplayMode.WHAT_IF, parameters={"gnss_integrity_sacc_max_mps": invalid}
            ),
        )


@pytest.mark.parametrize(
    "name",
    [
        "gnss_integrity_suspect_duration_ms",
        "gnss_integrity_reject_duration_ms",
        "gnss_integrity_recovery_duration_ms",
    ],
)
def test_retired_integer_value_domain_is_exact(dataset, name):
    plugin = Kf6AlgorithmPlugin()
    original = plugin.recorded_parameters(dataset)[name]
    for invalid in (float(original), True):
        with pytest.raises(ValueError, match=f"parameter_type_invalid:{name}"):
            plugin._Parameters_Resolve(
                dataset, ReplayRequest(mode=ReplayMode.WHAT_IF, parameters={name: invalid})
            )
    with pytest.raises(ValueError, match=f"parameter_retired_revision3:{name}"):
        plugin._Parameters_Resolve(
            dataset, ReplayRequest(mode=ReplayMode.WHAT_IF, parameters={name: original + 1})
        )


@pytest.mark.parametrize("invalid", [True, 2])
def test_enable_enumeration_domain_remains_strict(dataset, invalid):
    plugin = Kf6AlgorithmPlugin()
    with pytest.raises(
        ValueError, match="parameter_(type_invalid|out_of_range):gnss_integrity_enable"
    ):
        plugin._Parameters_Resolve(
            dataset,
            ReplayRequest(mode=ReplayMode.WHAT_IF, parameters={"gnss_integrity_enable": invalid}),
        )
