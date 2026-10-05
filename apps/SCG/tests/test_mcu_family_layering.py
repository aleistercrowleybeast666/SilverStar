from __future__ import annotations

from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.project.model import ProjectModel_Parse
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.validation import Project_Validate


def test_f407_project_selects_api_family_and_exact_mcu(builtin_catalog) -> None:
    model = ReferenceProject_Create("FamilyLayering", catalog=builtin_catalog)
    restored = ProjectModel_Parse(model.Dictionary_Get())
    assert restored.mcu_family == "silverstar.mcu_family.stm32f4"
    assert Project_Validate(restored, builtin_catalog).valid

    selected = restored.ComponentIds_Get()
    assert selected.index("silverstar.platform.api") < selected.index(model.mcu_family)
    assert selected.index(model.mcu_family) < selected.index(model.mcu)

    api = builtin_catalog.Component_Get("silverstar.platform.api")
    family = builtin_catalog.Component_Get(model.mcu_family)
    exact = builtin_catalog.Component_Get(model.mcu)
    assert (api.payload_root / "Platform/Inc/platform_spi.h").is_file()
    assert (
        family.payload_root / "Platform/STM32F4/Src/platform_spi_stm32f4.c"
    ).is_file()
    assert not (exact.payload_root / "Platform").exists()
    assert not (exact.payload_root / "Drivers").exists()
    assert exact.metadata["platform_family_id"] == family.component_id

    graph = SourceGraph_Resolve(restored, builtin_catalog)
    assert "Platform/STM32F4/Inc" in graph.include_dirs
    assert "Platform/STM32F4/Src/platform_spi_stm32f4.c" in graph.sources
    assert graph.sources.count("Platform/STM32F4/Src/platform_spi_stm32f4.c") == 1
    assert graph.asm_sources == ("startup_stm32f407xx.s",)


def test_wrong_mcu_family_is_rejected(builtin_catalog) -> None:
    model = ReferenceProject_Create("WrongFamily", catalog=builtin_catalog)
    model.mcu_family = "silverstar.mcu_family.nonexistent"
    result = Project_Validate(model, builtin_catalog)
    assert not result.valid
    assert any(issue.code == "missing_component" for issue in result.issues)
