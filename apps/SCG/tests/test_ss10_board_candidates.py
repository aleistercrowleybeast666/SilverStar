"""Owned software board profiles must not acquire hardware qualification."""
import json
import re
import runpy
import shutil
import subprocess
from dataclasses import replace

import pytest
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.h7_storage import (
    H7StorageContract_Get,
    H7StorageInputs_Validate,
)
from silverstar_fccg.generator.multi_target import GroundFiles_Render, _GroundModel_Get
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve, SourceGraphError
from silverstar_fccg.project.air_link import GroundTargetIssues_Get
from silverstar_fccg.project.model import ProjectModel_Load
from silverstar_fccg.project.resources import (
    BoardHardwareInventory_Get,
    BoardResourceProvisions_Get,
)
from silverstar_fccg.project.validation import Project_Validate


@pytest.fixture
def model(workspace_root):
    return ProjectModel_Load(workspace_root / 'examples/SSFC1_0_SSGS1_0.ssproject')


def test_ss10_example_uses_current_owners_and_reports_unverified(model, builtin_catalog):
    result = Project_Validate(model, builtin_catalog)
    assert not [issue for issue in result.issues if issue.level == 'error']
    assert 'board_unverified' in {issue.code for issue in result.issues}
    assert not GroundTargetIssues_Get(model, builtin_catalog)
    assert model.hardware.mode == model.ground_target.hardware.mode == 'board_plugin'
    assert model.hardware.snapshot_id == model.ground_target.hardware.snapshot_id == ''
    assert model.native_usb is None
    for board_id, part in ((model.board, 'STM32H743ZIT6'),
                           (model.ground_target.board, 'STM32C071FBP6')):
        board = builtin_catalog.Component_Get(board_id)
        assert board.board.verified is False
        assert BoardHardwareInventory_Get(board).mcu_part == part
        assert all(row.metadata['connection_fixed'] for row in BoardResourceProvisions_Get(board))
    assert model.ground_target.pc_resource == 'USART2'
    uart = next(r for r in model.ground_target.hardware.resources if r.resource_id == 'USART2')
    assert {d['direction'] for d in uart.metadata['dma']} == {'DMA_PERIPH_TO_MEMORY', 'DMA_MEMORY_TO_PERIPH'}


def test_c071_only_exact_current_ground_profile_can_resolve(model, builtin_catalog):
    ground = _GroundModel_Get(model, builtin_catalog)
    graph = SourceGraph_Resolve(ground, builtin_catalog)
    assert graph.linker_script == 'STM32C071XX_FLASH.ld'
    assert not any('usb' in path.lower() for path in graph.sources)
    for changed in (replace(ground, board=''), replace(ground, core=model.core),
                    replace(ground, hardware=replace(ground.hardware, mode='custom'))):
        with pytest.raises(SourceGraphError, match='no supported UART generation profile'):
            SourceGraph_Resolve(changed, builtin_catalog)


def test_ssfc_owning_storage_replacement_is_unique(model, builtin_catalog):
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert graph.sources.count('FATFS/Target/sd_diskio.c') == 1
    assert 'HardwareGenerated/STM32CubeMX/FATFS/Target/sd_diskio.c' not in graph.sources
    assert 'HardwareGenerated/STM32CubeMX/FATFS/Target/sd_diskio.c' in graph.exclude_sources
    assert len(H7StorageContract_Get(model, builtin_catalog)['required_input_sha256']) == 10


def test_ssfc_storage_rejects_modified_input_and_shadow_header(model, builtin_catalog, tmp_path):
    H7StorageInputs_Validate(model, builtin_catalog, {}, tmp_path)
    target = tmp_path / 'HardwareGenerated/STM32CubeMX/FATFS/Target/ffconf.h'
    target.parent.mkdir(parents=True)
    target.write_text('unreviewed input')
    with pytest.raises(ValueError, match='unreviewed or modified'):
        H7StorageInputs_Validate(model, builtin_catalog, {}, tmp_path)
    target.unlink()
    shadow = tmp_path / 'FATFS/Target/ffconf.h'
    shadow.parent.mkdir(parents=True)
    shadow.write_text('unreviewed shadow')
    with pytest.raises(ValueError, match='shadow headers'):
        H7StorageInputs_Validate(model, builtin_catalog, {}, tmp_path)


