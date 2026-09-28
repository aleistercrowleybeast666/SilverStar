from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from silverstar_fccg.project.model import HardwareResource


@dataclass(frozen=True, slots=True)
class PinInventory:
    pin: str
    signal: str
    label: str = ""
    mode: str = ""
    alternate_function: str = ""
    pull: str = ""
    output_default: str = ""
    output_type: str = ""
    speed: str = ""
    exti_trigger: str = ""
    locked: bool = False
    exti_line: int | None = None


@dataclass(frozen=True, slots=True)
class DmaInventory:
    request: str
    instance: str
    direction: str = ""
    mode: str = ""
    priority: str = ""
    channel: str = ""


@dataclass(frozen=True, slots=True)
class NvicInventory:
    irq: str
    enabled: bool
    preempt_priority: int | None = None
    sub_priority: int | None = None


@dataclass(frozen=True, slots=True)
class PeripheralInventory:
    instance: str
    kind: str
    pins: dict[str, str] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    dma: tuple[DmaInventory, ...] = ()
    irq: NvicInventory | None = None


@dataclass(frozen=True, slots=True)
class TimebaseInventory:
    kind: str = ""
    source: str = ""
    handle: str = ""
    instance: str = ""
    irq: str = ""
    counter_frequency_hz: int = 0
    period_counts: int = 0
    tick_frequency_hz: int = 0
    interrupt_started: bool = False
    errors: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return self.kind == "tim" and not self.errors


@dataclass(frozen=True, slots=True)
class FatFsInventory:
    enabled: bool = False
    app_source: str = ""
    app_header: str = ""
    object_symbol: str = ""
    path_symbol: str = ""
    driver_symbol: str = ""
    sd_handle: str = ""
    sd_instance: str = ""
    card_detect_pin: str = ""
    target_sources: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return self.enabled and not self.errors


