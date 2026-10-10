"""Auditable derivatives of recognized native HAL sources; originals stay frozen.

These are source profiles, not MCU admission lists. Unknown source bytes need
review. The SPI increment bounds the blocking entry points used by SCG and their
flag waiter. Other HAL entry points keep their upstream behavior and limitations.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re

from silverstar_fccg.hardware.native_classic_cdc import NATIVE_PREFIX


REVIEWED_HAL_PREFIX = "HardwareGenerated/ReviewedNativeHal/"
_PROFILES = {
    "74c20012ae5e579f6f720b941e66cae7b39ca47d80d873dc53d2274519795802": ("spi", "ST F1 HAL 1.8.7"),
    "641ad467e834c17a83c445cf8eea7c8317a71976d7e0c77da740be999251efe4": ("spi", "ST F4 HAL 1.28.3"),
    "0baff878faf8551e43ad63959f04bae08d61ee94e686e56a56cd97d02535c4d9": ("uart", "ST F1 HAL 1.8.7"),
    "a74ed3a9a13a4fcbaada9e6f88f7d4fcabe2a75852a6ce4c09f8d4314a2e851a": ("uart", "ST F4 HAL 1.28.3"),
}


def NativeC_VisibleGet(source: str) -> str:
    """Keep offsets while excluding comments and string/character literals."""
    pattern = r'/\*.*?\*/|//[^\r\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    return re.sub(pattern, lambda match: "".join("\n" if c == "\n" else " "
                  for c in match[0]), source, flags=re.S)


def NativeC_FunctionSpanGet(source: str, name: str) -> tuple[int, int, int]:
    visible = NativeC_VisibleGet(source)
    pattern = (r"(?m)^[ \t]*(?:(?:static|__weak)\s+)?[A-Za-z_][\w \t*]*\b" +
               re.escape(name) + r"\s*\([^;{}]*\)\s*\{")
    matches = list(re.finditer(pattern, visible))
    if len(matches) != 1:
        raise ValueError("Native function needs one actual definition: " + name)
    match = matches[0]
    opening = match.end() - 1
    depth = 1
    for index in range(opening + 1, len(visible)):
        depth += (visible[index] == "{") - (visible[index] == "}")
        if depth == 0:
            return match.start(), opening, index + 1
    raise ValueError("Native function has unmatched braces: " + name)


def _SpiBounded_Apply(source: str) -> str:
    for name, expected in (("HAL_SPI_Transmit", 2), ("HAL_SPI_TransmitReceive", 2),
                           ("SPI_WaitFlagStateUntilTimeout", 1)):
        start, opening, end = NativeC_FunctionSpanGet(source, name)
        function = source[start:end]
        visible = NativeC_VisibleGet(function)
        insertions = []
        for match in re.finditer(r"\bwhile\s*\(", visible):
            position = match.end()
            depth = 1
            while depth and position < len(visible):
                depth += (visible[position] == "(") - (visible[position] == ")")
                position += 1
            while position < len(visible) and visible[position].isspace():
                position += 1
            if depth or position == len(visible) or visible[position] != "{":
                raise ValueError("Unknown native blocking SPI loop body")
            if name == "SPI_WaitFlagStateUntilTimeout":
                guard = """
    /* Enter the existing timeout cleanup even when native HAL tick stops. */
    if (native_poll_budget == 0U) { Timeout = 0U; tmp_timeout = 0U; }
    else { native_poll_budget--; }
"""
            else:
                guard = """
      /* An ordinary bounded timeout; no successful transfer is published. */
      if (native_poll_budget == 0U)
      {
        hspi->State = HAL_SPI_STATE_READY;
        __HAL_UNLOCK(hspi);
        return HAL_TIMEOUT;
      }
      native_poll_budget--;
"""
            insertions.append((position + 1, guard))
        if len(insertions) != expected:
            raise ValueError("Native SPI loop inventory changed: " + name)
        for position, guard in reversed(insertions):
            function = function[:position] + guard + function[position:]
        local = opening - start + 1
        function = (function[:local] + "\n  uint32_t native_poll_budget = 2000000U;\n" +
                    function[local:])
        source = source[:start] + function + source[end:]
    return source


def _UartPointer_Apply(source: str) -> str:
    for name, state in (("HAL_UART_Transmit", "gState"),
                        ("HAL_UARTEx_ReceiveToIdle", "RxState")):
        start, _opening, end = NativeC_FunctionSpanGet(source, name)
        function = source[start:end]
        visible = NativeC_VisibleGet(function)
        matches = list(re.finditer(r"if\s*\(pdata8bits\s*==\s*NULL\)\s*\{", visible))
        if len(matches) != 1:
            raise ValueError("Native UART pointer owner branch changed: " + name)
        position = matches[0].end()
        guard = f"""
        /* Both alternate pointers unavailable is a failed buffer contract. */
        if (pdata16bits == NULL)
        {{
          huart->{state} = HAL_UART_STATE_READY;
          return HAL_ERROR;
        }}
"""
        function = function[:position] + guard + function[position:]
        source = source[:start] + function + source[end:]
    return source


def NativeHalDerivatives_Render(files: dict[str, bytes], sources: list[str] | tuple[str, ...]
                                ) -> tuple[dict[str, bytes], dict[str, str], dict]:
    rendered: dict[str, bytes] = {}
    replacements: dict[str, str] = {}
    entries = []
    for kind in ("spi", "uart"):
        owners = [path for path in sources if re.fullmatch(
            r"Drivers/STM32[A-Za-z0-9]+_HAL_Driver/Src/stm32[a-z0-9]+_hal_" + kind + r"\.c", path)]
        if len(owners) != 1:
            raise ValueError("One native HAL source owner required: " + kind)
        path = owners[0]
        original = files[path]
        digest = hashlib.sha256(original).hexdigest()
        profile = _PROFILES.get(digest)
        if profile is None or profile[0] != kind:
            raise ValueError("Unreviewed native HAL source bytes: " + path)
        source = original.decode("utf-8-sig")
        derived = (_SpiBounded_Apply(source) if kind == "spi" else _UartPointer_Apply(source)).encode("utf-8")
        target = REVIEWED_HAL_PREFIX + path
        rendered[target] = derived
        replacements[NATIVE_PREFIX + path] = target
        patch = target + ".patch"
        rendered[patch] = "".join(difflib.unified_diff(source.splitlines(keepends=True),
            derived.decode("utf-8").splitlines(keepends=True),
            fromfile=NATIVE_PREFIX + path, tofile=NATIVE_PREFIX + path)).encode("utf-8")
        entries.append({"profile": profile[1], "kind": kind, "original": NATIVE_PREFIX + path,
                        "original_sha256": digest, "derived": target,
                        "derived_sha256": hashlib.sha256(derived).hexdigest(), "patch": patch,
                        "patch_sha256": hashlib.sha256(rendered[patch]).hexdigest()})
    manifest = {"format_version": 1, "entries": entries,
                "patch_policy": "Apply same-path unified patches only to an isolated copy of the original; publish the result at derived and retain original bytes",
                "spi_scope": "Only SCG-used blocking Transmit/TransmitReceive and their flag waiter; 2000000 polls per function; no time/WCET proof",
                "uart_scope": "Check alternate 16-bit pointer before dereference; buffer capacity/alignment and caller ownership remain required",
                "upstream_limits": "Other HAL APIs, internal callbacks and native initialization retain vendor limitations; not whole-firmware original Power-of-Ten compliance"}
    rendered[REVIEWED_HAL_PREFIX + "manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    return rendered, replacements, manifest