def test_ssgs_normal_render_owns_dma_irq_and_configuration_outputs(model, builtin_catalog, workspace_root):
    files = GroundFiles_Render(model, builtin_catalog, WorkspacePolicy(workspace_root))
    graph = json.loads(files['Generated/ground_source_graph.json'])
    assert set(graph['required_irq_handlers']) == {'SysTick_Handler', 'EXTI2_3_IRQHandler',
        'DMA1_Channel1_IRQHandler', 'DMA1_Channel2_3_IRQHandler', 'USART2_IRQHandler'}
    assert b'HAL_UARTEx_ReceiveToIdle_DMA' in files['Generated/Src/pc_byte_stream.c']
    assert b'GroundBridge_Init()' in files['Core/Src/main.c']
    assert b'OPTIMIZATION := -Og -g3' in files['Makefile']
    assert b'--build-dir $(BUILD_DIR)' in files['Makefile']
    assert b'"-fdebug-prefix-map=$(CURDIR)=."' in files['Makefile']
    assert b'-fno-working-directory -save-temps=obj' in files['Makefile']


def test_ground_build_directory_rejects_escaping_and_unknown_configurations(workspace_root):
    namespace = runpy.run_path(str(workspace_root / 'plugins/builtin/silverstar_core_ground_0_1_0/payload/Tools/ground_artifact_contract.py'))
    validate = namespace['BuildDirectory_Validate']
    for path in ('build', 'build/analysis', 'build/Debug', 'build/Debug/analysis'):
        validate(path)
    for path in ('../build', 'build/../external', 'build/Random', 'C:/build', 'build\\Debug'):
        with pytest.raises(ValueError):
            validate(path)


def test_ssfc_hal_tick_irq_routes_to_its_initialized_timer(builtin_catalog):
    board = builtin_catalog.Component_Get('silverstar.board.ssfc_1_0')
    core = board.payload_root / 'HardwareGenerated/STM32CubeMX/Core/Src'
    interrupt = (core / 'stm32h7xx_it.c').read_text(encoding='utf8')
    body = re.search(r'void TIM6_DAC_IRQHandler\(void\)\s*\{([^}]+)\}', interrupt)[1]
    assert body.count('HAL_TIM_IRQHandler(&htim6);') == 1
    callback = (core / 'main.c').read_text(encoding='utf8')
    assert 'htim->Instance == TIM6' in callback
    assert 'HAL_IncTick();' in callback


def test_ssfc_actual_irq_translation_unit_dispatches_tick(builtin_catalog, workspace_root, tmp_path):
    compiler = shutil.which('gcc')
    assert compiler, 'Actual Host GCC required'
    header = '''#include <stdint.h>
typedef struct { unsigned int value; } SD_HandleTypeDef;
typedef struct { unsigned int value; } DMA_HandleTypeDef;
typedef struct { unsigned int value; } UART_HandleTypeDef;
typedef struct { unsigned int value; } TIM_HandleTypeDef;
#define RADIO_DIO1_Pin 32U
#define GNSS_PPS_Pin 64U
void HAL_SD_IRQHandler(SD_HandleTypeDef *handle);
void HAL_DMA_IRQHandler(DMA_HandleTypeDef *handle);
void HAL_UART_IRQHandler(UART_HandleTypeDef *handle);
void HAL_TIM_IRQHandler(TIM_HandleTypeDef *handle);
void HAL_GPIO_EXTI_IRQHandler(uint16_t pin);
void TIM6_DAC_IRQHandler(void);
'''
    (tmp_path / 'main.h').write_text(header)
    (tmp_path / 'stm32h7xx_it.h').write_text('/* Host declarations are in main.h. */\n')
    source = builtin_catalog.Component_Get('silverstar.board.ssfc_1_0').payload_root / 'HardwareGenerated/STM32CubeMX/Core/Src/stm32h7xx_it.c'
    binary = tmp_path / 'tick.exe'
    command = [compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-fanalyzer',
               '-I' + str(tmp_path), str(source), str(workspace_root / 'tests/fixtures/ssfc_tick_irq_host.c'),
               '-o', str(binary)]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