@dataclass(frozen=True, slots=True)
class HardwareInventory:
    mcu_part: str
    mcu_name: str
    mcu_family: str
    package: str
    core: str
    cubemx_version: str
    firmware_package: str
    pins: tuple[PinInventory, ...]
    uarts: tuple[PeripheralInventory, ...]
    spis: tuple[PeripheralInventory, ...]
    i2cs: tuple[PeripheralInventory, ...]
    adcs: tuple[PeripheralInventory, ...]
    timers: tuple[PeripheralInventory, ...]
    pwms: tuple[PeripheralInventory, ...]
    cans: tuple[PeripheralInventory, ...]
    dmas: tuple[DmaInventory, ...]
    nvic: tuple[NvicInventory, ...]
    clocks: dict[str, Any]
    peripherals: tuple[str, ...]
    generated_sources: tuple[str, ...] = ()
    usb_cdc: bool = False
    timebase: TimebaseInventory = field(default_factory=TimebaseInventory)
    fatfs: FatFsInventory = field(default_factory=FatFsInventory)
    issues: tuple[str, ...] = ()

    def Dictionary_Get(self) -> dict[str, Any]:
        # HardwareConfiguration is persisted as strict JSON.  Normalize tuple
        # fields here so a freshly detected inventory is byte-semantically
        # identical to the same inventory after save/reload.
        return json.loads(json.dumps(asdict(self), ensure_ascii=False))

    def HardwareResources_Get(self) -> tuple[HardwareResource, ...]:
        resources: list[HardwareResource] = []
        if self.usb_cdc:
            resources.append(HardwareResource(
                "USB_CDC", "usb_cdc", {"capabilities": ["usb.device", "usb.cdc"],
                                         "physical_resource": "USB Device CDC"}
            ))
        groups = (
            (self.uarts, "platform_uart.h", "huart"),
            (self.spis, "platform_spi.h", "hspi"),
            (self.i2cs, "platform_i2c.h", "hi2c"),
            (self.adcs, "platform_adc.h", "hadc"),
            (self.timers, "platform_timer.h", "htim"),
            (self.pwms, "platform_pwm.h", "htim"),
            (self.cans, "platform_can.h", ""),
        )
        kind_indexes: dict[str, int] = {}
        for peripherals, header, handle_prefix in groups:
            for peripheral in peripherals:
                index = kind_indexes.get(peripheral.kind, 0)
                kind_indexes[peripheral.kind] = index + 1
                handle_instance = str(
                    peripheral.settings.get("timer_instance", peripheral.instance)
                )
                suffix_match = re.search(r"(\d+)$", handle_instance)
                suffix = suffix_match.group(1) if suffix_match else str(index + 1)
                effective_handle_prefix = handle_prefix
                if peripheral.kind == "can_classic":
                    effective_handle_prefix = "hcan"
                elif peripheral.kind == "can_fd":
                    effective_handle_prefix = "hfdcan"
                c_id_kind = {
                    "can_classic": "CAN",
                    "can_fd": "FDCAN",
                }.get(peripheral.kind, peripheral.kind.upper())
                c_id_type = {
                    "uart": "PlatformUartId",
                    "spi": "PlatformSpiId",
                    "i2c": "PlatformI2cId",
                    "adc": "PlatformAdcId",
                    "timer": "PlatformTimerId",
                    "pwm": "PlatformPwmId",
                    "can_classic": "PlatformCanId",
                    "can_fd": "PlatformFdcanId",
                }.get(peripheral.kind)
                metadata = {
                    "c_id": (
                        f"(({c_id_type}){index}U)"
                        if c_id_type is not None
                        else f"PLATFORM_{c_id_kind}_{index + 1}"
                    ),
                    "header": header,
                    "handle": f"{effective_handle_prefix}{suffix}",
                    "logical_index": index,
                    "peripheral": peripheral.instance,
                    "physical_resource": peripheral.instance,
                    "pins": dict(peripheral.pins),
                    "pin_electrical": {
                        role: {
                            "pin": pin.pin,
                            "signal": pin.signal,
                            "mode": pin.mode,
                            "alternate_function": (
                                pin.alternate_function or pin.signal
                            ),
                            "pull": pin.pull,
                            "output_type": pin.output_type,
                            "speed": pin.speed,
                        }
                        for role, physical_pin in peripheral.pins.items()
                        for pin in self.pins
                        if pin.pin == physical_pin
                    },
                    **dict(peripheral.settings),
                    "dma": [asdict(item) for item in peripheral.dma],
                }
                if peripheral.irq is not None:
                    metadata["irq"] = asdict(peripheral.irq)
                    metadata["irq_enabled"] = int(peripheral.irq.enabled)
                resources.append(
                    HardwareResource(peripheral.instance, peripheral.kind, metadata)
                )

        gpio_pins = tuple(
            pin
            for pin in self.pins
            if pin.signal in {"GPIO_Input", "GPIO_Output"}
            or "EXTI" in pin.signal.upper()
            or "GPXTI" in pin.signal.upper()
        )
        for index, pin in enumerate(sorted(gpio_pins, key=lambda value: value.pin)):
            if "EXTI" in pin.signal.upper() or "GPXTI" in pin.signal.upper():
                kind = "gpio_interrupt"
            elif pin.signal == "GPIO_Output":
                kind = "gpio_output"
            else:
                kind = "gpio_input"
            label = pin.label or pin.pin
            resource_id = re.sub(r"[^A-Za-z0-9_.-]", "_", label)
            if pin.label:
                macro = re.sub(r"[^A-Za-z0-9_]", "_", pin.label)
                port_expression = f"{macro}_GPIO_Port"
                pin_expression = f"{macro}_Pin"
            else:
                physical_match = re.fullmatch(
                    r"P([A-K])(\d+)(?:-[A-Z0-9_]+)?", pin.pin
                )
                if physical_match is None:
                    raise ValueError(
                        f"Unsupported CubeMX GPIO pin identity: {pin.pin}"
                    )
                port_expression = f"GPIO{physical_match.group(1)}"
                pin_expression = f"GPIO_PIN_{physical_match.group(2)}"
            irq = None
            if pin.exti_line is not None:
                if pin.exti_line <= 4:
                    irq_name = f"EXTI{pin.exti_line}_IRQn"
                elif pin.exti_line <= 9:
                    irq_name = "EXTI9_5_IRQn"
                else:
                    irq_name = "EXTI15_10_IRQn"
                irq = next(
                    (item for item in self.nvic if item.irq == irq_name), None
                )
            resources.append(
                HardwareResource(
                    resource_id,
                    kind,
                    {
                        "c_id": f"((PlatformGpioId){index}U)",
                        "header": "platform_gpio.h",
                        "port": port_expression,
                        "pin": pin_expression,
                        "logical_index": index,
                        "physical_pin": pin.pin,
                        "physical_resource": f"{pin.pin} ({pin.signal})",
                        "label": label,
                        "signal": pin.signal,
                        "mode": kind,
                        "pin_mode": pin.mode,
                        "alternate_function": pin.alternate_function,
                        "pull": pin.pull,
                        "output_type": pin.output_type,
                        "speed": pin.speed,
                        "output_default": pin.output_default,
                        "initial_level": pin.output_default,
                        "exti_trigger": pin.exti_trigger,
                        "locked": pin.locked,
                        "exti_line": pin.exti_line,
                        "irq": asdict(irq) if irq is not None else {},
                        "irq_enabled": int(
                            irq is not None and irq.enabled
                        ),
                    },
                )
            )
        if any(item.startswith("SDIO") for item in self.peripherals):
            sdio_dmas = tuple(
                item
                for item in self.dmas
                if item.request.startswith("SDIO_")
            )
            sdio_irq = next(
                (item for item in self.nvic if item.irq == "SDIO_IRQn"),
                None,
            )
            sdio_pins = {
                _PinSignalParts_Get(pin.signal, "SDIO"): pin.pin
                for pin in self.pins
                if pin.signal.startswith("SDIO_")
            }
            resources.append(
                HardwareResource(
                    "SDIO",
                    "sdio",
                    {
                        "c_id": "PLATFORM_SDIO_1",
                        "header": "sdio.h",
                        "handle": self.fatfs.sd_handle,
                        "peripheral": self.fatfs.sd_instance or "SDIO",
                        "physical_resource": "SDIO",
                        "pins": sdio_pins,
                        "dma": [asdict(item) for item in sdio_dmas],
                        "irq": asdict(sdio_irq) if sdio_irq is not None else {},
                        "irq_enabled": int(
                            sdio_irq is not None and sdio_irq.enabled
                        ),
                        "fatfs": asdict(self.fatfs),
                    },
                )
            )
        if self.timebase.kind:
            resources.append(
                HardwareResource(
                    "SYSTEM_TIME",
                    "time",
                    {
                        "c_id": "((PlatformTimeId)0U)",
                        "header": "platform_time.h",
                        "logical_index": 0,
                        "handle": self.timebase.handle,
                        "handle_type": "TIM_HandleTypeDef",
                        "timer_instance": self.timebase.instance,
                        "physical_resource": (
                            f"HAL Timebase {self.timebase.instance}"
                            if self.timebase.instance
                            else "HAL Timebase"
                        ),
                        "timebase": asdict(self.timebase),
                        "counter_frequency_hz": (
                            self.timebase.counter_frequency_hz
                        ),
                        "period_counts": self.timebase.period_counts,
                        "tick_frequency_hz": self.timebase.tick_frequency_hz,
                        "irq": self.timebase.irq,
                    },
                )
            )
        return tuple(resources)


