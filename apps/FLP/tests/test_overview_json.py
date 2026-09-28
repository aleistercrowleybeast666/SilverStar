import json
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from types import MappingProxyType

import numpy as np

from silverstar_flp.export.service import ExportOptions, FlightExporter, _Json_Default
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from tests.sslog_synthetic import AnalysisFlight_Build


def test_overview_export_preserves_immutable_quality(tmp_path):
    dataset = Sslog0ParserPlugin().parse(AnalysisFlight_Build(tmp_path / "SYNTHETIC_overview.BIN"))
    quality = replace(
        dataset.data_quality,
        record_counts={"ESTIMATOR": 3},
        sequence_gaps=(
            MappingProxyType(
                {"missing_count": 2, "nested": MappingProxyType({"source": "logger"})}
            ),
        ),
    )
    dataset = replace(dataset, data_quality=quality)
    result = FlightExporter().export(
        dataset,
        tmp_path / "export",
        options=ExportOptions(
            include_diagnostics=False,
            include_events=False,
            include_csv=False,
            include_full_covariance_keyframes=False,
            include_plots=False,
            include_trajectory_3d=False,
            include_attitude_gif=False,
        ),
    )
    assert not result.failures
    overview = next(item.path for item in result.generated if item.item_id == "overview")
    payload = json.loads(overview.read_text(encoding="utf-8"))["data_quality"]
    assert payload["record_counts"] == {"ESTIMATOR": 3}
    assert payload["sequence_gaps"][0] == {"missing_count": 2, "nested": {"source": "logger"}}
    assert isinstance(quality.record_counts, MappingProxyType)
    assert isinstance(quality.sequence_gaps[0], MappingProxyType)


def test_json_default_keeps_paths_enums_numpy_and_nested_dataclasses():
    class Mode(Enum):
        RECORDED = "recorded"

    @dataclass(frozen=True)
    class Payload:
        mapping: object

    value = Payload(
        MappingProxyType(
            {
                "path": Path("flight.BIN"),
                "mode": Mode.RECORDED,
                "scalar": np.int32(3),
                "array": np.array([1, 2]),
            }
        )
    )
    assert json.loads(json.dumps(value, default=_Json_Default)) == {
        "mapping": {"path": "flight.BIN", "mode": "recorded", "scalar": 3, "array": [1, 2]}
    }
