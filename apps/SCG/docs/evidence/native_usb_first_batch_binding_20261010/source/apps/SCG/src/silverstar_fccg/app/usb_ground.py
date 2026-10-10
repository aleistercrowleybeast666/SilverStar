"""First-batch USB backend selection and C071 native/companion model binding.

The registry is backend-owned. Project flags, part names and capability labels
are not admission or release authority. C071 source identity can be bound while
its firmware renderer/build integration and USB acceptance remain blocked.
Existing F407 private APIs remain available outside this first-batch dispatcher.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re

from silverstar_fccg.app.native_ground import (
    BINDING_KEY, NativeGroundProjectImportResult, NativeGroundBackendResult,
    NativeGroundProject_Import, NativeGroundCandidate_Plan,
    NativeGroundCandidate_Export, NativeGroundCandidate_Build, _Resources_Get,
)
from silverstar_fccg.hardware.cubemx import CubeMxImportError, CubeMxImportResult
from silverstar_fccg.hardware.inventory import CubeMxInventory_Parse
from silverstar_fccg.hardware.native_classic_cdc import NativeDeviceFacts, NativeMemoryRegion
from silverstar_fccg.project.model import (
    HardwareConfiguration, HardwareResource, ProjectModel_Parse,
    GroundRadioConfigurations_Get,
)

C071_PART = "STM32C071FBP6"
C071_KEY = "usb_ground_c071_native"
C071_PROFILE = "C071FBP6_MINI_USB_V1"
C071_PREFIX = "HardwareGenerated/UsbGroundNative/"
FIRST_BATCH_PARTS = ("STM32F103C8T6", C071_PART)
C071_LIMITS = ("C071 native PCD/companion identity and model plan only; firmware "
    "render/build integration NOT IMPLEMENTED in this backend. Formal USB release "
    "BLOCKED: b66 independent review has no passed outcome and must not be retried "
    "or bypassed. Full EP0/async lifecycle, critical contracts, stack/WCET and hardware NOT PROVEN.")
_PROFILE_HASHES = {
    "f103-device-facts.json": "7c4ec3cb53e16dc856fdfcc6f87f0be8889df2403e870d719b65b0f4329f3126",
    "c071-device-facts.json": "b48d9ea209c362f7ba0a662a8c695a8ec0e3d659bd26b96b7700d962d397a014",
    "c071-native-profile.json": "5c9ad2ccaae3b0bd4a81c00e5c450610f48c82b7d5958c9587b921be82d29589",
    "c071-companion-manifest.json": "8835f4c76e6ea94ceeccf742ec59665157ddf2a089a4a361ad25b2671afcc6d7",
}


class UsbGroundPlanResult(str, Enum):
    RenderedCandidate = "RenderedCandidate"
    BlockedFirmwareIntegration = "BlockedFirmwareIntegration"


@dataclass(frozen=True, slots=True)
class UsbGroundCandidatePlan:
    result: UsbGroundPlanResult
    part: str
    profile: str
    model_sha256: str
    source_snapshot_id: str
    capability_facts: dict
    native_plan: object | None
    recipe_plan: dict
    detail: str


def _Json_Encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _Hash_Get(body):
    return hashlib.sha256(body).hexdigest()


def _Profile_Load(name):
    path = Path(__file__).resolve().parents[1] / "hardware/usb_profiles" / name
    if (name not in _PROFILE_HASHES or path.is_symlink() or
            _Hash_Get(path.read_bytes()) != _PROFILE_HASHES[name]):
        raise CubeMxImportError("Backend USB target profile identity changed")
    return json.loads(path.read_text(encoding="utf-8"))


def UsbGroundTarget_Validate(part: str, hclk_hz: int):
    expected = {"STM32F103C8T6": 72_000_000, C071_PART: 48_000_000}
    if part not in expected or type(hclk_hz) is not int or expected[part] != hclk_hz:
        raise CubeMxImportError("First-batch USB backend requires exact F103C8T6/72MHz or C071FBP6/48MHz; F407 remains a separate private candidate")


def UsbGroundDeviceFacts_Get(part: str, independent_irq_header: Path) -> NativeDeviceFacts:
    if part not in FIRST_BATCH_PARTS:
        raise CubeMxImportError("Unsupported first-batch exact USB target")
    values = _Profile_Load("f103-device-facts.json" if part == FIRST_BATCH_PARTS[0] else "c071-device-facts.json")
    facts = NativeDeviceFacts(**{**values,
        "regions": tuple(NativeMemoryRegion(**item) for item in values["regions"]),
        "irq_numbers": tuple(tuple(item) for item in values["irq_numbers"])})
    facts.Facts_Validate()
    path = Path(independent_irq_header)
    if path.is_symlink() or path.is_junction() or not path.is_file():
        raise CubeMxImportError("Independent SDK IRQ header unavailable")
    body = path.read_bytes()
    enumerators = tuple((name, int(value)) for name, value in
        re.findall(r"([A-Za-z0-9_]+_IRQn)\s*=\s*(-?\d+)", body.decode("utf-8-sig")))
    if _Hash_Get(body) != facts.irq_header_sha256 or enumerators != facts.irq_numbers:
        raise CubeMxImportError("Independent SDK IRQ bytes/enumerators differ from backend facts")
    return facts


def _IndependentHeader_Validate(header, root):
    if Path(header).resolve().is_relative_to(root.resolve()):
        raise CubeMxImportError("Independent SDK facts must be supplied outside the native input/cache")


def _Companion_Inspect(root):
    if root is None:
        raise CubeMxImportError("C071 requires the pinned external companion source identity; no project capability flag can substitute")
    root = Path(root).resolve()
    expected = _Profile_Load("c071-companion-manifest.json")
    manifest = root / "companion-manifest.json"
    if _Hash_Get(manifest.read_bytes()) != _PROFILE_HASHES["c071-companion-manifest.json"]:
        raise CubeMxImportError("C071 companion manifest identity changed")
    payload = root / "payload"
    actual = set()
    for path in payload.rglob("*"):
        if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(payload):
            raise CubeMxImportError("C071 companion payload alias rejected")
        if path.is_file():
            actual.add(path.relative_to(payload).as_posix())
    if actual != set(expected["files_sha256"]):
        raise CubeMxImportError("C071 companion payload inventory changed")
    for relative, digest in expected["files_sha256"].items():
        if _Hash_Get((payload / relative).read_bytes()) != digest:
            raise CubeMxImportError("C071 companion payload identity changed: " + relative)
    # Byte identity is deliberately separate from review, ABI and runtime proof.
    return {"source_commit": "b66f142f7ab9b5611bd2f9a84a105835e4f77b96",
        "component": "silverstar.usb_cdc.stm32c071_mini", "version": "0.1.1",
        "manifest_sha256": _PROFILE_HASHES["c071-companion-manifest.json"],
        "files_sha256": expected["files_sha256"], "independent_review": "NO_PASSED_OUTCOME",
        "formal_release": False}


def _C071Native_Inspect(root):
    profile = _Profile_Load("c071-native-profile.json")
    iocs = tuple(root.glob("*.ioc"))
    if len(iocs) != 1:
        raise CubeMxImportError("C071 requires one root IOC")
    expected = dict(profile["files_sha256"])
    expected.update({iocs[0].name: profile["ioc_sha256"], "Makefile": profile["makefile_sha256"],
        "startup_stm32c071xx.s": profile["startup_sha256"], "STM32C071XX_FLASH.ld": profile["linker_sha256"]})
    actual = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(root):
            raise CubeMxImportError("C071 native input alias rejected")
        if any(part.casefold() in {"build", ".git", "debug", "release"} for part in relative.parts):
            continue
        if path.is_file() and (relative.parts[0] in {"Core", "Drivers"} or
                path.suffix.lower() in {".c", ".h", ".s", ".ld", ".ioc"} or path.name == "Makefile"):
            actual.add(relative.as_posix())
    if actual != set(expected):
        raise CubeMxImportError("C071 native complete source inventory changed")
    if sum((root / p).stat().st_size for p in expected) > 32 * 1024 * 1024:
        raise CubeMxImportError("C071 native snapshot exceeds fixed profile bound")
    files = {p: (root / p).read_bytes() for p in expected}
    if any(_Hash_Get(files[p]) != digest for p, digest in expected.items()):
        raise CubeMxImportError("C071 native pin/clock/build/source identity changed")
    generated = {p: b.decode("utf-8-sig") for p, b in files.items() if p.startswith("Core/")}
    inventory = CubeMxInventory_Parse(files[iocs[0].name].decode("utf-8-sig"), generated_files=generated)
    return files, inventory, iocs[0].name, profile


def _C071Model_Validate(model, spi, gpio):
    radios = GroundRadioConfigurations_Get(model.ground_target)
    ground = model.ground_target
    if (not ground.enabled or ground.pc_interface != "usb_cdc" or
            model.air_link.radio_family != "sx128x" or len(radios) != 1 or
            radios[0].plugin != "silverstar.device.telemetry.sx1281" or
            radios[0].module_variant != "e28_2g4m12sx" or radios[0].instance_id != "radio0" or
            (spi, tuple(gpio)) != ("SPI1", ("RADIO_NSS", "RADIO_RESET", "RADIO_BUSY", "RADIO_DIO1")) or
            ground.tx_led_resource or ground.rx_led_resource or ground.activity_led_enabled is True):
        raise CubeMxImportError("C071 model requires exact mini USB/single E28 resource profile; unrelated configurations are not silently replaced")


def _Snapshot_Store(importer, files, proof):
    encoded = _Json_Encode(proof)
    identity = _Hash_Get(encoded)
    parent = importer.policy.Path_Resolve(importer.cache_root / identity, allow_root=False)
    destination = parent / "UsbGroundNative"
    if os.name == "nt" and any(len(str(destination / p)) >= 248 for p in files):
        raise CubeMxImportError("Select a shorter workspace for portable native snapshot paths")
    if parent.exists():
        if not destination.is_dir() or (parent / "usb-ground-contract.json").read_bytes() != encoded:
            raise CubeMxImportError("Immutable C071 snapshot contract changed")
        cached, _inventory, _ioc, _profile = _C071Native_Inspect(destination)
        if cached != files:
            raise CubeMxImportError("Immutable C071 native snapshot changed")
    else:
        stage = importer.policy.StagingDirectory_Create("usb-ground-")
        try:
            for relative, body in files.items():
                importer.policy.RelativePath_Validate(relative)
                path = stage / "UsbGroundNative" / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
            (stage / "usb-ground-contract.json").write_bytes(encoded)
            parent.parent.mkdir(parents=True, exist_ok=True)
            importer.policy.Path_Replace(stage, parent)
        finally:
            if stage.exists():
                importer.policy.Tree_Remove(stage)
    return identity, destination


def UsbGroundProject_Import(importer, catalog, input_path, model, *, part,
        independent_irq_header, hclk_hz, spi_resource, gpio_resources,
        risk_acknowledged, companion_root=None):
    UsbGroundTarget_Validate(part, hclk_hz)
    if risk_acknowledged is not True:
        raise CubeMxImportError("Explicit private USB candidate acknowledgement required")
    root, _ioc = importer._Input_Resolve(input_path)
    _IndependentHeader_Validate(independent_irq_header, root)
    facts = UsbGroundDeviceFacts_Get(part, independent_irq_header)
    if part == FIRST_BATCH_PARTS[0]:
        return NativeGroundProject_Import(importer, catalog, input_path, model,
            device_facts=facts, hclk_hz=hclk_hz, spi_resource=spi_resource,
            gpio_resources=gpio_resources, risk_acknowledged=True)
    _C071Model_Validate(model, spi_resource, gpio_resources)
    companion = _Companion_Inspect(companion_root)
    files, inventory, ioc, profile = _C071Native_Inspect(root)
    proof = {"part": part, "profile": C071_PROFILE, "hclk_hz": hclk_hz,
        "input_kind": "native_pcd_plus_pinned_classic_cdc", "native_cdc": False,
        "native_files_sha256": {p: _Hash_Get(b) for p, b in files.items()},
        "companion": companion, "native_profile_sha256": _PROFILE_HASHES["c071-native-profile.json"],
        "spi": spi_resource, "gpio": list(gpio_resources), "formal_generation": "BLOCKED"}
    identity, destination = _Snapshot_Store(importer, files, proof)
    candidate = deepcopy(model)
    binding = {"format_version": 2, "scope": "PRIVATE_USB_GROUND_C071_BINDING",
        "snapshot_id": identity, "profile": C071_PROFILE, "hclk_hz": hclk_hz,
        "formal_generation": "BLOCKED"}
    # No USB CDC runtime capability is granted from a PCD-only native project.
    native_build = profile["effective_build"]
    def paths(name):
        return tuple(C071_PREFIX + p.removeprefix("HardwareGenerated/STM32CubeMX/")
            for p in native_build[name] if p.startswith("HardwareGenerated/STM32CubeMX/"))
    hardware = HardwareConfiguration(mode="custom", source_kind="manual_import",
        provider="silverstar.hardware_provider.stm32_cubemx", snapshot_id=identity,
        ioc_file=ioc, mcu=part, cubemx_version=inventory.cubemx_version,
        firmware_package=inventory.firmware_package, hal_cmsis_source_policy="imported_tree_authoritative",
        capabilities=("usb.native_pcd",), inventory={**inventory.Dictionary_Get(), C071_KEY: proof, BINDING_KEY: binding},
        resources=tuple(HardwareResource(r.resource_id, r.kind, deepcopy(r.metadata)) for r in inventory.HardwareResources_Get()),
        build_sources=paths("build_sources"), asm_sources=paths("asm_sources"), include_dirs=paths("include_dirs"),
        defines=tuple(native_build["defines"]), linker_script=C071_PREFIX + "STM32C071XX_FLASH.ld",
        source_digest=identity, source_label=root.name, risk_acknowledged=True)
    candidate.ground_target = replace(candidate.ground_target, mcu="", board="", hardware=hardware,
        resource_assignments=_Resources_Get(candidate, spi_resource, tuple(gpio_resources)), pc_resource="")
    candidate = ProjectModel_Parse(candidate.Dictionary_Get())
    imported = CubeMxImportResult(hardware, destination, tuple(inventory.peripherals), (C071_LIMITS,), inventory)
    return NativeGroundProjectImportResult(NativeGroundBackendResult.ImportedCandidate, candidate, imported, C071_PROFILE)


def UsbGroundCandidate_Plan(importer, catalog, model, *, independent_irq_header, companion_root=None):
    hardware = model.ground_target.hardware
    part = hardware.mcu
    facts = UsbGroundDeviceFacts_Get(part, independent_irq_header)
    if part == FIRST_BATCH_PARTS[0]:
        snapshot = importer.cache_root / hardware.snapshot_id
        _IndependentHeader_Validate(independent_irq_header, snapshot)
        plan = NativeGroundCandidate_Plan(importer, catalog, model, device_facts=facts)
        return UsbGroundCandidatePlan(UsbGroundPlanResult.RenderedCandidate, part, plan.profile,
            plan.model_sha256, plan.snapshot_id,
            {"native_classic_cdc": True, "formal_release": False}, plan, {}, "F103 private candidate only; formal release BLOCKED")
    proof = hardware.inventory.get(C071_KEY)
    binding = hardware.inventory.get(BINDING_KEY)
    if not isinstance(proof, dict) or not isinstance(binding, dict):
        raise CubeMxImportError("C071 binding missing; use unified import first")
    UsbGroundTarget_Validate(part, binding.get("hclk_hz"))
    identity = _Hash_Get(_Json_Encode(proof))
    if hardware.snapshot_id != identity or hardware.source_digest != identity:
        raise CubeMxImportError("C071 model source binding changed")
    snapshot = importer.policy.Path_Resolve(importer.cache_root / identity / "UsbGroundNative", allow_root=False)
    _IndependentHeader_Validate(independent_irq_header, snapshot)
    result = UsbGroundProject_Import(importer, catalog, snapshot, model, part=part,
        independent_irq_header=independent_irq_header, hclk_hz=binding["hclk_hz"],
        spi_resource=proof.get("spi"), gpio_resources=tuple(proof.get("gpio", ())),
        risk_acknowledged=True, companion_root=companion_root)
    # source_label records the original display name, not capability authority.
    expected = result.model.Dictionary_Get()
    expected["ground_target"]["hardware"]["source_label"] = hardware.source_label
    if _Json_Encode(expected) != _Json_Encode(model.Dictionary_Get()):
        raise CubeMxImportError("C071 saved model/source/resource/capability binding changed")
    profile = _Profile_Load("c071-native-profile.json")
    return UsbGroundCandidatePlan(UsbGroundPlanResult.BlockedFirmwareIntegration, part, C071_PROFILE,
        _Hash_Get(_Json_Encode(model.Dictionary_Get())), identity,
        {"native_pcd": True, "native_classic_cdc": False, "companion_source_identity_verified": True,
         "cdc_runtime_accepted": False, "formal_release": False}, None,
        {"effective_build_to_integrate": profile["effective_build"], "companion": proof["companion"],
         "firmware_files_rendered": False, "native_hal_cmsis_startup_linker_pcd_ownership": "PRESERVED"}, C071_LIMITS)


def UsbGroundCandidate_Export(importer, catalog, model, output, *, independent_irq_header, companion_root=None):
    plan = UsbGroundCandidate_Plan(importer, catalog, model,
        independent_irq_header=independent_irq_header, companion_root=companion_root)
    if plan.result != UsbGroundPlanResult.RenderedCandidate:
        raise CubeMxImportError(plan.detail)
    facts = UsbGroundDeviceFacts_Get(plan.part, independent_irq_header)
    return NativeGroundCandidate_Export(importer, catalog, model, output, device_facts=facts)


def UsbGroundCandidate_Build(importer, catalog, model, project_root, output, *, independent_irq_header, companion_root=None):
    plan = UsbGroundCandidate_Plan(importer, catalog, model,
        independent_irq_header=independent_irq_header, companion_root=companion_root)
    if plan.result != UsbGroundPlanResult.RenderedCandidate:
        raise CubeMxImportError(plan.detail)
    facts = UsbGroundDeviceFacts_Get(plan.part, independent_irq_header)
    return NativeGroundCandidate_Build(importer, catalog, model, project_root, output, device_facts=facts)
