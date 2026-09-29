from __future__ import annotations

import pytest
from silverstar_fccg.project.alignment import (
    ALIGNMENT_MAX_CONSTRAINTS,
    AlignmentConfiguration,
    AlignmentConfiguration_Parse,
    AlignmentConstraint,
)
from silverstar_fccg.project.model import PROJECT_FORMAT_VERSION, ProjectModel_Parse
from silverstar_fccg.project.reference import ReferenceProject_Create


def test_bounded_alignment_configuration_round_trips_in_project(builtin_catalog) -> None:
    model = ReferenceProject_Create("VectorProject", catalog=builtin_catalog)
    model.alignment = AlignmentConfiguration(
        constraints=(
            AlignmentConstraint("gravity", 2.0),
            AlignmentConstraint("magnetic_field", 1.5, -7.25),
            AlignmentConstraint("reference_direction", 0.75, body_axis="-Y", nav_azimuth_deg=235.0),
        ),
        external_source_instance="imu0",
        external_yaw_authoritative=False,
        external_known_azimuth_deg=235.0,
    )
    encoded = model.Dictionary_Get()
    assert encoded["format_version"] == PROJECT_FORMAT_VERSION == 14
    assert ProjectModel_Parse(encoded).alignment == model.alignment
    from silverstar_fccg.generator.render import _FlightConfigHeader_Render

    header = _FlightConfigHeader_Render(model, builtin_catalog)
    assert "SYSTEM_ALIGNMENT_CONSTRAINT_COUNT" in header
    assert "ALIGNMENT_CONSTRAINT_MAGNETIC_FIELD" in header
    assert "-2" in header
    assert "SYSTEM_ALIGNMENT_KNOWN_YAW_DEG" in header
    assert "-145.0F" in header


@pytest.mark.parametrize("replacement", [
    {"weight": 0.0},
    {"weight": float("nan")},
    {"body_axis": "X"},
    {"nav_azimuth_deg": 360.0},
    {"declination_deg": 181.0},
])
def test_constraint_rejects_invalid_values(replacement: dict) -> None:
    values = AlignmentConfiguration().Dictionary_Get()
    values["constraints"][1].update(replacement)
    with pytest.raises(ValueError):
        AlignmentConfiguration_Parse(values)


def test_constraint_count_and_yaw_authority_are_bounded() -> None:
    values = AlignmentConfiguration().Dictionary_Get()
    values["constraints"] += [values["constraints"][1]] * (ALIGNMENT_MAX_CONSTRAINTS - 1)
    with pytest.raises(ValueError, match="two to six"):
        AlignmentConfiguration_Parse(values)
    values = AlignmentConfiguration().Dictionary_Get()
    values["external_known_azimuth_deg"] = None
    with pytest.raises(ValueError, match="known azimuth"):
        AlignmentConfiguration_Parse(values)
    values["external_yaw_authoritative"] = True
    assert AlignmentConfiguration_Parse(values).external_known_azimuth_deg is None


def test_pre_release_format_13_uses_explicit_default_alignment(builtin_catalog) -> None:
    model = ReferenceProject_Create("PreviousProject", catalog=builtin_catalog)
    encoded = model.Dictionary_Get()
    encoded["format_version"] = 13
    del encoded["alignment"]
    assert ProjectModel_Parse(encoded).alignment == AlignmentConfiguration()


def test_reference_selects_vector_strategy_and_single_source(builtin_catalog) -> None:
    from silverstar_fccg.generator.source_graph import SourceGraph_Resolve

    model = ReferenceProject_Create("VectorReference", catalog=builtin_catalog)
    assert model.strategies["alignment"] == "silverstar.algorithm.alignment.vector_constraints"
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert graph.sources.count(
        "Algorithm/Alignment/VectorConstraints/Src/alignment_strategy_binding.c"
    ) == 1
    assert not any(
        path.endswith("/alignment_strategy_binding.c")
        and "/VectorConstraints/" not in path
        for path in graph.sources
    )
