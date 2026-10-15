"""Read-only capability inspection and separate CDC integration-kit export.

This is not Ground admission, a native build executor, or firmware acceptance.
No project flag, part string or textual match can grant those authorities.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re

from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.usb_cdc_transport import UsbCdcTransport_Render
from silverstar_fccg.hardware.cubemx import CubeMxImportError
from silverstar_fccg.hardware.usb_transport_capabilities import UsbCapabilities_Inspect


class UsbTransportPlanResult(str, Enum):
    Experimental = "Experimental"
    Rejected = "Rejected"


@dataclass(frozen=True, slots=True)
class UsbTransportPlan:
    result: UsbTransportPlanResult
    stack: str
    part: str
    indexed: bool
    reasons: tuple[str, ...]
    files_sha256: dict[str, str]
    owners: dict[str, str]
    licenses: tuple[str, ...]
    review: tuple[str, ...]
    capabilities: dict


_REVIEW = (
    "Clock/PHY/VBUS/IRQ/linker correctness: NOT PROVEN",
    "Explicit successful configure/retire/RX hooks: NOT PROVEN",
    "Native LL error propagation and physical cancellation: NOT PROVEN",
    "Complete critical contracts, stack/WCET and hardware: NOT PROVEN",
    "One main owner plus USB IRQ; no RTOS/DMA/cache/composite supported",
)
_IGNORED = {".git", "build", "debug", "release", ".idea", ".vscode"}


def _Project_Read(root: Path) -> dict[str, bytes]:
    if root.is_symlink() or root.is_junction() or not root.is_dir():
        raise CubeMxImportError("USB input must be a real project directory")
    # Resolve redirected user folders once; files below the selected source root
    # must still be regular, unaliased files. This input is always read-only.
    root = root.resolve()
    policy = WorkspacePolicy(root)
    files = {}
    total = 0
    visited = 0
    for directory, directories, names in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories if name.casefold() not in _IGNORED]
        for name in directories + names:
            path = Path(directory) / name
            relative = path.relative_to(root)
            visited += 1
            if visited > 16000:
                raise CubeMxImportError("USB inspection exceeds 16000 entries")
            policy.Path_Resolve(path, allow_root=False)
            if path.is_symlink() or path.is_junction():
                raise CubeMxImportError("USB source aliases are not supported")
            if not path.is_file():
                continue
            if ("license" not in name.casefold() and "release_notes" not in name.casefold() and
                    path.suffix.casefold() not in {".ioc", ".c", ".h", ".s", ".ld", ".txt", ".cmake", ".md"}
                    and path.name not in {"Makefile", "LICENSE", "COPYING", "scg-usb-build.json"}):
                continue
            remaining = 64 * 1024 * 1024 - total
            if path.stat().st_size > remaining:
                raise CubeMxImportError("USB source inspection exceeds 64 MiB")
            with path.open("rb") as stream:
                body = stream.read(remaining + 1)
            if len(body) > remaining:
                raise CubeMxImportError("USB source grew beyond the inspection bound")
            total += len(body)
            files[relative.as_posix()] = body
    return files


def _Code_Read(body: bytes) -> str:
    text = body.decode("utf-8-sig", errors="replace")
    return re.sub(r"/\*.*?\*/|//[^\r\n]*", "", text, flags=re.S)


def UsbTransport_Plan(input_path: str | Path) -> UsbTransportPlan:
    root = Path(input_path).absolute()
    files = _Project_Read(root)
    hashes = {p: hashlib.sha256(b).hexdigest() for p, b in sorted(files.items())}
    iocs = [p for p in files if "/" not in p and p.endswith(".ioc")]
    reasons = []
    owners = {}
    if len(iocs) != 1:
        reasons.append("ONE_ROOT_IOC_REQUIRED")
    ioc = files[iocs[0]].decode("utf-8-sig", errors="replace") if len(iocs) == 1 else ""
    values = dict(line.split("=", 1) for line in ioc.splitlines() if "=" in line)
    part = values.get("Mcu.CPN", values.get("Mcu.Name", "UNKNOWN"))
    code = {p: _Code_Read(b) for p, b in files.items() if p.endswith((".c", ".h"))}
    native = "\n".join(code.values())
    application = "\n".join(body for p, body in code.items() if p.endswith(".c") and
        not any(part.casefold() in {"drivers", "middlewares"} for part in Path(p).parts))
    usbx = ("USBX" in ioc.upper() or any("ux_device" in p.lower() or
            "usbx" in p.lower() for p in files))
    required = ("usbd_cdc.c", "usbd_cdc.h", "usbd_def.h", "usbd_core.c", "usbd_core.h",
                "usbd_ctlreq.c", "usbd_ctlreq.h", "usbd_ioreq.c", "usbd_ioreq.h", "usbd_desc.c", "usbd_desc.h",
                "usbd_cdc_if.c", "usbd_cdc_if.h", "usb_device.c", "usb_device.h",
                "usbd_conf.c", "usbd_conf.h", "main.c", "main.h")
    for name in required:
        candidates = [p for p in files if Path(p).name == name]
        if len(candidates) != 1:
            reasons.append("MISSING_OR_AMBIGUOUS_OWNER:" + name)
        else:
            owners[name] = candidates[0]
    stack = "USBX" if usbx else ("ST_USB_DEVICE_CDC" if "usbd_cdc.c" in owners else
        ("PCD_ONLY" if "HAL_PCD_Init" in native else "UNKNOWN"))
    if usbx:
        reasons.append("USBX_REQUIRES_SEPARATE_ADAPTER")
    elif stack != "ST_USB_DEVICE_CDC":
        reasons.append("COMPLETE_NATIVE_CDC_REQUIRED")
    if not re.search(r"USB_DEVICE\.[^=]*Class[^=]*=Cdc\b", ioc, re.I):
        reasons.append("IOC_SINGLE_CDC_CLASS_REQUIRED")
    if (re.search(r"=USB_OTG_HS\b|=HIGH_SPEED\b|=USBX\b", ioc, re.I) or
            "hUsbDeviceHS" in code.get(owners.get("usb_device.c", ""), "")):
        reasons.append("HIGH_SPEED_OR_ALTERNATE_STACK_UNSUPPORTED")
    if re.search(r"COMPOSITE|=FREERTOS\b|=THREADX\b", ioc, re.I):
        reasons.append("COMPOSITE_OR_RTOS_OWNER_UNSUPPORTED")
    if re.search(r"dma_enable\s*=\s*(?:ENABLE|1)|SCB_EnableDCache\s*\(", application):
        reasons.append("DMA_OR_DATA_CACHE_UNSUPPORTED")
    app = code.get(owners.get("usb_device.c", ""), "")
    interface = code.get(owners.get("usbd_cdc_if.c", ""), "")
    definition = code.get(owners.get("usbd_def.h", ""), "")
    indexed = "pClassDataCmsit" in definition
    if not all(token in app for token in ("hUsbDeviceFS", "MX_USB_DEVICE_Init", "USBD_RegisterClass")):
        reasons.append("SINGLE_FS_INIT_OWNER_REQUIRED")
    if (len(re.findall(r"USBD_RegisterClass\s*\(", app)) != 1 or
            "USBD_RegisterClassComposite" in app):
        reasons.append("SINGLE_CLASS_REQUIRED")
    if not all(token in interface for token in ("CDC_Transmit_FS", "CDC_Receive_FS", "USBD_CDC_ReceivePacket")):
        reasons.append("CLASSIC_FS_INTERFACE_ABI_REQUIRED")
    if (not indexed and "pClassData" not in definition) or "TxState" not in native:
        reasons.append("CLASS_STORAGE_ABI_UNRECOGNIZED")
    if "HAL_PCD_IRQHandler" not in application or not any(p.lower().endswith(".s") for p in files):
        reasons.append("NATIVE_IRQ_AND_STARTUP_REQUIRED")
    if not any(p.endswith(".ld") for p in files):
        reasons.append("NATIVE_LINKER_REQUIRED")
    if not any(Path(p).name in {"Makefile", "CMakeLists.txt", "scg-usb-build.json"} for p in files):
        reasons.append("NATIVE_BUILD_DESCRIPTION_REQUIRED")
    if "SystemClock_Config" not in native:
        reasons.append("NATIVE_CLOCK_OWNER_REQUIRED")
    licenses = tuple(sorted(p for p in files if "license" in Path(p).name.lower() or
                            Path(p).name == "COPYING"))
    capabilities, capability_reasons = UsbCapabilities_Inspect(files, owners)
    reasons.extend(capability_reasons)
    capabilities["layers"] = {
        "stack": stack, "class_abi": ("indexed" if indexed else "legacy") if stack == "ST_USB_DEVICE_CDC" else "NOT_CLASSIC",
        "link": "FS_SINGLE_CDC" if stack == "ST_USB_DEVICE_CDC" else "UNRESOLVED",
        "scheduler": "UNRESOLVED_USBX_EXECUTION" if usbx else "MAIN_PLUS_USB_IRQ_ONLY", "buffer_owner": "CPU_STATIC_COPY",
        "unsupported": ["USBX_STANDALONE_ADAPTER", "USBX_THREADX_ADAPTER", "HS",
                        "DMA", "DATA_CACHE", "COMPOSITE", "CLASSIC_RTOS"],
        "native_configuration_owner": "CUBEMX_INPUT",
    }
    conf = code.get(owners.get("usbd_conf.c", ""), "")
    capabilities["configuration_findings"] = []
    if ("HAL_PCDEx_SetTxFiFo" in conf and not
            re.search(r"HAL_PCDEx_SetTxFiFo\s*\([^,]+,\s*2[Uu]?\s*,", conf)):
        capabilities["configuration_findings"].append(
            "NATIVE_TX_FIFO_EP2_NOT_EXPLICIT: inspect CDC notification endpoint allocation; runtime configuration guard must pass")
    if not reasons:
        from silverstar_fccg.generator.usb_cdc_integration import UsbIntegrationProfile_Get
        try:
            profile = UsbIntegrationProfile_Get(files)
            capabilities["automatic_integration"] = {"status": "SOURCE_SHAPE_AVAILABLE", "profile": profile}
        except ValueError as error:
            capabilities["automatic_integration"] = {"status": "MANUAL_HOOKS_REQUIRED", "reason": str(error)}
    else:
        capabilities["automatic_integration"] = {"status": "BLOCKED_BY_CAPABILITY_FINDINGS"}
    return UsbTransportPlan(UsbTransportPlanResult.Rejected if reasons else
        UsbTransportPlanResult.Experimental, stack, part, indexed,
        tuple(dict.fromkeys(reasons)), hashes, owners, licenses, _REVIEW, capabilities)


def UsbAdaptation_Describe(plan: UsbTransportPlan, *, integrated: bool = False) -> dict:
    """Local import/audit description, never an assertion of runtime readiness.

    This does not create a second contracts/ authority or authorize arbitrary
    patch instructions. Source replacement remains generator-owned and bounded.
    """
    return {
        "format": "silverstar.usb.adaptation", "version": 1,
        "readiness": "BLOCKED" if plan.reasons else "EXPERIMENTAL_UNVERIFIED",
        "native_sources_sha256": plan.files_sha256, "native_owners": plan.owners,
        "capability_layers": plan.capabilities["layers"],
        "native_build_inventory": plan.capabilities.get("build", {}),
        "native_authority": ["clock", "pins", "PCD initialization", "USB initialization",
                             "PMA/FIFO layout", "startup", "linker", "IRQ wiring"],
        "bindings": {"device": "hUsbDeviceFS", "initialize": "MX_USB_DEVICE_Init",
                     "receive": "CDC_Receive_FS", "transmit": "CDC_Transmit_FS",
                     "class_data": "pClassDataCmsit[0]" if plan.indexed else "pClassData"},
        "transport": {"rx_capacity": 512, "tx_capacity": 256, "packet_size": 64,
                      "queue_success_is_delivery_ack": False},
        "lifecycle_hooks": {name: "GENERATED_NOT_ACCEPTED" if integrated else "UNBOUND_REQUIRES_REVIEW"
            for name in ("configure_after_native_success", "receive_copy_and_deferred_rearm", "single_main_service",
                         "invalidate_on_reset_disconnect_suspend_fault", "retire_only_after_checked_cancellation")},
        "build_attachment": {"source_replacements": "lifecycle-integration.json" if integrated else None,
            "additional_sources": ["Src/usb_cdc_transport.c", "Src/usb_cdc_port.c"] +
                (["Src/usb_cdc_retire.c"] if integrated else []),
            "assertion_owner": "CHOOSE_BUNDLED_OR_EXISTING_EXACTLY_ONCE"},
        "automatic_integration": plan.capabilities["automatic_integration"],
        "missing_capabilities": list(plan.reasons),
        "configuration_findings": plan.capabilities["configuration_findings"],
        "required_evidence": ["effective compiler dependencies and ABI", "unique source replacement graph",
            "normal and fault Host cases", "ARM link and analyzer", "critical-contract review",
            "controller cancellation and IRQ timing on board", "complete stack bounds"],
        "acceptance": "NOT_PROVEN",
    }


def _AssertionFiles_Read() -> dict[str, bytes]:
    scg = Path(__file__).resolve().parents[3]
    payload = scg / "plugins/builtin/silverstar_core_0_1_0/payload"
    paths = ("Common/Inc/silverstar_assert.h", "Common/Inc/silverstar_compiler.h",
             "Common/Src/silverstar_assert.c")
    return {**{p: (payload / p).read_bytes() for p in paths},
            "LICENSE-SilverStar.txt": (scg.parents[1] / "LICENSE").read_bytes()}


def UsbTransport_Export(input_path: str | Path, output_path: str | Path, *, integrate: bool = False) -> UsbTransportPlan:
    root = Path(input_path).absolute()
    output = Path(output_path).absolute()
    if any(p.is_symlink() or p.is_junction() for p in (output, *output.parents)):
        raise CubeMxImportError("USB kit output aliases are not supported")
    plan = UsbTransport_Plan(root)
    if plan.result != UsbTransportPlanResult.Experimental:
        raise CubeMxImportError("USB integration rejected: " + "; ".join(plan.reasons))
    integrated = {}
    if integrate:
        from silverstar_fccg.generator.usb_cdc_integration import UsbCdcIntegration_Render
        native = _Project_Read(root)
        if {p: hashlib.sha256(b).hexdigest() for p, b in native.items()} != plan.files_sha256:
            raise CubeMxImportError("Native USB input changed before integration")
        try:
            integrated = UsbCdcIntegration_Render(native, plan.owners)
        except ValueError as error:
            raise CubeMxImportError(str(error)) from error
    if output.resolve().is_relative_to(root.resolve()) or root.resolve().is_relative_to(output.resolve()):
        raise CubeMxImportError("USB kit output must be disjoint from the input")
    policy = WorkspacePolicy(output.parent)
    destination = policy.Path_Resolve(output, allow_root=False)
    if destination.exists():
        raise CubeMxImportError("USB kit output must not already exist")
    if (output.parent / ".staging").is_symlink() or (output.parent / ".staging").is_junction():
        raise CubeMxImportError("USB kit staging aliases are not supported")
    stage = policy.StagingDirectory_Create("usb-kit-")
    try:
        rendered = UsbCdcTransport_Render(indexed=plan.indexed)
        rendered.update(integrated)
        assertion_files = _AssertionFiles_Read()
        rendered.update(assertion_files)
        rendered["assertion-owner.json"] = json.dumps({
            "owner": "apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload",
            "license": "repository LICENSE (Apache-2.0); native input licenses remain independent",
            "files_sha256": {p: hashlib.sha256(b).hexdigest() for p, b in assertion_files.items()},
        }, indent=2).encode()
        rendered["integration.json"] = json.dumps(asdict(plan), indent=2).encode()
        rendered["usb-adaptation.json"] = json.dumps(UsbAdaptation_Describe(plan, integrated=integrate), indent=2).encode()
        rendered["README.txt"] = (
            "Experimental integration kit, not a ready firmware. Native project unchanged.\n"
            "See apps/SCG/docs/USB_CDC_TRANSPORT_20261013.md for all hook contracts.\n"
            "Includes the unchanged SilverStar fail-stop owner and its Apache-2.0 license.\n"
            "Call Configure only after real configuration success. Native Init owns first RX arm.\n"
            "CDC Receive: call UsbCdc_Receive exactly once; remove native immediate rearm.\n"
            "Main owner: call UsbCdc_Service regularly and check every result.\n"
            "Reset/disconnect/unconfigure/suspend/fault: LinkDown before application publication.\n"
            "Quiesced only after successful hardware cancellation; never from timeout/state alone.\n"
            "Then Configure on a new successful configuration. All TX writers must use this kit.\n"
            "USBD_OK can hide discarded LL failures; middleware acceptance remains NOT PROVEN.\n"
            "CMake >= 3.17: include usb_cdc_transport.cmake; UsbCdc_Attach(target BUNDLED).\n"
            "For an existing compatible SilverStar assertion owner use EXISTING instead.\n"
            "Make: add both Src C files, Inc and Common/Inc; include Common/Src/silverstar_assert.c\n"
            "only when the native target does not already link that assertion owner.\n"
            "No hooks, stack source patches, clock or IRQ edits are applied automatically.\n"
        ).encode()
        if integrate:
            rendered["README.txt"] += (
                "\nOPT-IN SOURCE-BOUND INTEGRATION: lifecycle-integration.json lists exact replacements.\n"
                "Compile each Native derivative instead of its original, never both; add all additional_sources.\n"
                "CubeMX clock/PMA/FIFO/initialization/startup remain authoritative. Input project is unchanged.\n"
                "Configuration is checked before class initialization; invalid PMA/FIFO layout blocks online state.\n"
                "Do not use the plain UsbCdc_Attach fragment alone for an integrated build.\n"
                "Suspend invalidates the session; resume stays offline until reset/reconfiguration.\n"
                "This connects callbacks in source, not a hardware or full safety acceptance.\n"
            ).encode()
        for relative, body in rendered.items():
            path = stage / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        if UsbTransport_Plan(root) != plan or _AssertionFiles_Read() != assertion_files:
            raise CubeMxImportError("Native USB input changed during export")
        manifest = {p: hashlib.sha256(b).hexdigest() for p, b in rendered.items()}
        # Reserve exclusively. Never replace even an empty directory created
        # concurrently by the user. A completion manifest is published last;
        # failures leave an identifiable incomplete kit, never delete user data.
        destination.mkdir()
        for relative, body in {**rendered, "kit-sha256.json": json.dumps(manifest, indent=2).encode()}.items():
            path = policy.Path_Resolve(destination / relative, allow_root=False)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(body)
    finally:
        if stage.exists():
            policy.Tree_Remove(stage)
    return plan


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--integrate", action="store_true",
                        help="Export source-bound native lifecycle derivatives; requires --output")
    args = parser.parse_args()
    if args.integrate and not args.output:
        parser.error("--integrate requires --output")
    plan = UsbTransport_Export(args.input, args.output, integrate=args.integrate) if args.output else UsbTransport_Plan(args.input)
    print(json.dumps(asdict(plan), indent=2))
    return 0 if plan.result == UsbTransportPlanResult.Experimental else 2


if __name__ == "__main__":
    raise SystemExit(main())
