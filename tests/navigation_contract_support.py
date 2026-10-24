"""Assertions against owned contracts; no model or application imports."""
import json


def NavigationParameters_Assert(repository):
    def read(relative):
        return json.loads((repository / relative).read_text(encoding="utf-8"))

    base = read("contracts/navigation_v1.json")["eskf15"]["parameters"]
    recovery = read("contracts/navigation_gnss_reacquisition_v1.json")
    # These two extensions are declared separately from the base navigation
    # parameter set. Freeze their physical meaning rather than accepting extras.
    expected = dict(base)
    expected.update({row["id"]: row for row in recovery["parameters"]})
    expected.update({
        "fusion_timing_mode": dict(type="integer", default=1, min=0, max=2,
                                   unit="1", representation="value"),
        "fusion_horizon_ms": dict(type="integer", default=300, min=10, max=550,
                                  unit="ms", representation="value"),
    })
    manifest = read("apps/SCG/plugins/builtin/silverstar_algorithm_estimator_eskf15/plugin.json")
    actual = {row["id"]: row for row in manifest["algorithm_parameters"]["parameters"]}
    assert len(actual) == len(manifest["algorithm_parameters"]["parameters"])
    assert set(actual) == set(expected)
    keys = ("type", "default", "min", "max", "unit", "representation")
    for name, row in expected.items():
        assert {key: actual[name][key] for key in keys} == {key: row[key] for key in keys}, name
        if "nis_df" in row:
            assert actual[name]["nis_df"] == row["nis_df"], name
    metadata = manifest["metadata"]
    assert metadata["fusion_timing_contract"]["parameter"] == "fusion_timing_mode"
    assert metadata["fusion_horizon_contract"]["parameter"] == "fusion_horizon_ms"
    assert metadata["gnss_reacquisition_contract"]["schema_id"] == recovery["schema_id"]
    return manifest
