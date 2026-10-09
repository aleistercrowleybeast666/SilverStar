"""Generic typed HAL SPI/GPIO binding from actual native initialization owners.

This route validates whole initializer values, not occurrence of a recognized
name inside an expression. It does not configure native GPIO, clocks or SPI.
"""
from __future__ import annotations

import hashlib
import re

from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet, NativeC_VisibleGet


def NativePlatformContract_Inspect(files: dict[str, bytes], proof: dict, inventory) -> dict:
    resources = {item.resource_id: item for item in inventory.HardwareResources_Get()}
    spi = resources[proof["bindings"]["spi"]]
    handle = str(spi.metadata["handle"])
    peripheral = str(spi.resource_id)
    if not re.fullmatch(r"SPI[1-9][0-9]*", peripheral):
        raise ValueError("Native peripheral identifier is not a literal SPI instance")
    core = {p: NativeC_VisibleGet(files[p].decode("utf-8-sig"))
            for p in proof["build"]["sources"] if p.startswith("Core/")}
    initializers = []
    expected = {"Mode": "SPI_MODE_MASTER", "Direction": "SPI_DIRECTION_2LINES",
                "DataSize": "SPI_DATASIZE_8BIT", "CLKPolarity": "SPI_POLARITY_LOW",
                "CLKPhase": "SPI_PHASE_1EDGE", "NSS": "SPI_NSS_SOFT",
                "FirstBit": "SPI_FIRSTBIT_MSB", "TIMode": "SPI_TIMODE_DISABLE",
                "CRCCalculation": "SPI_CRCCALCULATION_DISABLE"}
    init_name = "MX_" + peripheral + "_Init"
    for path in core:
        try:
            _start, opening, end = NativeC_FunctionSpanGet(files[path].decode("utf-8-sig"), init_name)
        except ValueError:
            continue
        body = core[path][opening + 1:end - 1]
        assignments = re.findall(re.escape(handle) + r"\.Init\.(\w+)\s*=\s*([^;{}]+);", body)
        values = dict(assignments)
        if len(values) != len(assignments) or any(values.get(key, "").strip() != value
                                                 for key, value in expected.items()):
            raise ValueError("Native SPI initializer contradicts the exact radio contract")
        if not re.fullmatch(r"SPI_BAUDRATEPRESCALER_(2|4|8|16|32|64|128|256)",
                            values.get("BaudRatePrescaler", "").strip()):
            raise ValueError("Native SPI prescaler is not a literal supported initializer")
        if values["BaudRatePrescaler"].strip() != spi.metadata.get("BaudRatePrescaler"):
            raise ValueError("Native SPI actual prescaler differs from physical inventory")
        expected["BaudRatePrescaler"] = values["BaudRatePrescaler"].strip()
        if (len(re.findall(re.escape(handle) + r"\.Instance\s*=\s*" + peripheral + r"\s*;", body)) != 1 or
                not re.search(r"if\s*\(HAL_SPI_Init\s*\(\s*&" + handle +
                              r"\s*\)\s*!=\s*HAL_OK\s*\)\s*\{\s*Error_Handler\(\);\s*\}", body)):
            raise ValueError("Native SPI initialization call/result owner is unknown")
        initializers.append(path)
    if len(initializers) != 1:
        raise ValueError("Native SPI needs one actual initialization function")
    # Hardware inventory supplies parsed bus frequency/pins; no fabricated SPI
    # rate is emitted. A prepared radio route needs the declared physical range.
    clock = spi.metadata.get("clock_hz")
    if type(clock) is not int or not 100_000 <= clock <= 10_000_000:
        raise ValueError("Native radio SPI clock is unavailable or outside its contract")
    headers = [files[p].decode("utf-8-sig") for p in files if p.startswith("Core/") and p.endswith(".h")]
    definitions = {}
    for header in headers:
        for name, value in re.findall(r"(?m)^\s*#define\s+(\w+)\s+([^\r\n]+)", header):
            if name.endswith(("_Pin", "_GPIO_Port")):
                if name in definitions:
                    raise ValueError("Native GPIO macro has multiple owners: " + name)
                definitions[name] = value.strip()

    def port_get(token):
        value = definitions.get(token, token)
        if not re.fullmatch(r"GPIO[A-Z]", value):
            raise ValueError("Native GPIO port is an expression or unknown alias: " + token)
        return value

    def pins_get(expression):
        tokens = expression.split("|")
        pins = []
        for token in tokens:
            value = definitions.get(token.strip(), token.strip())
            match = re.fullmatch(r"GPIO_PIN_(\d|1[0-5])", value)
            if match is None:
                raise ValueError("Native GPIO pin is an expression or unknown alias")
            pins.append(int(match[1]))
        if len(pins) != len(set(pins)):
            raise ValueError("Native GPIO initialization repeats a pin")
        return pins

    configs = {}
    levels = {}
    for path, code in core.items():
        blocks = re.findall(r"GPIO_InitStruct\.Pin\s*=\s*([^;]+);"
            r"((?:\s*GPIO_InitStruct\.\w+\s*=\s*[^;]+;)*)\s*"
            r"HAL_GPIO_Init\s*\(\s*(\w+)\s*,\s*&GPIO_InitStruct\s*\)\s*;", code)
        if len(blocks) != len(re.findall(r"\bHAL_GPIO_Init\s*\(", code)):
            raise ValueError("Native GPIO initialization has unparsed aliases/control flow: " + path)
        for pin_expression, fields, port in blocks:
            attrs = re.findall(r"GPIO_InitStruct\.(\w+)\s*=\s*([^;]+);", fields)
            if len(dict(attrs)) != len(attrs):
                raise ValueError("Native GPIO initializer field has multiple writes")
            for pin in pins_get(pin_expression):
                key = (port_get(port), pin)
                configs.setdefault(key, []).append((path, {k: v.strip() for k, v in attrs}))
        for port, pin_expression, level in re.findall(
                r"HAL_GPIO_WritePin\s*\(\s*(\w+)\s*,\s*([\w| \t]+)\s*,\s*(\w+)\s*\)\s*;", code):
            for pin in pins_get(pin_expression):
                levels.setdefault((port_get(port), pin), []).append((path, level))
    labels = proof["bindings"]["gpio"]
    if len(labels) != 4:
        raise ValueError("Native radio needs exact NSS/reset/busy/DIO1 role order")
    bindings = []
    for role, label, mode in zip(("nss", "reset", "busy", "dio1"), labels,
                                 ("GPIO_MODE_OUTPUT_PP", "GPIO_MODE_OUTPUT_PP",
                                  "GPIO_MODE_INPUT", "GPIO_MODE_IT_RISING")):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", label):
            raise ValueError("Native GPIO role label is not a literal identifier")
        port = port_get(label + "_GPIO_Port")
        pin = pins_get(label + "_Pin")[0]
        if resources[label].metadata.get("physical_pin") != "P" + port[4:] + str(pin):
            raise ValueError("Native source GPIO pin differs from physical inventory")
        matches = configs.get((port, pin), [])
        if len(matches) != 1 or matches[0][1].get("Mode") != mode:
            raise ValueError("Native GPIO has conflicting actual mode owners: " + role)
        owner, attrs = matches[0]
        if attrs.get("Pull") not in ({"GPIO_NOPULL", "GPIO_PULLUP"} if role == "nss" else {"GPIO_NOPULL"}):
            raise ValueError("Native GPIO pull contradicts the radio contract: " + role)
        if role in {"nss", "reset"}:
            if attrs.get("Speed") != "GPIO_SPEED_FREQ_LOW" or levels.get((port, pin)) != [(owner, "GPIO_PIN_SET")]:
                raise ValueError("Native GPIO lacks a unique safe inactive output initializer")
            code = core[owner]
            write = re.search(r"HAL_GPIO_WritePin\s*\([^;]+" + re.escape(label) + r"_Pin[^;]+;", code)
            configure = re.search(r"GPIO_InitStruct\.Pin\s*=\s*[^;]*\b" + re.escape(label) + r"_Pin\b[^;]*;", code)
            if write is None or configure is None or write.start() >= configure.start():
                raise ValueError("Native radio output level is not set before mode initialization")
        bindings.append({"role": role, "label": label, "port": port, "pin": "GPIO_PIN_" + str(pin), "owner": owner})
    if any(re.search(r"(?m)^\s*(?:(?:__weak|static)\s+)?void\s+HAL_GPIO_EXTI_Callback\s*\([^;{}]*\)\s*\{", code)
           for code in core.values()):
        raise ValueError("Native application already owns the GPIO EXTI callback")
    dio_pin = int(bindings[3]["pin"].removeprefix("GPIO_PIN_"))
    irq = "EXTI" + (str(dio_pin) if dio_pin <= 4 else "9_5" if dio_pin <= 9 else "15_10")
    irq_name, handler = irq + "_IRQn", irq + "_IRQHandler"
    if handler not in proof["independent_irq_slots"]:
        raise ValueError("Native DIO1 interrupt lacks an independently bound vector slot")
    handler_owners = []
    for path, code in core.items():
        try:
            _start, opening, end = NativeC_FunctionSpanGet(files[path].decode("utf-8-sig"), handler)
        except ValueError:
            continue
        handler_body = code[opening+1:end-1]
        calls = re.findall(r"HAL_GPIO_EXTI_IRQHandler\s*\(\s*(\w+)\s*\)\s*;", handler_body)
        remaining = re.sub(r"HAL_GPIO_EXTI_IRQHandler\s*\(\s*\w+\s*\)\s*;", "", handler_body)
        called_pins = [pins_get(pin)[0] for pin in calls]
        if (remaining.strip() or not 1 <= len(calls) <= 16 or
                calls.count(labels[3] + "_Pin") != 1 or len(set(called_pins)) != len(called_pins)):
            raise ValueError("Native DIO1 interrupt handler has an unknown application owner")
        handler_owners.append(path)
    gpio_owner = bindings[3]["owner"]
    gpio_code = core[gpio_owner]
    priorities = re.findall(r"HAL_NVIC_SetPriority\s*\(\s*" + irq_name +
        r"\s*,\s*(\d+)U?\s*,\s*(\d+)U?\s*\)\s*;", gpio_code)
    irq_headers = [content.decode("utf-8-sig") for path, content in files.items()
        if path.endswith(".h") and hashlib.sha256(content).hexdigest() == proof["device_facts"]["irq_header_sha256"]]
    priority_bits = re.findall(r"(?m)^\s*#define\s+__NVIC_PRIO_BITS\s+(\d+)U?\b", irq_headers[0]) if len(irq_headers) == 1 else []
    if (len(handler_owners) != 1 or
            len(re.findall(r"HAL_NVIC_EnableIRQ\s*\(\s*" + irq_name + r"\s*\)\s*;", gpio_code)) != 1 or
            len(priorities) != 1 or len(priority_bits) != 1 or
            not 1 <= int(priority_bits[0]) <= 8 or
            any(int(value) >= 1 << int(priority_bits[0]) for value in priorities[0])):
        raise ValueError("Native DIO1 interrupt needs one exact enabled priority owner")
    for signal in ("sck", "miso", "mosi"):
        physical = spi.metadata.get("pins", {}).get(signal, "")
        match = re.fullmatch(r"P([A-Z])(\d|1[0-5])", physical)
        matches = configs.get(("GPIO" + match[1], int(match[2])), []) if match else []
        modes = {"GPIO_MODE_AF_PP", "GPIO_MODE_INPUT"} if signal == "miso" else {"GPIO_MODE_AF_PP"}
        if len(matches) != 1 or matches[0][0] != initializers[0] or matches[0][1].get("Mode") not in modes:
            raise ValueError("Native SPI physical pin lacks a unique matching initialization owner: " + signal)
    if not re.search(r"__HAL_RCC_" + peripheral + r"_CLK_ENABLE\s*\(\s*\)\s*;", core[initializers[0]]):
        raise ValueError("Native SPI peripheral clock owner is unavailable")
    return {"spi_handle": handle, "spi_peripheral": peripheral, "spi_owner": initializers[0],
            "spi_clock_hz": clock, "spi_initializers": expected, "gpio": bindings,
            "dio1_irq": {"handler": handler, "owner": handler_owners[0], "irq_number": proof["independent_irq_slots"][handler],
                         "priority": tuple(int(value) for value in priorities[0]), "priority_bits": int(priority_bits[0])},
            "source_contract": "Exact native initializer values; typed runtime checks still required"}


