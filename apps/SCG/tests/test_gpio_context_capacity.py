"""Actual F4 GPIO backend: retain sparse IDs while bounding inactive storage."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest


def test_reference_gpio_count_uses_complete_declared_board(builtin_catalog):
    from silverstar_fccg.generator.render import _PlatformGpioContextCount_Get
    from silverstar_fccg.project.reference import ReferenceProject_Create
    model = ReferenceProject_Create("GpioCapacity", catalog=builtin_catalog)
    assert _PlatformGpioContextCount_Get(model, builtin_catalog) == 9
    # Device selection never licenses discarding an existing board GPIO ID.
    model.device_instances = []
    assert _PlatformGpioContextCount_Get(model, builtin_catalog) == 9


@pytest.mark.parametrize("indices,expected", [([], 1), ([0, 8], 9), ([0, 95], 96)])
def test_custom_gpio_count_preserves_sparse_high_ids(indices, expected):
    from silverstar_fccg.generator.render import _PlatformGpioContextCount_Get
    resources = [SimpleNamespace(kind="gpio_output", resource_id=f"pin{index}",
        metadata={"logical_index": index, "port": "GPIOA", "pin": "GPIO_PIN_0"}) for index in indices]
    model = SimpleNamespace(hardware=SimpleNamespace(mode="custom", resources=resources))
    assert _PlatformGpioContextCount_Get(model, None) == expected


@pytest.mark.parametrize("index", [-1, 96, True])
def test_gpio_count_rejects_invalid_indices(index):
    from silverstar_fccg.generator.render import _PlatformGpioContextCount_Get
    resource = SimpleNamespace(kind="gpio_interrupt", resource_id="invalid",
        metadata={"logical_index": index, "port": "GPIOA", "pin": "GPIO_PIN_0"})
    model = SimpleNamespace(hardware=SimpleNamespace(mode="custom", resources=[resource]))
    with pytest.raises(ValueError, match="GPIO binding"):
        _PlatformGpioContextCount_Get(model, None)


def test_legacy_opaque_gpio_symbol_preserves_full_interface(monkeypatch):
    import silverstar_fccg.generator.render as render
    monkeypatch.setattr(render, "_BoardPlatformResources_Get", lambda *_: {
        "gpios": [{"c_id": "USER_DEFINED_GPIO_ID"}]})
    catalog = SimpleNamespace(Component_Get=lambda *_: None)
    model = SimpleNamespace(hardware=SimpleNamespace(mode="board"), board="legacy")
    assert render._PlatformGpioContextCount_Get(model, catalog) == 96


@pytest.mark.parametrize("capacity", [9, 96])
def test_gpio_backend_capacity_and_irq_boundaries(tmp_path, workspace_root, capacity):
    builtin = workspace_root / "plugins/builtin"
    platform = builtin / "silverstar_mcu_family_stm32f4/payload/Platform/STM32F4"
    api = builtin / "silverstar_platform_api/payload/Platform/Inc"
    source = Path(os.environ.get("SILVERSTAR_GPIO_TEST_SOURCE", str(platform / "Src/platform_gpio_stm32f4.c")))
    (tmp_path / "stm32f4xx_hal.h").write_text('''#include <stdint.h>
typedef struct { uint16_t value; } GPIO_TypeDef;
typedef enum { GPIO_PIN_RESET, GPIO_PIN_SET } GPIO_PinState;
void HAL_GPIO_WritePin(GPIO_TypeDef *, uint16_t, GPIO_PinState);
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *, uint16_t);
''', encoding="utf8")
    harness = tmp_path / "gpio.c"
    harness.write_text('''#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include "platform_gpio_stm32f4.c"
static GPIO_TypeDef port;
static uint32_t mask;
static unsigned highest_lookup;
uint8_t PlatformStm32f4Resource_GpioGet(PlatformGpioId id, PlatformStm32f4GpioResource *out)
{
    assert((unsigned)id < PLATFORM_GPIO_COUNT);
    if ((unsigned)id > highest_lookup) { highest_lookup = (unsigned)id; }
    if ((id != PLATFORM_GPIO_0) && ((unsigned)id != SILVERSTAR_PLATFORM_GPIO_CONTEXT_COUNT - 1U)) { return 0U; }
    *out = (PlatformStm32f4GpioResource){&port, 4U, (uint8_t)(id != PLATFORM_GPIO_0)};
    return 1U;
}
PlatformCriticalState PlatformCritical_Enter(void) { PlatformCriticalState previous = mask; mask = 1U; return previous; }
void PlatformCritical_Exit(PlatformCriticalState previous) { assert(mask == 1U); mask = previous; }
void HAL_GPIO_WritePin(GPIO_TypeDef *p, uint16_t pin, GPIO_PinState state)
{ assert(p == &port && pin == 4U); p->value = (state == GPIO_PIN_SET) ? pin : 0U; }
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *p, uint16_t pin)
{ assert(p == &port && pin == 4U); return p->value ? GPIO_PIN_SET : GPIO_PIN_RESET; }
int main(void)
{
    uint8_t value = 77U;
    PlatformGpioId last = (PlatformGpioId)(SILVERSTAR_PLATFORM_GPIO_CONTEXT_COUNT - 1U);
    assert(PlatformGpio_Write(PLATFORM_GPIO_0, 1U) == PLATFORM_OK);
    assert(PlatformGpio_Read(PLATFORM_GPIO_0, &value) == PLATFORM_OK && value == 1U);
    assert(PlatformGpio_Write(last, 0U) == PLATFORM_OK);
    assert(PlatformGpio_Write(PLATFORM_GPIO_1, 1U) == PLATFORM_INVALID_ARGUMENT);
    value = 77U;
    assert(PlatformGpio_Read((PlatformGpioId)SILVERSTAR_PLATFORM_GPIO_CONTEXT_COUNT, &value) == PLATFORM_INVALID_ARGUMENT && value == 77U);
    assert(PlatformGpio_Write((PlatformGpioId)-1, 1U) == PLATFORM_INVALID_ARGUMENT);
    assert(PlatformGpio_Read(PLATFORM_GPIO_0, NULL) == PLATFORM_INVALID_ARGUMENT);
    HAL_GPIO_EXTI_Callback(8U);
    assert(PlatformGpio_IrqConsume(last) == 0U);
    HAL_GPIO_EXTI_Callback(4U); HAL_GPIO_EXTI_Callback(4U);
    mask = 1U;
    assert(PlatformGpio_IrqConsume(last) == 1U && mask == 1U);
    mask = 0U;
    assert(PlatformGpio_IrqConsume(last) == 1U && mask == 0U);
    assert(PlatformGpio_IrqConsume(last) == 0U);
    assert(PlatformGpio_IrqConsume(PLATFORM_GPIO_0) == 0U);
    assert(PlatformGpio_IrqConsume((PlatformGpioId)-1) == 0U);
    printf("allocated=%zu configured=%u highest_lookup=%u\\n", sizeof(s_gpio)/sizeof(s_gpio[0]), SILVERSTAR_PLATFORM_GPIO_CONTEXT_COUNT, highest_lookup);
    fflush(stdout);
    assert(sizeof(s_gpio)/sizeof(s_gpio[0]) == SILVERSTAR_PLATFORM_GPIO_CONTEXT_COUNT);
    assert(highest_lookup < SILVERSTAR_PLATFORM_GPIO_CONTEXT_COUNT);
    return 0;
}
''', encoding="utf8")
    compiler = shutil.which("gcc")
    assert compiler, "Actual Host GCC is required"
    executable = tmp_path / "gpio.exe"
    command = [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic", "-fanalyzer",
               f"-DSILVERSTAR_PLATFORM_GPIO_CONTEXT_COUNT={capacity}U",
               *["-I" + str(p) for p in (tmp_path, source.parent, platform / "Inc", api)],
               str(harness), "-o", str(executable)]
    compiled = subprocess.run(command, text=True, capture_output=True, timeout=60)
    (tmp_path / "compile.log").write_text(compiled.stdout + compiled.stderr, encoding="utf8")
    (tmp_path / "command.json").write_text(json.dumps(command, indent=2), encoding="utf8")
    inputs = [source, harness, tmp_path / "stm32f4xx_hal.h",
              platform / "Inc/platform_stm32f4_resources.h", *api.glob("*.h")]
    receipt = {"compiler": subprocess.check_output([compiler, "--version"], text=True),
               "command": command, "compile_exit": compiled.returncode,
               "sources": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}}
    (tmp_path / "compiler-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf8")
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    result = subprocess.run([str(executable)], text=True, capture_output=True, timeout=20)
    (tmp_path / "run.log").write_text(result.stdout + result.stderr, encoding="utf8")
    assert result.returncode == 0, result.stdout + result.stderr