def CubeMxValues_Parse(ioc_text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in ioc_text.splitlines():
        if "=" not in raw_line or raw_line.lstrip().startswith("#"):
            continue
        key, value = raw_line.split("=", 1)
        values[
            key.strip().replace("\\ ", " ").replace("\\#", "#")
        ] = (
            value.strip()
            .replace("\\ ", " ")
            .replace("\\:", ":")
            .replace("\\#", "#")
        )
    return values


def _NaturalKey_Get(value: str) -> tuple[str, int, str]:
    match = re.search(r"(\d+)$", value)
    return (
        re.sub(r"\d+$", "", value),
        int(match.group(1)) if match else -1,
        value,
    )


def _Integer_Get(value: str) -> int | str:
    try:
        return int(value, 0)
    except ValueError:
        return value


def _PinSignalParts_Get(signal: str, instance: str) -> str:
    if signal.startswith(instance + "_"):
        return signal[len(instance) + 1 :].casefold()
    return signal.casefold()


def _Pull_Normalize(value: str) -> str:
    upper = value.upper()
    if "PULLUP" in upper:
        return "up"
    if "PULLDOWN" in upper:
        return "down"
    return "none"


def _OutputType_Normalize(value: str, signal: str) -> str:
    upper = value.upper()
    if re.search(r"(?:^|_)OD(?:_|$)", upper) or "OPEN_DRAIN" in upper:
        return "open_drain"
    if signal == "GPIO_Output" or "PP" in upper or "PUSH_PULL" in upper:
        return "push_pull"
    if signal.upper().startswith("I2C"):
        return "open_drain"
    return ""


def _Speed_Normalize(value: str, signal: str) -> str:
    upper = value.upper()
    if "VERY_HIGH" in upper:
        return "very_high"
    if "HIGH" in upper:
        return "high"
    if "MEDIUM" in upper:
        return "medium"
    return "low" if signal == "GPIO_Output" else ""


def _Level_Normalize(value: str, signal: str) -> str:
    upper = value.upper()
    if re.search(r"(?:^|_)SET(?:_|$)", upper) or upper in {"HIGH", "1"}:
        return "high"
    if re.search(r"(?:^|_)RESET(?:_|$)", upper) or upper in {"LOW", "0"}:
        return "low"
    return "low" if signal == "GPIO_Output" else ""


def _ExtiTrigger_Normalize(value: str, signal: str) -> str:
    upper = f"{value} {signal}".upper()
    if "RISING_FALLING" in upper or "BOTH" in upper:
        return "both"
    if "FALLING" in upper:
        return "falling"
    if "EXTI" in upper or "GPXTI" in upper or "RISING" in upper:
        return "rising"
    return ""


def _FrequencyHz_Parse(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return max(0, value)
    text = str(value).strip()
    try:
        return max(0, int(text, 0))
    except ValueError:
        pass
    match = re.fullmatch(
        r"([0-9]+(?:\.[0-9]+)?)\s*([kKmM]?)\s*(?:bits?/s|hz)?",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return 0
    scale = {"": 1, "k": 1_000, "m": 1_000_000}[match.group(2).casefold()]
    return int(round(float(match.group(1)) * scale))


def _MacroInteger_Get(value: Any, default: int = 0) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    text = str(value).strip()
    try:
        return int(text, 0)
    except ValueError:
        expression = re.fullmatch(r"(0[xX][0-9A-Fa-f]+|\d+)\s*([+-])\s*(\d+)", text)
        if expression is not None:
            left = int(expression.group(1), 0)
            right = int(expression.group(3), 10)
            return left + right if expression.group(2) == "+" else left - right
        match = re.search(r"(\d+)(?:TQ|BIT)?$", text, re.IGNORECASE)
        return int(match.group(1)) if match else default


def _TimerClockHz_Get(instance: str, values: dict[str, str]) -> int:
    number = _MacroInteger_Get(instance)
    bus = "APB2" if number in {1, 8, 9, 10, 11} else "APB1"
    for key in (
        f"RCC.{bus}TimFreq_Value",
        f"RCC.{bus}TimerFreq_Value",
        f"RCC.{bus}TIMFreq_Value",
    ):
        frequency = _FrequencyHz_Parse(values.get(key, ""))
        if frequency > 0:
            return frequency
    bus_frequency = _FrequencyHz_Parse(values.get(f"RCC.{bus}Freq_Value", ""))
    if bus_frequency <= 0:
        return 0
    divider = values.get(f"RCC.{bus}CLKDivider", "")
    return bus_frequency if divider.upper().endswith("DIV1") else bus_frequency * 2


def _Dma_Get(values: dict[str, str]) -> tuple[DmaInventory, ...]:
    requests = sorted(
        {
            value
            for key, value in values.items()
            if re.fullmatch(r"Dma\.Request\d+", key)
        },
        key=_NaturalKey_Get,
    )
    result: list[DmaInventory] = []
    for request in requests:
        prefix = f"Dma.{request}."
        indexes = {
            key[len(prefix) :].split(".", 1)[0]
            for key in values
            if key.startswith(prefix) and "." in key[len(prefix) :]
        }
        for index in sorted(indexes, key=lambda value: int(value) if value.isdigit() else 0):
            item_prefix = f"{prefix}{index}."
            result.append(
                DmaInventory(
                    request=request,
                    instance=values.get(item_prefix + "Instance", ""),
                    direction=values.get(item_prefix + "Direction", ""),
                    mode=values.get(item_prefix + "Mode", ""),
                    priority=values.get(item_prefix + "Priority", ""),
                    channel=values.get(item_prefix + "Channel", ""),
                )
            )
    return tuple(result)


def _Nvic_Get(values: dict[str, str]) -> tuple[NvicInventory, ...]:
    result: list[NvicInventory] = []
    for key, value in sorted(values.items()):
        if not key.startswith("NVIC.") or not key.endswith("IRQn"):
            continue
        parts = value.split(":")
        enabled = bool(parts and parts[0].casefold() == "true")
        preempt = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        sub = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        result.append(NvicInventory(key[len("NVIC.") :], enabled, preempt, sub))
    return tuple(result)


def _Peripheral_Get(
    instance: str,
    kind: str,
    values: dict[str, str],
    pins: tuple[PinInventory, ...],
    dmas: tuple[DmaInventory, ...],
    nvic: tuple[NvicInventory, ...],
) -> PeripheralInventory:
    pin_map = {
        _PinSignalParts_Get(pin.signal, instance): pin.pin
        for pin in pins
        if pin.signal.startswith(instance + "_")
        or (kind == "adc" and pin.signal.startswith("ADCx_"))
    }
    settings: dict[str, Any] = {}
    prefix = instance + "."
    for key, value in values.items():
        if not key.startswith(prefix):
            continue
        name = key[len(prefix) :]
        if name in {"IPParameters"} or name.endswith("Parameters"):
            continue
        settings[name] = _Integer_Get(value)
    if kind == "uart":
        settings["baud_rate"] = _Integer_Get(values.get(prefix + "BaudRate", "0"))
        settings["mode"] = values.get(prefix + "VirtualMode", "")
        settings["word_length"] = _Integer_Get(
            re.sub(
                r"\D",
                "",
                values.get(prefix + "WordLength", "8"),
            )
            or "8"
        )
        parity = values.get(prefix + "Parity", "none").casefold()
        settings["parity"] = (
            "none" if "none" in parity else "even" if "even" in parity else "odd"
        )
        stop_bits = values.get(prefix + "StopBits", "1")
        settings["stop_bits"] = (
            2.0 if "2" in stop_bits else 1.5 if "1_5" in stop_bits else 1.0
        )
    elif kind == "spi":
        raw_mode = values.get(prefix + "Mode", values.get(prefix + "VirtualType", ""))
        settings["mode"] = "master" if "MASTER" in raw_mode.upper() else "slave"
        settings["clock_hz"] = _FrequencyHz_Parse(
            values.get(prefix + "CalculateBaudRate", "")
        )
        polarity = values.get(prefix + "CLKPolarity", "SPI_POLARITY_LOW").upper()
        phase = values.get(prefix + "CLKPhase", "SPI_PHASE_1EDGE").upper()
        first_bit = values.get(prefix + "FirstBit", "SPI_FIRSTBIT_MSB").upper()
        data_size = values.get(prefix + "DataSize", "SPI_DATASIZE_8BIT")
        data_bits_match = re.search(r"(\d+)", data_size)
        settings["cpol"] = "high" if "HIGH" in polarity else "low"
        settings["cpha"] = "2edge" if "2EDGE" in phase else "1edge"
        settings["data_bits"] = (
            int(data_bits_match.group(1)) if data_bits_match else 8
        )
        settings["bit_order"] = "lsb" if "LSB" in first_bit else "msb"
    elif kind == "i2c":
        settings["bus_frequency_hz"] = _FrequencyHz_Parse(
            values.get(
                prefix + "CalculateClockFrequency",
                values.get(prefix + "ClockSpeed", "0"),
            )
        )
        settings["address_mode"] = (
            "10bit"
            if "10BIT" in values.get(prefix + "AddressingMode", "").upper()
            else "7bit"
        )
        settings["own_address"] = _MacroInteger_Get(
            values.get(prefix + "OwnAddress1", "0")
        )
    elif kind in {"can_classic", "can_fd"}:
        raw_mode = values.get(prefix + "Mode", "")
        settings["mode"] = raw_mode.casefold().removeprefix("can_mode_")
        settings["can_kind"] = "bxcan" if kind == "can_classic" else "fdcan"
        settings["frame_format"] = "classic" if kind == "can_classic" else "fd"
        prescaler = _MacroInteger_Get(
            values.get(prefix + "Prescaler", values.get(prefix + "NominalPrescaler", "0"))
        )
        segment1 = _MacroInteger_Get(
            values.get(prefix + "TimeSeg1", values.get(prefix + "NominalTimeSeg1", "0"))
        )
        segment2 = _MacroInteger_Get(
            values.get(prefix + "TimeSeg2", values.get(prefix + "NominalTimeSeg2", "0"))
        )
        clock_hz = _FrequencyHz_Parse(
            values.get(
                prefix + "ClockFrequency",
                values.get("RCC.APB1Freq_Value", "0"),
            )
        )
        calculated = _FrequencyHz_Parse(
            values.get(
                prefix + "CalculateBaudRate",
                values.get(prefix + "NominalBitRate", "0"),
            )
        )
        if calculated <= 0 and all(value > 0 for value in (clock_hz, prescaler, segment1, segment2)):
            calculated = clock_hz // (prescaler * (1 + segment1 + segment2))
        settings.update(
            {
                "clock_hz": clock_hz,
                "nominal_bitrate": calculated,
                "prescaler": prescaler,
                "time_segment_1": segment1,
                "time_segment_2": segment2,
                "sync_jump_width": _MacroInteger_Get(
                    values.get(prefix + "SyncJumpWidth", "0")
                ),
                "automatic_bus_off": (
                    "ENABLE" in values.get(prefix + "AutoBusOff", "").upper()
                ),
                "auto_retransmission": (
                    "DISABLE"
                    not in values.get(prefix + "AutoRetransmission", "").upper()
                ),
            }
        )
    dma_items = tuple(item for item in dmas if item.request.startswith(instance + "_"))
    irq_names = {f"{instance}_IRQn", f"{instance}1_IRQn"}
    irq = next(
        (
            item
            for item in nvic
            if item.irq in irq_names or item.irq.startswith(instance + "_")
        ),
        None,
    )
    return PeripheralInventory(
        instance,
        kind,
        pin_map,
        _CaseInsensitiveKeys_Normalize(settings),
        dma_items,
        irq,
    )


def _CaseInsensitiveKeys_Normalize(values: dict[str, Any]) -> dict[str, Any]:
    """Keep inventory JSON consumable by case-insensitive PowerShell parsers.

    CubeMX commonly emits fields such as ``Mode`` while FCCG adds a normalized
    ``mode`` field.  JSON permits both, but Windows PowerShell 5 rejects that
    object.  Keep the normalized lower-case spelling and retain the raw value
    under a deterministic ``cubemx_`` name.
    """
    groups: dict[str, list[tuple[str, Any]]] = {}
    for key, value in values.items():
        groups.setdefault(key.casefold(), []).append((key, value))
    reserved = {key.casefold() for key in values}
    result: dict[str, Any] = {}
    for entries in groups.values():
        preferred = next(
            (entry for entry in entries if entry[0] == entry[0].casefold()),
            entries[0],
        )
        result[preferred[0]] = preferred[1]
        for key, value in entries:
            if key == preferred[0]:
                continue
            candidate = f"cubemx_{key}"
            suffix = 2
            while candidate.casefold() in reserved or any(
                candidate.casefold() == existing.casefold()
                for existing in result
            ):
                candidate = f"cubemx_{key}_{suffix}"
                suffix += 1
            result[candidate] = value
    return result


def _GeneratedTimerFacts_Get(
    generated_sources: tuple[str, ...],
) -> dict[tuple[str, int], dict[str, str]]:
    facts: dict[tuple[str, int], dict[str, str]] = {}
    text = "\n".join(generated_sources)
    handles = {
        handle.casefold(): timer.upper()
        for handle, timer in re.findall(
            r"\b(h?tim\d+)\.Instance\s*=\s*(TIM\d+)\s*;", text
        )
    }
    counter_modes = {
        handle.casefold(): mode.casefold()
        for handle, mode in re.findall(
            r"\b(h?tim\d+)\.Init\.CounterMode\s*=\s*"
            r"(TIM_COUNTERMODE_[A-Z0-9_]+)\s*;",
            text,
        )
    }
    call_pattern = re.compile(
        r"HAL_TIM_PWM_ConfigChannel\s*\(\s*&(?P<handle>h?tim\d+)\s*,"
        r"\s*&[A-Za-z_][A-Za-z0-9_]*\s*,\s*TIM_CHANNEL_(?P<channel>[1-4])\s*\)",
    )
    previous_end_by_handle: dict[str, int] = {}
    for match in call_pattern.finditer(text):
        handle = match.group("handle").casefold()
        timer = handles.get(handle)
        if timer is None:
            continue
        block_start = previous_end_by_handle.get(handle, max(0, match.start() - 3000))
        block = text[block_start : match.start()]
        previous_end_by_handle[handle] = match.end()
        modes = re.findall(
            r"\.OCMode\s*=\s*(TIM_OCMODE_[A-Z0-9_]+)\s*;", block
        )
        polarities = re.findall(
            r"\.OCPolarity\s*=\s*(TIM_OCPOLARITY_[A-Z0-9_]+)\s*;",
            block,
        )
        facts[(timer, int(match.group("channel")))] = {
            "pwm_mode": modes[-1].casefold() if modes else "",
            "polarity": polarities[-1].casefold() if polarities else "",
            "counter_mode": counter_modes.get(handle, ""),
            "configuration_call": "HAL_TIM_PWM_ConfigChannel",
        }
    return facts


def _PwmDeclaration_Get(
    values: dict[str, str],
) -> dict[tuple[str, int], str]:
    declarations: dict[tuple[str, int], str] = {}
    for key, raw_value in values.items():
        if not key.startswith("SH."):
            continue
        fields = [field.strip() for field in raw_value.split(",")]
        if len(fields) < 2 or "PWM Generation" not in fields[1]:
            continue
        match = re.fullmatch(r"(TIM\d+)_CH([1-4])(N)?", fields[0])
        if match is None:
            continue
        timer, channel, complementary = match.groups()
        declarations[(timer, int(channel))] = (
            "complementary" if complementary else fields[1]
        )
    return declarations


def _Pwm_Get(
    pin: PinInventory,
    timer: str,
    channel: int,
    values: dict[str, str],
    generated_facts: dict[tuple[str, int], dict[str, str]],
    declaration: str,
    pins: tuple[PinInventory, ...],
    dmas: tuple[DmaInventory, ...],
    nvic: tuple[NvicInventory, ...],
) -> PeripheralInventory:
    facts = generated_facts.get((timer, channel), {})
    base = _Peripheral_Get(timer, "pwm", values, pins, dmas, nvic)
    prefix = timer + "."
    prescaler = _MacroInteger_Get(values.get(prefix + "Prescaler", "0"))
    period = _MacroInteger_Get(values.get(prefix + "Period", "0"))
    timer_clock_hz = _TimerClockHz_Get(timer, values)
    frequency_hz = 0
    if timer_clock_hz > 0 and prescaler >= 0 and period >= 0:
        divisor = (prescaler + 1) * (period + 1)
        frequency_hz = timer_clock_hz // divisor if divisor > 0 else 0
    polarity_raw = str(facts.get("polarity", ""))
    mode_raw = str(facts.get("pwm_mode", ""))
    counter_mode_raw = str(facts.get("counter_mode", ""))
    active_high = "LOW" not in polarity_raw.upper()
    settings = {
        **base.settings,
        "timer_instance": timer,
        "channel": channel,
        "channel_token": f"TIM_CHANNEL_{channel}",
        "cubemx_pwm_declaration": declaration,
        "configuration_call": str(facts.get("configuration_call", "")),
        "pwm_mode": (
            "pwm1"
            if mode_raw.upper() == "TIM_OCMODE_PWM1"
            else "pwm2" if mode_raw.upper() == "TIM_OCMODE_PWM2" else ""
        ),
        "counter_mode": (
            "up"
            if counter_mode_raw.upper() == "TIM_COUNTERMODE_UP"
            else counter_mode_raw.casefold().removeprefix("tim_countermode_")
        ),
        "complementary": False,
        "prescaler": prescaler,
        "period_counts": period + 1,
        "timer_clock_hz": timer_clock_hz,
        "frequency_hz": frequency_hz,
        "resolution_bits": max(1, (period + 1).bit_length() - 1),
        "polarity": "active_high" if active_high else "active_low",
        "active_high": int(active_high),
        "safe_state": "inactive",
        "safe_inactive_behavior": "forced_inactive_then_stop",
        "safe_inactive_compare": 0,
        "physical_resource": f"{timer}:CH{channel}",
    }
    return PeripheralInventory(
        instance=f"{timer}_CH{channel}",
        kind="pwm",
        pins={"out": pin.pin},
        settings=settings,
        dma=base.dma,
        irq=base.irq,
    )


def _GeneratedFiles_Normalize(
    generated_sources: tuple[str, ...],
    generated_files: dict[str, str] | None,
) -> dict[str, str]:
    if generated_files is not None:
        return {
            str(path).replace("\\", "/"): text
            for path, text in generated_files.items()
        }
    result: dict[str, str] = {}
    for index, text in enumerate(generated_sources):
        name = f"generated_{index}.c"
        if "HAL_InitTick" in text:
            name = "Core/Src/stm32xx_hal_timebase_tim.c"
        elif "MX_FATFS_Init" in text:
            name = "FATFS/App/fatfs.c"
        result[name] = text
    return result


def _TimebaseInventory_Get(
    values: dict[str, str],
    generated_files: dict[str, str],
    nvic: tuple[NvicInventory, ...],
) -> TimebaseInventory:
    expected_instance = values.get("NVIC.TimeBaseIP", "").strip().upper()
    if not expected_instance:
        virtual_modes = {
            value.strip().upper()
            for key, value in values.items()
            if key.startswith("VP_SYS_VS_") and key.endswith(".Mode")
        }
        timer_modes = sorted(
            value for value in virtual_modes if re.fullmatch(r"TIM\d+", value)
        )
        if len(timer_modes) == 1:
            expected_instance = timer_modes[0]
    expected_irq = values.get("NVIC.TimeBase", "").strip()
    timebase_files = {
        path: text
        for path, text in generated_files.items()
        if path.casefold().endswith("_hal_timebase_tim.c")
        or "HAL_InitTick" in text
    }
    errors: list[str] = []
    if not re.fullmatch(r"TIM\d+", expected_instance):
        return TimebaseInventory(
            kind="systick" if not expected_instance else expected_instance.casefold(),
            irq=expected_irq,
            errors=(
                "CubeMX HAL Timebase must use one TIM peripheral / "
                "CubeMX HAL 时间基准必须使用唯一 TIM 外设",
            ),
        )
    if len(timebase_files) != 1:
        errors.append(
            "Exactly one generated HAL TIM timebase source is required / "
            "必须存在且仅存在一个 HAL TIM 时间基准源文件"
        )
    source = next(iter(timebase_files), "")
    text = timebase_files.get(source, "")
    handles = tuple(
        dict.fromkeys(
            re.findall(
                r"\bTIM_HandleTypeDef\s+([A-Za-z_][A-Za-z0-9_]*)\s*;",
                text,
            )
        )
    )
    if len(handles) != 1:
        errors.append(
            "HAL TIM timebase must declare exactly one handle / "
            "HAL TIM 时间基准必须声明唯一句柄"
        )
    handle = handles[0] if len(handles) == 1 else ""
    instance_matches = tuple(
        dict.fromkeys(
            match.upper()
            for match in re.findall(
                rf"\b{re.escape(handle)}\.Instance\s*=\s*(TIM\d+)\s*;",
                text,
            )
        )
    ) if handle else ()
    instance = instance_matches[0] if len(instance_matches) == 1 else ""
    if len(instance_matches) != 1 or instance != expected_instance:
        errors.append(
            "Generated HAL timebase handle/instance does not match .ioc / "
            "生成的 HAL 时间基准句柄或实例与 .ioc 不一致"
        )
    generated_irqs = tuple(
        dict.fromkeys(
            re.findall(r"HAL_NVIC_EnableIRQ\s*\(\s*([A-Za-z_][A-Za-z0-9_]*_IRQn)\s*\)", text)
        )
    )
    generated_irq = generated_irqs[0] if len(generated_irqs) == 1 else ""
    if (
        not expected_irq
        or len(generated_irqs) != 1
        or generated_irq != expected_irq
    ):
        errors.append(
            "HAL Timebase IRQ is missing or inconsistent / "
            "HAL 时间基准 IRQ 缺失或不一致"
        )
    nvic_entry = next((item for item in nvic if item.irq == expected_irq), None)
    if nvic_entry is None or not nvic_entry.enabled:
        errors.append(
            "HAL Timebase IRQ is not enabled in CubeMX NVIC / "
            "CubeMX NVIC 未启用 HAL 时间基准 IRQ"
        )
    counter_matches = tuple(
        dict.fromkeys(
            int(value)
            for value in re.findall(
                r"uwTimclock\s*/\s*(\d+)U?\s*\)\s*-\s*1U?",
                text,
            )
        )
    )
    counter_frequency_hz = counter_matches[0] if len(counter_matches) == 1 else 0
    period_matches = tuple(
        dict.fromkeys(
            (int(counter), int(tick))
            for counter, tick in re.findall(
                rf"\b{re.escape(handle)}\.Init\.Period\s*=\s*\(\s*(\d+)U?\s*/\s*(\d+)U?\s*\)\s*-\s*1U?",
                text,
            )
        )
    ) if handle else ()
    period_counter, tick_frequency_hz = (
        period_matches[0] if len(period_matches) == 1 else (0, 0)
    )
    period_counts = (
        period_counter // tick_frequency_hz
        if tick_frequency_hz > 0 and period_counter % tick_frequency_hz == 0
        else 0
    )
    if (
        counter_frequency_hz != 1_000_000
        or period_counter != counter_frequency_hz
        or tick_frequency_hz != 1_000
        or period_counts != 1_000
    ):
        errors.append(
            "HAL Timebase must prove a 1 MHz counter and 1 ms period / "
            "HAL 时间基准必须可证明为 1 MHz 计数与 1 ms 周期"
        )
    interrupt_started = bool(
        handle
        and re.search(
            rf"HAL_TIM_Base_Start_IT\s*\(\s*&{re.escape(handle)}\s*\)",
            text,
        )
    )
    if not interrupt_started:
        errors.append(
            "HAL Timebase is not started in interrupt mode / "
            "HAL 时间基准未以中断模式启动"
        )
    return TimebaseInventory(
        kind="tim",
        source=source,
        handle=handle,
        instance=instance,
        irq=generated_irq or expected_irq,
        counter_frequency_hz=counter_frequency_hz,
        period_counts=period_counts,
        tick_frequency_hz=tick_frequency_hz,
        interrupt_started=interrupt_started,
        errors=tuple(dict.fromkeys(errors)),
    )


def _FatFsInventory_Get(
    values: dict[str, str],
    peripherals: tuple[str, ...],
    generated_files: dict[str, str],
) -> FatFsInventory:
    enabled = "FATFS" in peripherals
    if not enabled:
        return FatFsInventory()
    errors: list[str] = []
    app_sources = {
        path: text
        for path, text in generated_files.items()
        if path.casefold().endswith("/fatfs/app/fatfs.c")
        or path.casefold() == "fatfs/app/fatfs.c"
    }
    app_headers = {
        path: text
        for path, text in generated_files.items()
        if path.casefold().endswith("/fatfs/app/fatfs.h")
        or path.casefold() == "fatfs/app/fatfs.h"
    }
    if len(app_sources) != 1 or len(app_headers) != 1:
        errors.append(
            "CubeMX FatFs requires one FATFS/App/fatfs.c and fatfs.h / "
            "CubeMX FatFs 必须包含唯一 FATFS/App/fatfs.c 与 fatfs.h"
        )
    app_source = next(iter(app_sources), "")
    app_header = next(iter(app_headers), "")
    combined = "\n".join((*app_sources.values(), *app_headers.values()))
    object_symbols = tuple(
        dict.fromkeys(
            re.findall(r"(?:extern\s+)?FATFS\s+([A-Za-z_][A-Za-z0-9_]*)\s*;", combined)
        )
    )
    path_symbols = tuple(
        dict.fromkeys(
            re.findall(r"(?:extern\s+)?char\s+([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*\d+\s*\]\s*;", combined)
        )
    )
    link_matches = tuple(
        dict.fromkeys(
            re.findall(
                r"FATFS_LinkDriver(?:Ex)?\s*\(\s*&([A-Za-z_][A-Za-z0-9_]*)\s*,\s*([A-Za-z_][A-Za-z0-9_]*)",
                combined,
            )
        )
    )
    if len(object_symbols) != 1 or len(path_symbols) != 1 or len(link_matches) != 1:
        errors.append(
            "CubeMX FatFs object/path/driver symbols are missing or ambiguous / "
            "CubeMX FatFs 对象、路径或驱动符号缺失或存在歧义"
        )
    object_symbol = object_symbols[0] if len(object_symbols) == 1 else ""
    path_symbol = path_symbols[0] if len(path_symbols) == 1 else ""
    driver_symbol = link_matches[0][0] if len(link_matches) == 1 else ""
    if len(link_matches) == 1 and path_symbol != link_matches[0][1]:
        errors.append(
            "CubeMX FatFs linked path symbol does not match its declaration / "
            "CubeMX FatFs 链接路径符号与声明不一致"
        )
    sdio_text = "\n".join(
        text
        for path, text in generated_files.items()
        if path.casefold().endswith("/core/src/sdio.c")
        or path.casefold() == "core/src/sdio.c"
    )
    handles = tuple(
        dict.fromkeys(
            re.findall(r"\bSD_HandleTypeDef\s+([A-Za-z_][A-Za-z0-9_]*)\s*;", sdio_text)
        )
    )
    sd_handle = handles[0] if len(handles) == 1 else ""
    instances = tuple(
        dict.fromkeys(
            re.findall(
                rf"\b{re.escape(sd_handle)}\.Instance\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\s*;",
                sdio_text,
            )
        )
    ) if sd_handle else ()
    sd_instance = instances[0] if len(instances) == 1 else ""
    if len(handles) != 1 or len(instances) != 1 or sd_instance != "SDIO":
        errors.append(
            "CubeMX SDIO handle/instance is missing or ambiguous / "
            "CubeMX SDIO 句柄或实例缺失或存在歧义"
        )
    target_sources = tuple(
        sorted(
            path
            for path in generated_files
            if "/fatfs/target/" in ("/" + path.casefold())
            and path.casefold().endswith(".c")
        )
    )
    if not target_sources:
        errors.append(
            "CubeMX FatFs Target glue is missing / CubeMX FatFs Target 胶水缺失"
        )
    if "SDIO" not in peripherals:
        errors.append(
            "FatFs is enabled without STM32 SDIO / 已启用 FatFs 但未启用 STM32 SDIO"
        )
    return FatFsInventory(
        enabled=True,
        app_source=app_source,
        app_header=app_header,
        object_symbol=object_symbol,
        path_symbol=path_symbol,
        driver_symbol=driver_symbol,
        sd_handle=sd_handle,
        sd_instance=sd_instance,
        card_detect_pin=values.get("FATFS0.BSP.instance", ""),
        target_sources=target_sources,
        errors=tuple(dict.fromkeys(errors)),
    )


def CubeMxInventory_Parse(
    ioc_text: str,
    *,
    generated_sources: tuple[str, ...] = (),
    generated_files: dict[str, str] | None = None,
) -> HardwareInventory:
    values = CubeMxValues_Parse(ioc_text)
    normalized_generated_files = _GeneratedFiles_Normalize(
        generated_sources, generated_files
    )
    peripherals = tuple(
        sorted(
            {
                value
                for key, value in values.items()
                if re.fullmatch(r"Mcu\.IP\d+", key)
            },
            key=_NaturalKey_Get,
        )
    )
    usb_device_selected = "USB_DEVICE" in peripherals
    cdc_class_selected = any(
        key.startswith("USB_DEVICE.") and "CDC" in value.upper()
        for key, value in values.items()
    )
    cdc_source_present = any(
        path.replace("\\", "/").lower().endswith("usbd_cdc_if.c")
        for path in normalized_generated_files
    )
    usb_cdc = usb_device_selected and cdc_class_selected and cdc_source_present
    pins: list[PinInventory] = []
    for key, signal in values.items():
        if not key.endswith(".Signal"):
            continue
        pin = key[: -len(".Signal")]
        if not re.fullmatch(r"P[A-K][0-9]+(?:-[A-Z0-9_]+)?", pin):
            continue
        exti_match = re.search(r"(?:GPXTI|EXTI)(\d+)", signal, re.IGNORECASE)
        mode_value = values.get(
            f"{pin}.GPIO_ModeDefaultEXTI",
            values.get(f"{pin}.GPIO_Mode", values.get(f"{pin}.Mode", "")),
        )
        output_type_value = values.get(
            f"{pin}.GPIO_ModeDefaultOutputPP",
            values.get(f"{pin}.GPIO_OutputType", mode_value),
        )
        output_default_value = values.get(f"{pin}.PinState", "")
        pins.append(
            PinInventory(
                pin=pin,
                signal=signal,
                label=values.get(f"{pin}.GPIO_Label", ""),
                mode=mode_value,
                alternate_function=values.get(
                    f"{pin}.GPIO_AF",
                    values.get(
                        f"{pin}.GPIO_AFName",
                        values.get(f"{pin}.GPIO_AFValue", ""),
                    ),
                ),
                pull=_Pull_Normalize(values.get(f"{pin}.GPIO_PuPd", "")),
                output_default=_Level_Normalize(output_default_value, signal),
                output_type=_OutputType_Normalize(output_type_value, signal),
                speed=_Speed_Normalize(
                    values.get(f"{pin}.GPIO_Speed", ""), signal
                ),
                exti_trigger=_ExtiTrigger_Normalize(mode_value, signal),
                locked=values.get(f"{pin}.Locked", "false").casefold()
                == "true",
                exti_line=int(exti_match.group(1)) if exti_match else None,
            )
        )
    pin_values = tuple(sorted(pins, key=lambda value: value.pin))
    dmas = _Dma_Get(values)
    nvic = _Nvic_Get(values)

    def group(prefixes: tuple[str, ...], kind: str) -> tuple[PeripheralInventory, ...]:
        return tuple(
            _Peripheral_Get(item, kind, values, pin_values, dmas, nvic)
            for item in peripherals
            if item.startswith(prefixes)
        )

    timers = group(("TIM", "LPTIM"), "timer")
    pwm_declarations = _PwmDeclaration_Get(values)
    all_generated_sources = tuple(normalized_generated_files.values())
    generated_timer_facts = _GeneratedTimerFacts_Get(all_generated_sources)
    pwm_values: list[PeripheralInventory] = []
    pwm_issues: list[str] = []
    pins_by_signal: dict[str, PinInventory] = {}
    for pin in pin_values:
        normalized_signal = pin.signal.removeprefix("S_")
        signal_match = re.fullmatch(
            r"(TIM\d+_CH[1-4])(?:_ETR)?", normalized_signal
        )
        if signal_match is not None:
            pins_by_signal[signal_match.group(1)] = pin
    for (timer, channel), declaration in sorted(pwm_declarations.items()):
        resource_name = f"{timer}_CH{channel}"
        pin = pins_by_signal.get(resource_name)
        facts = generated_timer_facts.get((timer, channel), {})
        problems: list[str] = []
        if declaration == "complementary":
            problems.append("complementary CHxN output is unsupported")
        if pin is None:
            problems.append("no physical output pin is assigned")
        if facts.get("configuration_call") != "HAL_TIM_PWM_ConfigChannel":
            problems.append("generated code has no HAL_TIM_PWM_ConfigChannel call")
        if facts.get("pwm_mode") not in {
            "tim_ocmode_pwm1",
            "tim_ocmode_pwm2",
        }:
            problems.append("PWM1/PWM2 mode is missing or unsupported")
        if facts.get("polarity") not in {
            "tim_ocpolarity_high",
            "tim_ocpolarity_low",
        }:
            problems.append("output polarity is missing or unsupported")
        if facts.get("counter_mode") != "tim_countermode_up":
            problems.append("only edge-aligned up-counter mode is supported")
        timer_prefix = timer + "."
        if any(
            token in f"{key}={value}".upper()
            for key, value in values.items()
            if key.startswith(timer_prefix)
            for token in (
                "CENTERALIGNED",
                "COMBINED",
                "ASYMMETRIC",
                "ONEPULSE",
                "ENCODER",
                "DEADTIME",
            )
        ):
            problems.append("advanced/combined timer mode is unsupported")
        if problems:
            pwm_issues.append(
                f"inventory.pwm.{resource_name}: " + "; ".join(problems)
            )
            continue
        assert pin is not None
        pwm_values.append(
            _Pwm_Get(
                pin,
                timer,
                channel,
                values,
                generated_timer_facts,
                declaration,
                pin_values,
                dmas,
                nvic,
            )
        )
    for resource_name, pin in sorted(pins_by_signal.items()):
        match = re.fullmatch(r"(TIM\d+)_CH([1-4])", resource_name)
        if match is None or (match.group(1), int(match.group(2))) in pwm_declarations:
            continue
        shared_modes = tuple(
            fields[1].strip()
            for key, raw_value in values.items()
            if key.startswith("SH.")
            for fields in ([field.strip() for field in raw_value.split(",")],)
            if len(fields) >= 2 and fields[0] == resource_name
        )
        mode_text = ", ".join(shared_modes) if shared_modes else "pin signal only"
        pwm_issues.append(
            f"inventory.pwm.{resource_name}: {mode_text} is not a supported "
            f"CubeMX PWM Generation channel ({pin.pin})"
        )
    timebase = _TimebaseInventory_Get(values, normalized_generated_files, nvic)
    if timebase.instance:
        conflicting = tuple(
            pwm
            for pwm in pwm_values
            if pwm.settings.get("timer_instance") == timebase.instance
        )
        if conflicting:
            pwm_values = [
                pwm
                for pwm in pwm_values
                if pwm.settings.get("timer_instance") != timebase.instance
            ]
            pwm_issues.append(
                "inventory.timebase_pwm_conflict: "
                f"{timebase.instance} is reserved by the CubeMX HAL Timebase / "
                f"{timebase.instance} 已由 CubeMX HAL 时间基准独占"
            )
    pwms = tuple(pwm_values)
    fatfs = _FatFsInventory_Get(
        values, peripherals, normalized_generated_files
    )
    clock_prefixes = ("RCC.", "Clock.")
    clocks = {
        key: _Integer_Get(value)
        for key, value in sorted(values.items())
        if key.startswith(clock_prefixes)
        and (
            "Freq" in key
            or key.endswith("Source")
            or key.endswith("VALUE")
            or key.endswith("Divider")
        )
    }
    issues: list[str] = []
    if not dmas:
        issues.append("inventory.dma_missing")
    if not nvic:
        issues.append("inventory.nvic_missing")
    if not pin_values:
        issues.append("inventory.pinout_missing")
    issues.extend(pwm_issues)
    issues.extend(f"inventory.timebase: {message}" for message in timebase.errors)
    issues.extend(f"inventory.fatfs: {message}" for message in fatfs.errors)
    return HardwareInventory(
        mcu_part=values.get(
            "Mcu.CPN", values.get("Mcu.Name", values.get("ProjectManager.DeviceId", ""))
        ),
        mcu_name=values.get("Mcu.Name", ""),
        mcu_family=values.get("Mcu.Family", ""),
        package=values.get("Mcu.Package", ""),
        core=values.get(
            "Mcu.Core",
            values.get("Mcu.CPU", values.get("Mcu.UserName", "")),
        ),
        cubemx_version=values.get("MxCube.Version", ""),
        firmware_package=values.get("ProjectManager.FirmwarePackage", ""),
        pins=pin_values,
        uarts=group(("USART", "UART", "LPUART"), "uart"),
        spis=group(("SPI",), "spi"),
        i2cs=group(("I2C",), "i2c"),
        adcs=group(("ADC",), "adc"),
        timers=timers,
        pwms=pwms,
        cans=(
            *group(("CAN",), "can_classic"),
            *group(("FDCAN",), "can_fd"),
        ),
        dmas=dmas,
        nvic=nvic,
        clocks=clocks,
        peripherals=peripherals,
        usb_cdc=usb_cdc,
        generated_sources=tuple(sorted(normalized_generated_files)),
        timebase=timebase,
        fatfs=fatfs,
        issues=tuple(issues),
    )