def NativePlatform_FilesRender(contract: dict) -> dict[str, bytes]:
    handle = contract["spi_handle"]
    peripheral = contract["spi_peripheral"]
    prescaler = contract["spi_initializers"]["BaudRatePrescaler"]
    if (not re.fullmatch(r"hspi[1-9][0-9]*", handle) or
            not re.fullmatch(r"SPI[1-9][0-9]*", peripheral) or
            not re.fullmatch(r"SPI_BAUDRATEPRESCALER_(2|4|8|16|32|64|128|256)", prescaler) or
            [item.get("role") for item in contract["gpio"]] != ["nss", "reset", "busy", "dio1"] or
            any(not re.fullmatch(r"GPIO[A-Z]", item["port"]) or
                not re.fullmatch(r"GPIO_PIN_(\d|1[0-5])", item["pin"]) for item in contract["gpio"])):
        raise ValueError("Native typed bindings must be literal identifiers with four explicit roles")
    rows = ",\n".join("    {" + item["port"] + ", " + item["pin"] + ", " +
                        ("1U" if item["role"] in {"nss", "reset"} else "0U") + "}"
                        for item in contract["gpio"])
    header = '''#ifndef __NATIVE_PLATFORM_H
#define __NATIVE_PLATFORM_H
#include "platform_types.h"
PlatformResult NativePlatform_Init(void);
void NativePlatform_Quiesce(void);
#endif /* __NATIVE_PLATFORM_H */
'''
    platform = '''#include "native_platform.h"
#include "native_clock.h"
#include "platform_spi.h"
#include "platform_gpio.h"
#include "platform_critical.h"
#include "silverstar_assert.h"
#include "main.h"
#include <stddef.h>

extern SPI_HandleTypeDef @HANDLE@;
typedef struct { GPIO_TypeDef *port; uint16_t pin; uint8_t output; } NativeGpioBinding;
static const NativeGpioBinding s_gpio_bindings[4] = {
@ROWS@
};
static uint8_t s_initialized;
static uint8_t s_spi_active;
static volatile uint8_t s_dio1_pending;
static uint8_t s_tx_copy[260];

PlatformResult NativePlatform_Init(void)
{
    if (s_initialized != 0U) { return PLATFORM_ALREADY_INITIALIZED; }
    if ((@HANDLE@.Instance != @PERIPHERAL@) ||
        (@HANDLE@.Init.Mode != SPI_MODE_MASTER) ||
        (@HANDLE@.Init.Direction != SPI_DIRECTION_2LINES) ||
        (@HANDLE@.Init.DataSize != SPI_DATASIZE_8BIT) ||
        (@HANDLE@.Init.CLKPolarity != SPI_POLARITY_LOW) ||
        (@HANDLE@.Init.CLKPhase != SPI_PHASE_1EDGE) ||
        (@HANDLE@.Init.NSS != SPI_NSS_SOFT) ||
        (@HANDLE@.Init.FirstBit != SPI_FIRSTBIT_MSB) ||
        (@HANDLE@.Init.TIMode != SPI_TIMODE_DISABLE) ||
        (@HANDLE@.Init.CRCCalculation != SPI_CRCCALCULATION_DISABLE) ||
        (@HANDLE@.Init.BaudRatePrescaler != @PRESCALER@) ||
        (@HANDLE@.State != HAL_SPI_STATE_READY) ||
        (NativeClock_StatusGet() != NativeClockResult_Ok))
    { return PLATFORM_NOT_READY; }
    s_initialized = 1U;
    return PLATFORM_OK;
}

void NativePlatform_Quiesce(void)
{
    /* Native initialization owns these pins; retire this sole radio owner. */
    HAL_GPIO_WritePin(s_gpio_bindings[0].port, s_gpio_bindings[0].pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(s_gpio_bindings[1].port, s_gpio_bindings[1].pin, GPIO_PIN_RESET);
    s_initialized = 0U;
}

PlatformResult PlatformGpio_Write(PlatformGpioId id, uint8_t high)
{
    uint32_t index = (uint32_t)id;
    if ((index >= 4U) || (high > 1U)) { return PLATFORM_INVALID_ARGUMENT; }
    if (s_initialized == 0U) { return PLATFORM_NOT_READY; }
    if (s_gpio_bindings[index].output == 0U) { return PLATFORM_UNSUPPORTED; }
    HAL_GPIO_WritePin(s_gpio_bindings[index].port, s_gpio_bindings[index].pin,
        (high != 0U) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    return PLATFORM_OK;
}

PlatformResult PlatformGpio_Read(PlatformGpioId id, uint8_t *high)
{
    uint32_t index = (uint32_t)id;
    if ((index >= 4U) || (high == NULL)) { return PLATFORM_INVALID_ARGUMENT; }
    if (s_initialized == 0U) { return PLATFORM_NOT_READY; }
    *high = (HAL_GPIO_ReadPin(s_gpio_bindings[index].port,
             s_gpio_bindings[index].pin) == GPIO_PIN_SET) ? 1U : 0U;
    return PLATFORM_OK;
}

void HAL_GPIO_EXTI_Callback(uint16_t pin)
{
    if (pin == s_gpio_bindings[3].pin) { s_dio1_pending = 1U; }
}

uint8_t PlatformGpio_IrqConsume(PlatformGpioId id)
{
    uint8_t pending;
    PlatformCriticalState saved;
    if ((id != PLATFORM_GPIO_3) || (s_initialized == 0U)) { return 0U; }
    saved = PlatformCritical_Enter();
    pending = s_dio1_pending;
    s_dio1_pending = 0U;
    PlatformCritical_Exit(saved);
    return pending;
}

static PlatformResult NativeSpi_ResultGet(HAL_StatusTypeDef result)
{
    switch (result)
    {
        case HAL_OK: return PLATFORM_OK;
        case HAL_BUSY: return PLATFORM_BUSY;
        case HAL_TIMEOUT: return PLATFORM_TIMEOUT;
        case HAL_ERROR: return PLATFORM_IO_ERROR;
        default: return PLATFORM_IO_ERROR;
    }
}

static PlatformResult NativeSpi_Exchange(PlatformSpiId id, const uint8_t *tx,
    uint8_t *rx, uint16_t length, uint32_t timeout, uint8_t receive,
    PlatformSpiDriverObservation *observation)
{
    uint16_t index;
    HAL_StatusTypeDef result;
    if (observation != NULL) { *observation = (PlatformSpiDriverObservation){0}; }
    if ((id != PLATFORM_SPI_1) || (tx == NULL) || (length == 0U) ||
        (length > sizeof(s_tx_copy)) || (timeout == 0U) || (timeout > 100U) ||
        ((receive != 0U) && (rx == NULL))) { return PLATFORM_INVALID_ARGUMENT; }
    if ((s_initialized == 0U) || (__get_IPSR() != 0U) || (__get_PRIMASK() != 0U))
    { return PLATFORM_NOT_READY; }
    SILVERSTAR_ASSERT(s_spi_active <= 1U, SILVERSTAR_ASSERT_MODULE_GENERATED,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_spi_active != 0U) { return PLATFORM_BUSY; }
    if (NativeClock_DelayUs(1U) != NativeClockResult_Ok) { return PLATFORM_NOT_READY; }
    s_spi_active = 1U;
    for (index = 0U; (index < length) && (index < sizeof(s_tx_copy)); index++)
    { s_tx_copy[index] = tx[index]; }
    result = (receive != 0U) ? HAL_SPI_TransmitReceive(&@HANDLE@, s_tx_copy, rx, length, timeout) :
        HAL_SPI_Transmit(&@HANDLE@, s_tx_copy, length, timeout);
    s_spi_active = 0U;
    /* No invented SR value is marked as observed. Native HAL byte ownership
     * and result are checked; register diagnostics need a separate ABI port. */
    if (NativeClock_DelayUs(1U) != NativeClockResult_Ok) { return PLATFORM_NOT_READY; }
    return NativeSpi_ResultGet(result);
}

PlatformResult PlatformSpi_WriteObserved(PlatformSpiId id, const uint8_t *data,
    uint16_t length, uint32_t timeout, PlatformSpiDriverObservation *observation)
{ return NativeSpi_Exchange(id, data, NULL, length, timeout, 0U, observation); }

PlatformResult PlatformSpi_TransferObserved(PlatformSpiId id, const uint8_t *tx,
    uint8_t *rx, uint16_t length, uint32_t timeout, PlatformSpiDriverObservation *observation)
{ return NativeSpi_Exchange(id, tx, rx, length, timeout, 1U, observation); }

PlatformResult PlatformSpi_Write(PlatformSpiId id, const uint8_t *data,
    uint16_t length, uint32_t timeout)
{ return PlatformSpi_WriteObserved(id, data, length, timeout, NULL); }

PlatformResult PlatformSpi_Transfer(PlatformSpiId id, const uint8_t *tx,
    uint8_t *rx, uint16_t length, uint32_t timeout)
{ return PlatformSpi_TransferObserved(id, tx, rx, length, timeout, NULL); }
'''.replace("@HANDLE@", handle).replace("@PERIPHERAL@", peripheral).replace("@ROWS@", rows).replace("@PRESCALER@", prescaler)
    return {"Generated/Inc/native_platform.h": header.encode("utf-8"),
            "Generated/Src/native_platform.c": platform.encode("utf-8")}
